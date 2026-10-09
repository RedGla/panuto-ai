"""Panuto AI: local announcement review and confirmed revision tracking."""
import json
import os
import re
import sqlite3
import tempfile
from datetime import date
from pathlib import Path
import streamlit as st
from jsonschema import validate, ValidationError
import db
from contracts import LLM_SCHEMA
from ingestion import ingest_file, ingest_text
from pipeline import analyze, blank_task
from dashboard import render_dashboard, render_data_tools
from compare import compare_tasks, find_matches

import ui

st.set_page_config(page_title="Panuto AI", page_icon=":material/school:", layout="wide",
                   initial_sidebar_state="auto")
ui.styles()
if os.getenv("PANUTO_DEMO") == "1" and os.getenv("PANUTO_STUB") == "1":
    st.error("Demo mode refuses development stubs. Unset PANUTO_STUB and restart.")
    st.stop()
if os.getenv("PANUTO_STUB") == "1":
    st.warning("DEVELOPMENT STUB — no model inference. Do not use for the demo.")
try:
    db.init_db()
except (sqlite3.Error, OSError) as exc:
    st.error(f"Cannot open local storage: {exc}")
    st.stop()

def source_view(doc):
    for warning in doc.warnings:
        st.warning(warning)
    if doc.ocr_confidence is not None:
        st.caption(f"OCR confidence: {doc.ocr_confidence:.1f}/100")
    with st.expander("Original source"):
        st.text(doc.text)
        if doc.original_path and doc.kind == "image":
            try:
                st.image(doc.original_path, alt="Original announcement screenshot")
            except Exception:
                st.caption("Original image could not be displayed.")

def reset_review(message):
    clear_draft()
    st.session_state["notice"] = message
    st.rerun()

