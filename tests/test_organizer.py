import csv
import io
import json
import sqlite3
import zipfile
from datetime import date
import pytest
import db
import backup
from ingestion import ingest_text
from organizer import filter_tasks, csv_export, calendar_export
from test_core import task


def seed(path):
    db.init_db(path)
    doc = ingest_text("Original announcement")
    task_id = db.save_task(task(doc.source_id), doc)
    revised = ingest_text("Updated announcement")
    db.add_version(task_id, task(revised.source_id, deadline="2026-10-23"), revised)
    db.set_state(task_id, "In progress", "High", "Bring notes", True)
    return task_id


def test_existing_database_additive_migration(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY,task_json TEXT NOT NULL,subject TEXT,activity TEXT,deadline TEXT)")
        connection.execute("INSERT INTO tasks VALUES(1,?,?,?,?)",
                           (json.dumps(task()), "ML", "activity", "2026-10-16"))
    db.init_db(path)
    assert db.get_task(1)["activity"] == "activity"
    assert db.get_states() == {}
    db.set_state(1, "Done", "High", "Personal note", True)
    db.init_db(path)
    assert db.get_states()[1]["status"] == "Done"
    assert db.get_task(1)["requirements"][0]["number"] == 300


def test_state_validation_and_missing_task(tmp_path):
    db.init_db(tmp_path / "db.sqlite")
    with pytest.raises(ValueError):
        db.set_state(1, status="Invented")
    with pytest.raises(KeyError):
        db.set_state(1)
    assert db.get_states() == {}


def test_filters_due_and_priority():
    tasks = [dict(task(), id=1), dict(task(deadline=None, subject="Physics"), id=2),
             dict(task(deadline="2026-10-23"), id=3)]
    states = {1: dict(status="Done", archived=False), 2: dict(priority="High", notes="Review vectors"),
              3: dict(archived=True)}
    today = date(2026, 10, 16)
    assert [x["id"] for x in filter_tasks(tasks, states, status="Done", today=today)] == [1]
    assert [x["id"] for x in filter_tasks(tasks, states, query="VECTORS", today=today)] == [2]
    assert filter_tasks(tasks, states, due="Due today", today=today) == []
    assert [x["id"] for x in filter_tasks(tasks, states, archive="Archived", today=today)] == [3]
    assert [x["id"] for x in filter_tasks(tasks, states, sort="Priority", today=today)] == [2, 1]
    assert filter_tasks(tasks, {}, due="Due today", today=today)[0]["id"] == 1
    assert filter_tasks(tasks, {}, due="Overdue", today=date(2026,10,17))[0]["id"] == 1


def test_exports_escape_and_unknown_dates():
    tasks = [dict(task(subject="=HYPERLINK(bad)", activity="Test, quiz\nnext line", deadline_time="23:59"),
                  id=1, status="To do", notes="@formula"),
             dict(task(deadline=None), id=2), dict(task(), id=3, status="Done")]
    rows = list(csv.DictReader(io.StringIO(csv_export(tasks).decode("utf-8-sig"))))
    assert rows[0]["subject"].startswith("'=") and rows[0]["notes"] == "'@formula"
    calendar = calendar_export(tasks).decode()
    assert calendar.count("BEGIN:VEVENT") == 1
    assert "DTSTART:20261016T235900" in calendar
    assert "Test\\, quiz\\nnext line" in calendar
    all_day = calendar_export([dict(task(),id=1)]).decode()
    assert "DTEND;VALUE=DATE:20261017" in all_day
    assert max(len(line.encode()) for line in calendar_export(
        [dict(task(subject="Filipino " * 50),id=1)]).decode().split("\r\n")) <= 75


