import copy
import json
from datetime import date
from urllib.error import URLError
import pytest
import db
import extraction
import pipeline
from contracts import LLM_SCHEMA, ExtractionResult
from compare import compare_tasks, find_matches
from ingestion import ingest_text
from jsonschema import validate

def task(source_id="source", **changes):
    result = pipeline.blank_task(source_id)
    result.update(subject="ML",activity="activity",deadline="2026-10-16",
                  deadline_text="next Friday",group_size=3,submission_format="PDF",
                  submission_platform="LMS",needs_date_confirmation=False,
                  requirements=[{"text":"dataset minimum 300 rows","number":300}])
    result.update(changes)
    return result

def llm_task(**changes):
    result = {key:value for key,value in task().items() if key in LLM_SCHEMA["required"]}
    result.update(changes)
    return result

def test_core_revision_pair():
    old = task()
    new = task(deadline="2026-10-23",requirements=[
        {"text":"dataset minimum 500 rows","number":500},
        {"text":"include data dictionary","number":None}])
    diff = compare_tasks(old,new)
    assert [(item.field.split(":")[0],item.kind) for item in diff.changes] == [
        ("deadline","changed"),("requirements","changed"),("requirements","added")]
    assert diff.has_conflict
    assert not compare_tasks(old,copy.deepcopy(old)).has_conflict

def test_normalization_and_removal():
    old = task(submission_format=" PDF ")
    new = task(submission_format="pdf",requirements=[])
    changes = compare_tasks(old,new).changes
    assert len(changes) == 1 and changes[0].kind == "removed"

def test_matching_never_chooses_version():
    saved = [dict(task(),id=1),dict(task(activity="quiz"),id=2)]
    scores = dict(find_matches(task(subject="Machine Learning"),saved))
    assert scores[1] == 1
    assert scores.get(2,0) < 0.75
    assert not find_matches(task(subject=None,activity=None),saved)

def test_persistence_and_audit(tmp_path):
    path = tmp_path/"panuto.db"
    db.init_db(path)
    original = ingest_text("Original announcement",date(2026,10,12))
    revised = ingest_text("Revision announcement",date(2026,10,14))
    task_id = db.save_task(task(original.source_id),original)
    db.add_version(task_id,task(revised.source_id,deadline="2026-10-23"),revised)
    db.init_db(path)
    versions = db.list_versions(task_id)
    assert [item["version"] for item in versions] == [1,2]
    assert [item["source_text"] for item in versions] == [original.text,revised.text]
    assert db.get_task(task_id)["deadline"] == "2026-10-23"
    edit = db.get_task(task_id)
    edit["activity"] = "Confirmed activity"
    db.update_task(task_id,edit)
    assert len(db.list_versions(task_id)) == 3
    unknown = ingest_text("No deadline")
    db.save_task(task(unknown.source_id,deadline=None),unknown)
    assert db.list_tasks()[-1]["deadline"] is None

def test_transaction_rollback(tmp_path):
    db.init_db(tmp_path/"db.sqlite")
    source = ingest_text("Original")
    with pytest.raises(ValueError):
        db.save_task(task("different"),source)
    assert db.list_tasks() == []
    task_id = db.save_task(task(source.source_id),source)
    invalid = task("missing",deadline="2026-10-23")
    with pytest.raises(ValueError):
        db.update_task(task_id,invalid)
    assert db.get_task(task_id)["deadline"] == "2026-10-16"
    assert len(db.list_versions(task_id)) == 1

def test_extraction_retry(monkeypatch):
    outputs = iter(["not JSON",json.dumps(llm_task())])
    calls = []
    def chat(messages):
        calls.append(copy.deepcopy(messages))
        return next(outputs)
    monkeypatch.setattr(extraction,"_chat",chat)
    result = extraction.extract_task("Deadline next Friday")
    assert result.valid and len(calls) == 2
    validate(result.task,LLM_SCHEMA)
    assert "Invalid JSON:" in calls[1][-1]["content"]
    assert result.latency_s >= 0