def render_review():
    result = st.session_state["analysis"]
    doc = st.session_state["source"]
    task = st.session_state.get("reviewed") or result["task"]
    source_view(doc)
    st.caption(f"Ready to review · {result['latency_s']:.2f}s processing time. Nothing is saved yet.")
    if not result["valid"]:
        st.error("Extraction failed. Enter the task manually.")
        for error in result["errors"]:
            st.caption(error)
    if task["needs_date_confirmation"]:
        st.warning(result["date_reason"])
    with st.expander("Edit extracted fields", expanded="reviewed" not in st.session_state, icon=":material/edit_note:"):
        with st.form("review_" + doc.source_id, border=False):
            st.subheader("Review extracted fields")
            st.caption("Select Review changes to keep your edits when switching workspace views.")
            values = {}
            fields = (
                ("subject","Subject"), ("activity","Activity"),
                ("deadline_text","Deadline phrase"), ("deadline_time","Deadline time (HH:MM)"),
                ("submission_platform","Submission platform"), ("submission_format","Submission format"))
            columns = st.columns(2)
            for index, (field, label) in enumerate(fields):
                values[field] = columns[index % 2].text_input(
                    label, value=task.get(field) or "", key=f"review_{field}_{doc.source_id}",
                    persist_state="session").strip() or None
            group = st.number_input("Group size (0 means unspecified)", min_value=0, step=1,
                                    value=max(0, task.get("group_size") or 0))
            values["group_size"] = group or None
            # Editable numeric quantity stays separate from each requirement's wording.
            requirements = st.data_editor(task.get("requirements") or [{"text":"","number":None}],
                column_order=["text","number"], num_rows="dynamic", key="requirements_" + doc.source_id,
                column_config={"text":st.column_config.TextColumn("Requirement", required=True),
                               "number":st.column_config.NumberColumn("Quantity", step=1)},
                width="stretch")
            values["extra_instructions"] = st.text_area(
                "Extra instructions", value=task.get("extra_instructions") or "").strip() or None
            values["is_revision"] = st.checkbox("This is a revision", value=task["is_revision"])
            resolved = date.fromisoformat(task["deadline"]) if task.get("deadline") else None
            chosen = st.date_input("Confirmed deadline (empty means unknown)", value=resolved)
            reviewed = st.form_submit_button("Review changes", type="primary", icon=":material/arrow_forward:")
    if reviewed:
        try:
            values["requirements"] = [
                {"text":str(item.get("text") or "").strip(), "number":item.get("number")}
                for item in requirements if str(item.get("text") or "").strip()]
            validate(values, LLM_SCHEMA)
            if values["deadline_time"] and not re.fullmatch(
                    r"(?:[01]\d|2[0-3]):[0-5]\d", values["deadline_time"]):
                raise ValueError("Time must use 24-hour HH:MM, for example 23:59.")
            values.update(deadline=chosen.isoformat() if chosen else None,
                          needs_date_confirmation=chosen is None, source_id=doc.source_id)
            st.session_state["reviewed"] = values
            st.session_state["confirm_" + doc.source_id] = False
            st.rerun()
        except (ValidationError, ValueError, TypeError) as exc:
            st.session_state.pop("reviewed", None)
            st.error("Review fields are invalid: " + str(exc).split("\n")[0])
    prepared = st.session_state.get("reviewed")
    if not prepared:
        return
    st.subheader("Confirm reviewed task")
    st.caption("These are the values that will be saved. Submit Review changes again after editing.")
    ui.review_summary(prepared)
    with st.expander("All reviewed values", icon=":material/data_object:"):
        st.json(prepared, expanded=False)
    saved = db.list_tasks()
    suggestions = find_matches(prepared, saved)
    suggested_ids = [task_id for task_id, _ in suggestions]
    choices = [None] + suggested_ids + [item["id"] for item in saved if item["id"] not in suggested_ids]
    lookup = {item["id"]:item for item in saved}
    def label(task_id):
        if task_id is None:
            return "New activity"
        item = lookup[task_id]
        return f"{item.get('subject') or 'Unknown subject'} — {item.get('activity') or 'Untitled'} (#{task_id})"
    if suggestions:
        best, score = suggestions[0]
        st.info(f"This looks like {lookup[best].get('activity') or 'a saved activity'} "
                f"({score:.0%} similarity). Same activity? You choose.")
    target = st.selectbox("Compare with saved activity", choices,
                          index=1 if suggestions else 0, format_func=label,
                          key="match_" + doc.source_id, on_change=ui.clear_confirmation,
                          args=("confirm_" + doc.source_id,))
    if target is not None:
        diff = compare_tasks(lookup[target], prepared)
        if not diff.has_conflict:
            st.success("No changes in deadline, submission, group size, or requirements.")
        if diff.has_conflict:
            ui.change_table(diff)
            st.warning("Instructions changed. Compare the saved and new values before choosing Use new.",
                       icon=":material/compare_arrows:")
    confirmed = st.checkbox("I reviewed the fields and deadline, including any unknown date.",
                            key="confirm_" + doc.source_id)
    col1, col2, col3 = st.columns(3)
    keep = col1.button("Keep old", disabled=target is None)
    replace = col2.button("Use new", disabled=target is None or not confirmed,
                          type="primary" if target is not None else "secondary")
    save = col3.button("Save as new activity", disabled=not confirmed, type="primary" if target is None else "secondary", icon=":material/check:")
    if keep:
        reset_review("Kept the saved version.")
    try:
        if replace:
            db.add_version(target, prepared, doc)
            reset_review("Saved a confirmed revision.")
        if save:
            db.save_task(prepared, doc)
            reset_review("Saved a new activity.")
    except (sqlite3.Error, OSError, ValueError, KeyError) as exc:
        st.error(f"Save failed. Review stays available: {exc}")


def clear_draft():
    doc = st.session_state.get("source")
    source_id = doc.source_id if doc else None
    for key in list(st.session_state):
        if key in ("source", "analysis", "reviewed", "announcement_draft") or (
                source_id and key.endswith(source_id)):
            st.session_state.pop(key, None)


@st.dialog("Start another announcement?", icon=":material/restart_alt:")
def discard_draft():
    st.write("This clears the current source and unsaved review. Your saved activities and history stay available.")
    left, right = st.columns(2)
    if left.button("Keep working", width="stretch"):
        st.rerun()
    if right.button("Discard draft", type="primary", width="stretch", on_click=clear_draft):
        st.rerun()


def manual_entry():
    doc = ingest_text("Manually entered activity.")
    st.session_state["source"] = doc
    st.session_state.pop("reviewed", None)
    st.session_state["analysis"] = dict(task=blank_task(doc.source_id), valid=True,
        errors=[], latency_s=0, date_reason="Choose a deadline or leave it unknown.")


