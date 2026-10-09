"""Bounded, portable backups with validated, additive recovery."""
import io
import json
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4
import db
from organizer import DEFAULT_STATE, validate_state

MAX_BACKUP = 50 * 1024 * 1024
MAX_EXPANDED = 100 * 1024 * 1024
SUFFIXES = {".png", ".jpg", ".jpeg", ".pdf"}


def _task(task, source_ids):
    from validation import validate_task
    if not isinstance(task, dict):
        raise ValueError("Invalid backed-up task.")
    validate_task(task)
    if task["source_id"] not in source_ids:
        raise ValueError("Task refers to a missing source.")


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("format") != "panuto-backup" or snapshot.get("version") != 1:
        raise ValueError("Unsupported Panuto backup format.")
    sources, tasks = snapshot.get("sources"), snapshot.get("tasks")
    if not isinstance(sources, list) or not isinstance(tasks, list) or len(sources) > 10000 or len(tasks) > 5000:
        raise ValueError("Invalid or oversized backup.")
    ids = set()
    for source in sources:
        source_id = source.get("source_id") if isinstance(source, dict) else None
        if not isinstance(source_id, str) or not re.fullmatch(r"[\w-]{1,128}", source_id) or source_id in ids:
            raise ValueError("Duplicate or invalid source.")
        ids.add(source_id)
        if source.get("kind") not in {"text", "image", "pdf"} or not isinstance(source.get("text"), str):
            raise ValueError("Invalid announcement source.")
        if not isinstance(source.get("warnings"), list) or any(not isinstance(x, str) for x in source["warnings"]):
            raise ValueError("Invalid source warnings.")
        if source.get("announcement_date") is not None:
            date.fromisoformat(source["announcement_date"])
        confidence = source.get("ocr_confidence")
        if confidence is not None and (type(confidence) not in (int, float) or not 0 <= confidence <= 100):
            raise ValueError("Invalid OCR confidence.")
        attachment = source.get("attachment")
        if attachment is not None and (not isinstance(attachment, str) or
                attachment != "sources/" + source_id + Path(attachment).suffix or
                Path(attachment).suffix not in SUFFIXES):
            raise ValueError("Invalid attachment path.")
    task_ids = set()
    for item in tasks:
        if not isinstance(item, dict) or type(item.get("id")) is not int or item["id"] in task_ids:
            raise ValueError("Invalid or duplicate activity.")
        task_ids.add(item["id"])
        _task(item["task"], ids)
        validate_state(item["state"])
        versions = item.get("versions")
        if not isinstance(versions, list) or not versions:
            raise ValueError("Missing task history.")
        for number, version in enumerate(versions, 1):
            if not isinstance(version, dict) or version.get("version") != number or not isinstance(version.get("source_text"), str):
                raise ValueError("Invalid version history.")
            datetime.fromisoformat(version["created_at"])
            _task(version["task"], ids)
        if versions[-1]["task"] != item["task"]:
            raise ValueError("Current task does not match its latest version.")
    return snapshot


def create_backup():
    rows = db.export_snapshot()
    states = {row["task_id"]: row for row in rows["task_state"]}
    sources = []
    files = {}
    source_root = db.source_directory().resolve()
    total = 0
    for row in rows["sources"]:
        source = dict(row)
        source["warnings"] = json.loads(source["warnings"])
        source["attachment"] = None
        path = Path(row["original_path"]) if row["original_path"] else None
        if path and path.is_file() and path.resolve().parent == source_root and path.suffix.lower() in SUFFIXES:
            name = "sources/" + row["source_id"] + path.suffix.lower()
            size = path.stat().st_size
            total += size
            if size > 20 * 1024 * 1024 or total > MAX_EXPANDED:
                raise ValueError("Backup exceeds attachment size limits.")
            files[name] = path.read_bytes()
            source["attachment"] = name
        elif path:
            source["warnings"].append("Original file unavailable in backup; source text is preserved.")
        source.pop("original_path", None)
        sources.append(source)
    tasks = []
    for row in rows["tasks"]:
        task = json.loads(row["task_json"])
        task.pop("id", None)
        versions = []
        for version in rows["task_versions"]:
            if version["task_id"] == row["id"]:
                versions.append(dict(version=version["version"], task=json.loads(version["task_json"]),
                                     source_text=version["source_text"], created_at=version["created_at"]))
        state = dict(DEFAULT_STATE, **{key: states.get(row["id"], {}).get(key, value)
                                     for key, value in DEFAULT_STATE.items()})
        state["archived"] = bool(state["archived"])
        tasks.append(dict(id=row["id"], task=task, versions=sorted(versions, key=lambda v: v["version"]), state=state))
    snapshot = validate_snapshot(dict(format="panuto-backup", version=1, sources=sources, tasks=tasks))
    manifest = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
    if len(manifest) + total > MAX_EXPANDED:
        raise ValueError("Backup exceeds size limits.")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest)
        for name, data in files.items():
            archive.writestr(name, data)
    if output.tell() > MAX_BACKUP:
        raise ValueError("Backup exceeds 50 MB. Copy the data directory with the app stopped instead.")
    return output.getvalue()


def inspect_backup(data):
    if len(data) > MAX_BACKUP:
        raise ValueError("Backup exceeds 50 MB.")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) > 10001 or len(set(names)) != len(names) or sum(x.file_size for x in infos) > MAX_EXPANDED:
            raise ValueError("Duplicate entries or oversized backup.")
        if "manifest.json" not in names or archive.getinfo("manifest.json").file_size > 20 * 1024 * 1024:
            raise ValueError("Missing or oversized backup manifest.")
        try:
            snapshot = validate_snapshot(json.loads(archive.read("manifest.json")))
        except (RecursionError, UnicodeDecodeError) as exc:
            raise ValueError("Backup manifest cannot be read.") from exc
        expected = {"manifest.json"} | {s["attachment"] for s in snapshot["sources"] if s.get("attachment")}
        if set(names) != expected:
            raise ValueError("Unexpected or missing backup files.")
        for info in infos:
            if info.filename != "manifest.json" and info.file_size > 20 * 1024 * 1024:
                raise ValueError("Attachment exceeds 20 MB.")
        # Force CRC checks before any storage mutation.
        for name in names:
            archive.read(name)
        return snapshot


def restore_backup(data):
    snapshot = inspect_backup(data)
    created = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for source in snapshot["sources"]:
                source["original_path"] = None
                attachment = source.get("attachment")
                if attachment:
                    folder = db.source_directory()
                    folder.mkdir(parents=True, exist_ok=True)
                    target = folder / (uuid4().hex + Path(attachment).suffix)
                    created.append(target)
                    target.write_bytes(archive.read(attachment))
                    source["original_path"] = str(target)
        return db.import_snapshot(snapshot)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