def test_invalid_output_is_bounded(monkeypatch):
    calls = []
    monkeypatch.setattr(extraction,"_chat",lambda messages: calls.append(1) or "{}")
    result = extraction.extract_task("Announcement")
    assert not result.valid and len(calls) == 2

def test_connection_failure_and_empty_input(monkeypatch):
    def unavailable(messages):
        raise URLError("Ollama stopped")
    monkeypatch.setattr(extraction,"_chat",unavailable)
    assert not extraction.extract_task("Announcement").valid
    assert not extraction.extract_task("").valid
    assert not extraction.extract_task("x"*12001).valid

def test_pipeline_uses_python_date(monkeypatch):
    monkeypatch.delenv("PANUTO_STUB",raising=False)
    monkeypatch.setattr(pipeline,"extract_task",lambda *args: ExtractionResult(
        llm_task(),True,[],"",0.1))
    doc = ingest_text("Original",date(2026,10,12))
    result = pipeline.analyze(doc)
    assert result["task"]["deadline"] == "2026-10-23"
    assert result["task"]["needs_date_confirmation"]
    assert result["task"]["source_id"] == doc.source_id

def test_demo_refuses_stub(monkeypatch):
    monkeypatch.setenv("PANUTO_DEMO","1")
    monkeypatch.setenv("PANUTO_STUB","1")
    with pytest.raises(RuntimeError,match="refuses"):
        pipeline.analyze(ingest_text("Announcement"))

def test_manual_fallback(monkeypatch):
    monkeypatch.delenv("PANUTO_STUB",raising=False)
    monkeypatch.setattr(pipeline,"extract_task",lambda *args: ExtractionResult(
        None,False,["Unavailable"],"",0.1))
    result = pipeline.analyze(ingest_text("Original"))
    assert not result["valid"] and result["task"]["requirements"] == []

def test_deadline_hallucination_is_rejected(monkeypatch):
    monkeypatch.setattr(extraction,"_chat",lambda messages: json.dumps(llm_task(deadline_text="Oct 23")))
    result = extraction.extract_task("Deadline next Friday")
    assert not result.valid
    assert any("verbatim" in error for error in result.errors)

def test_invalid_time_is_rejected(monkeypatch):
    monkeypatch.setattr(extraction,"_chat",lambda messages: json.dumps(llm_task(deadline_time="25:00")))
    result = extraction.extract_task("Deadline next Friday at 25:00")
    assert not result.valid

def test_deadline_preserves_source_capitalization(monkeypatch):
    monkeypatch.setattr(extraction,"_chat",lambda messages: json.dumps(llm_task(deadline_text="next friday")))
    result = extraction.extract_task("Deadline next Friday")
    assert result.valid and result.task["deadline_text"] == "next Friday"

@pytest.mark.parametrize("clock,expected", [("11:59 PM","23:59"),("12:00 AM","00:00"),("12:00 PM","12:00")])
def test_explicit_clock_normalization(monkeypatch,clock,expected):
    monkeypatch.setattr(extraction,"_chat",lambda messages: json.dumps(llm_task(deadline_time=clock)))
    result = extraction.extract_task("Deadline next Friday at " + clock)
    assert result.valid and result.task["deadline_time"] == expected

def test_absent_clock_cannot_be_invented(monkeypatch):
    monkeypatch.setattr(extraction,"_chat",lambda messages: json.dumps(llm_task(deadline_time="23:00")))
    result = extraction.extract_task("Deadline next Friday")
    assert result.valid and result.task["deadline_time"] is None

def test_numeric_date_is_not_clock(monkeypatch):
    monkeypatch.setattr(extraction,"_chat",lambda messages: json.dumps(
        llm_task(deadline_text="10/16",deadline_time="10:16")))
    result = extraction.extract_task("Deadline 10/16")
    assert result.valid and result.task["deadline_time"] is None
