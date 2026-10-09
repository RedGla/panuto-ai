from datetime import date
from pathlib import Path
import db
import pipeline
from contracts import ExtractionResult
from streamlit.testing.v1 import AppTest
from test_core import llm_task

APP = Path(__file__).resolve().parents[1]/"app.py"

def element(items,label):
    return next(item for item in items if item.label == label)

def load(app,text):
    element(app.text_area,"Announcement text").set_value(text)
    element(app.date_input,"Announcement date").set_value(date(2026,10,12))
    element(app.button,"Load source").click().run()
    element(app.button,"Analyze").click().run()
    assert not app.exception
    return app

def review(app,deadline):
    element(app.date_input,"Confirmed deadline (empty means unknown)").set_value(deadline)
    element(app.button,"Review changes").click().run()
    assert not app.exception

def test_confirm_revision_and_restart(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PANUTO_STUB",raising=False)
    monkeypatch.delenv("PANUTO_DEMO",raising=False)
    output = llm_task()
    monkeypatch.setattr(pipeline,"extract_task",lambda *args: ExtractionResult(output,True,[],"",0.1))
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    load(app,"Original announcement")
    review(app,date(2026,10,16))
    assert db.list_tasks() == []
    assert element(app.button,"Save as new activity").disabled
    element(app.checkbox,"I reviewed the fields and deadline, including any unknown date.").check().run()
    element(app.button,"Save as new activity").click().run()
    assert not app.exception and len(db.list_tasks()) == 1
    output = llm_task(deadline_text="Oct 23",deadline_time="23:59",is_revision=True,
        requirements=[{"text":"dataset minimum 500 rows","number":500},
                      {"text":"include data dictionary","number":None}])
    load(app,"Revision announcement")
    review(app,date(2026,10,23))
    assert any("deadline" in item.value for item in app.warning)
    assert any("data dictionary" in item.value for item in app.success)
    element(app.checkbox,"I reviewed the fields and deadline, including any unknown date.").check().run()
    element(app.button,"Use new").click().run()
    assert not app.exception
    assert len(db.list_versions(1)) == 2
    restarted = AppTest.from_file(str(APP)).run()
    assert not restarted.exception
    assert db.get_task(1)["deadline"] == "2026-10-23"

def test_failure_manual_entry(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PANUTO_STUB",raising=False)
    monkeypatch.setattr(pipeline,"extract_task",lambda *args: ExtractionResult(None,False,["Stopped"],"",0.1))
    app = load(AppTest.from_file(str(APP)).run(),"Announcement")
    assert any("Extraction failed" in item.value for item in app.error)
    element(app.text_input,"Subject").set_value("Physics")
    element(app.text_input,"Activity").set_value("Lab report")
    review(app,None)
    element(app.checkbox,"I reviewed the fields and deadline, including any unknown date.").check().run()
    element(app.button,"Save as new activity").click().run()
    assert not app.exception
    assert db.list_tasks()[0]["deadline"] is None

def test_demo_stub_refusal(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PANUTO_DEMO","1")
    monkeypatch.setenv("PANUTO_STUB","1")
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert any("refuses" in item.value for item in app.error)

def test_stub_review_save(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PANUTO_STUB","1")
    monkeypatch.delenv("PANUTO_DEMO",raising=False)
    app = load(AppTest.from_file(str(APP)).run(),"Development announcement")
    assert any("DEVELOPMENT STUB" in item.value for item in app.warning)
    review(app,None)
    element(app.checkbox,"I reviewed the fields and deadline, including any unknown date.").check().run()
    element(app.button,"Save as new activity").click().run()
    assert not app.exception and len(db.list_tasks()) == 1