def render_capture():
    ui.header("From announcement to action.",
              "Paste it. Check it. Know exactly what to submit.")
    if st.session_state.get("notice"):
        ui.notice("notice")
        st.button("View saved activities", icon=":material/arrow_forward:",
                  on_click=ui.navigate, args=("Dashboard",))
    ui.stepper()
    if "source" not in st.session_state:
        main, guide = st.columns([2.1, 1], gap="large")
        with main, st.container(key="capture_panel"):
            st.subheader("Add an announcement")
            mode = st.segmented_control("Input", ["Paste text", "Upload file"],
                                        default="Paste text", key="input_mode",
                                        selection_mode="single")
            with st.form("load_source", border=False):
                text = ""
                upload = None
                if mode != "Upload file":
                    text = st.text_area("Announcement text", height=200, max_chars=12000,
                        key="announcement_draft", persist_state="session",
                        placeholder="Paste your class announcement here. Filipino, Taglish, and English are welcome.")
                else:
                    upload = st.file_uploader("Screenshot or PDF", type=["png", "jpg", "jpeg", "pdf"],
                        max_upload_size=20, help="One announcement at a time. Maximum 20 MB.")
                left, right = st.columns(2)
                posted = left.date_input("Announcement date", value=date.today(),
                    help="The date the message was posted, used to interpret relative deadlines.")
                unknown_date = right.checkbox("Announcement date is unknown")
                load = st.form_submit_button("Load source", type="primary",
                                             icon=":material/arrow_forward:", width="stretch")
            if load:
                posted = None if unknown_date else posted
                if mode != "Upload file":
                    doc = ingest_text(text, posted)
                elif upload is None:
                    doc = ingest_text("", posted)
                    doc.warnings.append("Select a file first.")
                elif upload.size > 20 * 1024 * 1024:
                    doc = ingest_text("", posted)
                    doc.warnings.append("File exceeds the 20 MB limit.")
                else:
                    with tempfile.TemporaryDirectory() as folder:
                        path = Path(folder) / ("upload" + Path(upload.name).suffix.lower())
                        path.write_bytes(upload.getvalue())
                        with st.spinner("Reading source on your laptop…", show_time=True):
                            doc = ingest_file(str(path), posted)
                st.session_state["source"] = doc
                st.session_state.pop("analysis", None)
                st.session_state.pop("reviewed", None)
                st.rerun()
            st.button("Add task manually", icon=":material/edit_note:", type="tertiary",
                      on_click=manual_entry)
        with guide, st.container(key="capture_help"):
            st.markdown("### New message. Same activity?")
            st.write("Add the updated announcement just like the original. Panuto will suggest a match and show what changed.")
            st.markdown("**You decide what stays.**")
            st.caption("Nothing overwrites your saved instructions without your confirmation.")
            with st.expander("For a clearer result", icon=":material/lightbulb:"):
                st.write("Use one activity per announcement. Keep the subject, deadline, and requirements together.")
                st.write("For screenshots, include the full message and avoid cropped or blurry text.")
            st.caption(":material/laptop: Processed locally after setup.")
    else:
        if st.button("Start another announcement", icon=":material/restart_alt:",
                  type="tertiary"):
            discard_draft()
        if "analysis" not in st.session_state:
            doc = st.session_state["source"]
            st.subheader("Check the source")
            st.caption("Correct any OCR mistakes before analysis. The original stays in your history.")
            source_view(doc)
            corrected = st.text_area("Correct source text before analysis", value=doc.text,
                key="source_text_" + doc.source_id, max_chars=12000, height=230,
                persist_state="session")
            with st.container(horizontal=True):
                analyze_clicked = st.button("Analyze", disabled=not corrected.strip(),
                                            type="primary", icon=":material/auto_awesome:")
                manual_clicked = st.button("Enter task manually", icon=":material/edit_note:")
            if manual_clicked:
                st.session_state["analysis"] = dict(task=blank_task(doc.source_id), valid=True,
                    errors=[], latency_s=0, date_reason="Choose a deadline or leave it unknown.")
                st.session_state.pop("reviewed", None)
                st.rerun()
            if analyze_clicked:
                from dataclasses import replace
                with st.spinner("Analyzing on your laptop. This can take a moment…", show_time=True):
                    result = analyze(replace(doc, text=corrected))
                st.session_state["analysis"] = result
                st.rerun()
        if "analysis" in st.session_state:
            render_review()


try:
    tasks, states = db.list_tasks(), db.get_states()
    page = ui.sidebar(tasks, states)
    if page == "New announcement":
        render_capture()
    elif page == "Backup & setup":
        ui.header("A safe place for your work.", "Back up your activities. Recover a copy. Check your local setup.")
        render_data_tools()
    else:
        ui.header("Your week, in focus.", "Less chasing announcements. More time for the work.", tasks, states)
        render_dashboard()
except (sqlite3.Error, OSError, ValueError) as exc:
    st.error(f"Workspace could not load: {exc}")
