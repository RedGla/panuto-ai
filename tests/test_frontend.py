"""Focused regressions for the redesigned workspace."""
from datetime import date
from streamlit.testing.v1 import AppTest
import db
from test_app import APP, element, navigate, review
from test_core import task
from ingestion import ingest_text


def manual_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PANUTO_STUB", raising=False)
    app = navigate(AppTest.from_file(str(APP)).run(), "New announcement")
    element(app.button, "Add task manually").click().run()
    return app


def test_review_survives_navigation_and_requires_fresh_confirmation(tmp_path, monkeypatch):
    app = manual_app(tmp_path, monkeypatch)
    element(app.text_input, "Subject").set_value("Physics")
    element(app.text_input, "Activity").set_value("Lab report")
    element(app.number_input, "Group size (0 means unspecified)").set_value(4)
    element(app.text_area, "Extra instructions").set_value("Include calculations")
    review(app, date(2026, 10, 23))
    navigate(app, "Dashboard")
    navigate(app, "New announcement")
    assert element(app.text_input, "Activity").value == "Lab report"
    assert element(app.number_input, "Group size (0 means unspecified)").value == 4
    assert element(app.text_area, "Extra instructions").value == "Include calculations"
    assert element(app.date_input, "Confirmed deadline (empty means unknown)").value == date(2026, 10, 23)
    assert not db.list_tasks()
    element(app.checkbox, "I reviewed the fields and deadline, including any unknown date.").check().run()
    element(app.text_input, "Activity").set_value("Updated lab report")
    review(app, date(2026, 10, 24))
    assert element(app.button, "Save as new activity").disabled
    element(app.checkbox, "I reviewed the fields and deadline, including any unknown date.").check().run()
    element(app.button, "Save as new activity").click().run()
    assert not app.exception
    assert db.list_tasks()[0]["activity"] == "Updated lab report"
    assert "source" not in app.session_state
    assert element(app.button, "View saved activities")


def test_switching_revision_target_requires_confirmation_again(tmp_path, monkeypatch):
    app = manual_app(tmp_path, monkeypatch)
    doc = ingest_text("Saved activity source")
    db.save_task(task(doc.source_id), doc)
    review(app, None)
    element(app.checkbox, "I reviewed the fields and deadline, including any unknown date.").check().run()
    element(app.selectbox, "Compare with saved activity").set_value(1).run()
    assert element(app.button, "Use new").disabled
    assert len(db.list_versions(1)) == 1


def test_discard_dialog_preserves_or_clears_only_unsaved_draft(tmp_path, monkeypatch):
    app = manual_app(tmp_path, monkeypatch)
    source_id = app.session_state["source"].source_id
    element(app.button, "Start another announcement").click().run()
    assert not app.exception
    element(app.button, "Keep working").click().run()
    assert app.session_state["source"].source_id == source_id
    element(app.button, "Start another announcement").click().run()
    element(app.button, "Discard draft").click().run()
    assert not app.exception
    assert "source" not in app.session_state
    assert element(app.text_area, "Announcement text").value == ""
    assert db.list_tasks() == []


def test_filter_reset_and_compact_view_keep_saved_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db.init_db()
    doc = ingest_text("Source")
    db.save_task(task(doc.source_id), doc)
    app = AppTest.from_file(str(APP)).run()
    element(app.text_input, "Search activities").set_value("nonexistent").run()
    assert any("No activities match" in item.value for item in app.info)
    element(app.button, "Reset filters").click().run()
    assert not app.info
    element(app.toggle, "Compact view").set_value(True).run()
    assert not app.exception
    assert any("ML" in item.label for item in app.expander)
    assert len(db.list_tasks()) == 1


def test_dynamic_html_is_escaped_and_diff_has_text_labels(monkeypatch):
    import ui
    from contracts import Change, Diff
    output = []
    monkeypatch.setattr(ui.st, "html", lambda value: output.append(value))
    ui.task_summary(dict(subject="<script>alert(1)</script>", activity="<img onerror=x>",
                         deadline=None, due_label="Date unknown"))
    ui.change_table(Diff([Change("submission_format", "<b>old</b>", "<img src=x>", "changed")], True))
    assert all("<script>" not in value and "<img " not in value for value in output)
    assert "&lt;script&gt;" in output[0]
    assert "Saved version" in output[1] and "New announcement" in output[1]
    assert "changed" in output[1]
