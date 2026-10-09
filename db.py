"""SQLite storage with transactional, source-backed version history."""
import json
import sqlite3
from pathlib import Path
from datetime import date
_DB_PATH = Path("data/panuto.db")

def _connect():
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

def init_db(path="data/panuto.db"):
    global _DB_PATH
    _DB_PATH = Path(path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS sources(
            source_id TEXT PRIMARY KEY, kind TEXT NOT NULL, text TEXT NOT NULL,
            original_path TEXT, announcement_date TEXT, ocr_confidence REAL, warnings TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY, task_json TEXT NOT NULL, subject TEXT, activity TEXT, deadline TEXT);
        CREATE INDEX IF NOT EXISTS task_deadlines ON tasks(deadline);
        CREATE TABLE IF NOT EXISTS task_versions(
            id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id),
            version INTEGER NOT NULL, task_json TEXT NOT NULL,
            source_id TEXT NOT NULL REFERENCES sources(source_id), source_text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(task_id, version));
        """)

def _payload(task):
    task = {key:value for key,value in task.items() if key != "id"}
    if task.get("deadline"):
        date.fromisoformat(task["deadline"])
    if not task.get("source_id"):
        raise ValueError("A confirmed task must have a source.")
    return json.dumps(task, ensure_ascii=False), task

def _source(connection, source):
    connection.execute("INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?)",
        (source.source_id, source.kind, source.text, source.original_path,
         source.announcement_date.isoformat() if source.announcement_date else None,
         source.ocr_confidence, json.dumps(source.warnings)))

def _version(connection, task_id, task, payload):
    source = connection.execute("SELECT text FROM sources WHERE source_id=?",
                                (task["source_id"],)).fetchone()
    if source is None:
        raise ValueError("Source does not exist.")
    number = connection.execute(
        "SELECT COALESCE(MAX(version),0)+1 FROM task_versions WHERE task_id=?", (task_id,)).fetchone()[0]
    connection.execute(
        "INSERT INTO task_versions(task_id,version,task_json,source_id,source_text) VALUES(?,?,?,?,?)",
        (task_id, number, payload, task["source_id"], source["text"]))

def save_task(task, source):
    payload, task = _payload(task)
    if source.source_id != task["source_id"]:
        raise ValueError("Task source does not match its announcement.")
    with _connect() as connection:
        _source(connection, source)
        cursor = connection.execute(
            "INSERT INTO tasks(task_json,subject,activity,deadline) VALUES(?,?,?,?)",
            (payload, task.get("subject"), task.get("activity"), task.get("deadline")))
        task_id = cursor.lastrowid
        _version(connection, task_id, task, payload)
    return task_id

def _update(connection, task_id, task, payload):
    cursor = connection.execute(
        "UPDATE tasks SET task_json=?,subject=?,activity=?,deadline=? WHERE id=?",
        (payload, task.get("subject"), task.get("activity"), task.get("deadline"), task_id))
    if not cursor.rowcount:
        raise KeyError(f"Task {task_id} does not exist.")
    _version(connection, task_id, task, payload)

def add_version(task_id, task, source):
    payload, task = _payload(task)
    if source.source_id != task["source_id"]:
        raise ValueError("Task source does not match its announcement.")
    with _connect() as connection:
        _source(connection, source)
        _update(connection, task_id, task, payload)

def update_task(task_id, task):
    payload, task = _payload(task)
    with _connect() as connection:
        _update(connection, task_id, task, payload)

def get_task(task_id):
    with _connect() as connection:
        row = connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise KeyError(f"Task {task_id} does not exist.")
    return dict(json.loads(row["task_json"]), id=row["id"])

def list_tasks():
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM tasks ORDER BY deadline IS NULL,deadline,id").fetchall()
    return [dict(json.loads(row["task_json"]), id=row["id"]) for row in rows]

def list_versions(task_id):
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM task_versions WHERE task_id=? ORDER BY version", (task_id,)).fetchall()
    return [dict(version=row["version"], task=json.loads(row["task_json"]), source_id=row["source_id"],
                 source_text=row["source_text"], created_at=row["created_at"]) for row in rows]
