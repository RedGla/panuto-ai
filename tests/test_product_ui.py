from datetime import date
import db
import pipeline
from streamlit.testing.v1 import AppTest
from test_app import APP, element, review, navigate
from test_core import task
from ingestion import ingest_text


def test_manual_entry_without_model_and_organization(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PANUTO_STUB", raising=False)
    def forbidden(*args):
        raise AssertionError("Manual entry must not call the model")
    monkeypatch.setattr(pipeline, "extract_task", forbidden)
    app = AppTest.from_file(str(APP)).run()
    navigate(app, "New announcement")
    element(app.button, "Add task manually").click().run()
    element(app.text_input, "Subject").set_value("Physics")
    element(app.text_input, "Activity").set_value("Lab report")
    review(app, date(2026,10,16))
    element(app.checkbox, "I reviewed the fields and deadline, including any unknown date.").check().run()
    element(app.button, "Save as new activity").click().run()
    assert not app.exception
    navigate(app, "Dashboard")
    element(app.selectbox, "Status").select("Done")
    element(app.selectbox, "Priority").select("High")
    element(app.text_area, "Personal notes").set_value("Review vectors")
    element(app.button, "Save organization").click().run()
    assert not app.exception
    assert db.get_states()[1]["status"] == "Done"
    assert len(db.list_versions(1)) == 1
    element(app.text_input, "Search activities").set_value("not present").run()
    assert any("No activities match" in item.value for item in app.info)
    element(app.text_input, "Search activities").set_value("vectors").run()
    assert any("Physics" in item.label for item in app.expander)
    navigate(app, "Backup & setup")
    element(app.button, "Prepare backup").click().run()
    assert not app.exception and app.session_state["backup_download"].startswith(b"PK")


def test_edit_confirm_archive_recover_and_restart(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    db.init_db()
    doc = ingest_text("Source announcement")
    db.save_task(task(doc.source_id), doc)
    app = AppTest.from_file(str(APP)).run()
    app.text_input(key="edit_activity_1").set_value("Edited activity")
    element(app.button, "Save task edits").click().run()
    assert len(db.list_versions(1)) == 1
    element(app.checkbox, "Confirm task edits").check()
    element(app.button, "Save task edits").click().run()
    assert not app.exception
    assert len(db.list_versions(1)) == 2 and db.get_task(1)["activity"] == "Edited activity"
    element(app.checkbox, "Archived").check()
    element(app.button, "Save organization").click().run()
    assert any("No activities match" in x.value for x in app.info)
    element(app.selectbox, "Show activities").select("Archived").run()
    element(app.checkbox, "Archived").uncheck()
    element(app.button, "Save organization").click().run()
    restarted = AppTest.from_file(str(APP)).run()
    assert not restarted.exception
    assert db.get_states()[1]["archived"] == 0
    assert any("Edited activity" in item.label for item in restarted.expander)

def test_backup_recovery_ui_requires_confirmation(tmp_path,monkeypatch):
    import backup
    import streamlit
    monkeypatch.chdir(tmp_path)
    db.init_db()
    doc = ingest_text("Original source")
    db.save_task(task(doc.source_id), doc)
    data = backup.create_backup()
    class Upload:
        def getvalue(self):
            return data
    monkeypatch.setattr(streamlit, "file_uploader",
                        lambda label, **kwargs: Upload() if label == "Recover a Panuto backup" else None)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    navigate(app, "Backup & setup")
    assert element(app.button, "Recover backup").disabled
    assert len(db.list_tasks()) == 1
    element(app.checkbox, "Add these backup activities to my data").check().run()
    element(app.button, "Recover backup").click().run()
    assert not app.exception
    assert len(db.list_tasks()) == 2
    assert any("Recovered 1" in item.value for item in app.success)


def test_unavailable_local_setup_preserves_dashboard(tmp_path,monkeypatch):
    import diagnostics
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(diagnostics, "check_setup", lambda: [
        dict(name="Local model", ok=False, detail="Start Ollama. Manual entry remains available.")])
    app = AppTest.from_file(str(APP)).run()
    navigate(app, "Backup & setup")
    element(app.button, "Check local setup").click().run()
    assert not app.exception
    assert any("Start Ollama" in item.value for item in app.warning)
    navigate(app, "New announcement")
    assert element(app.button, "Add task manually")