def test_backup_recovery_preserves_history_and_files(tmp_path):
    original = tmp_path / "original" / "db.sqlite"
    task_id = seed(original)
    source_dir = db.source_directory()
    source_dir.mkdir()
    image = source_dir / "test.jpg"
    image.write_bytes(b"synthetic attachment bytes")
    with db._connect() as connection:
        connection.execute("UPDATE sources SET original_path=? WHERE source_id=?",
                           (str(image), db.get_task(task_id)["source_id"]))
    data = backup.create_backup()
    assert len(backup.inspect_backup(data)["tasks"]) == 1
    db.init_db(tmp_path / "restored" / "db.sqlite")
    existing = ingest_text("Existing task")
    db.save_task(task(existing.source_id, activity="Existing task"), existing)
    assert backup.restore_backup(data) == 1
    assert len(db.list_tasks()) == 2
    recovered = db.get_task(2)
    assert recovered["deadline"] == "2026-10-23"
    assert [x["source_text"] for x in db.list_versions(2)] == ["Original announcement", "Updated announcement"]
    assert db.get_states()[2]["status"] == "In progress"
    assert db.get_states()[2]["archived"] == 1
    assert next(db.source_directory().glob("*.jpg")).read_bytes() == image.read_bytes()
    assert recovered["source_id"] != db.get_task(1)["source_id"]


def rewrite(data, modify, extra=None):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(files["manifest.json"])
    modify(manifest)
    files["manifest.json"] = json.dumps(manifest).encode()
    if extra:
        files.update(extra)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


@pytest.mark.parametrize("mutation", [
    lambda m: m.update(version=99),
    lambda m: m["tasks"][0]["task"].update(deadline="2026-99-99"),
    lambda m: m["tasks"][0]["versions"].clear(),
    lambda m: m["tasks"][0]["state"].update(status="invalid"),
    lambda m: m["sources"][0].update(attachment="../secret.pdf"),
])
def test_invalid_backup_never_mutates_storage(tmp_path, mutation):
    seed(tmp_path / "db.sqlite")
    data = rewrite(backup.create_backup(), mutation)
    before = db.export_snapshot()
    with pytest.raises((ValueError, KeyError)):
        backup.restore_backup(data)
    assert db.export_snapshot() == before


def test_zip_paths_and_restore_rollback(tmp_path, monkeypatch):
    seed(tmp_path / "db.sqlite")
    data = backup.create_backup()
    malicious = rewrite(data, lambda m: None, {"../../evil.txt": b"bad"})
    with pytest.raises(ValueError, match="Unexpected"):
        backup.restore_backup(malicious)
    before = db.export_snapshot()
    def failed(_):
        raise sqlite3.OperationalError("disk unavailable")
    monkeypatch.setattr(db, "import_snapshot", failed)
    with pytest.raises(sqlite3.OperationalError):
        backup.restore_backup(data)
    assert db.export_snapshot() == before

def test_snapshot_restore_rolls_back_tasks_and_attachment_files(tmp_path, monkeypatch):
    seed(tmp_path / "origin" / "db.sqlite")
    folder = db.source_directory()
    folder.mkdir()
    image = folder / "proof.png"
    image.write_bytes(b"attachment")
    with db._connect() as connection:
        connection.execute("UPDATE sources SET original_path=?", (str(image),))
    other = ingest_text("Second activity")
    db.save_task(task(other.source_id, activity="Second activity"), other)
    data = backup.create_backup()
    db.init_db(tmp_path / "target" / "db.sqlite")
    original_payload = db._payload
    calls = 0
    def fail_second(item):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("Simulated interrupted recovery")
        return original_payload(item)
    monkeypatch.setattr(db, "_payload", fail_second)
    with pytest.raises(sqlite3.OperationalError):
        backup.restore_backup(data)
    assert db.list_tasks() == []
    assert db.export_snapshot()["sources"] == []
    assert list(db.source_directory().iterdir()) == []


def test_calendar_uid_survives_announcement_revision():
    old = dict(task(source_id="original"), id=1)
    new = dict(task(source_id="revision", deadline="2026-10-23"), id=1)
    def uid(item):
        return next(line for line in calendar_export([item]).decode().splitlines() if line.startswith("UID:"))
    assert uid(old) == uid(new)
