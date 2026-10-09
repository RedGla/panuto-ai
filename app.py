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

st.set_page_config(page_title="Panuto AI", page_icon="📋", layout="centered")
st.title("Panuto AI")
st.caption("Class announcements, clear tasks. Extraction and storage run on this computer.")
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
                st.image(doc.original_path)
            except Exception:
                st.caption("Original image could not be displayed.")

def reset_review(message):
    for key in ("analysis", "reviewed"):
        st.session_state.pop(key, None)
    st.session_state["notice"] = message
    st.rerun()

def render_review():
    result = st.session_state["analysis"]
    doc = st.session_state["source"]
    task = result["task"]
    source_view(doc)
    st.caption(f"Analysis took {result['latency_s']:.2f} seconds.")
    if not result["valid"]:
        st.error("Extraction failed. Enter the task manually.")
        for error in result["errors"]:
            st.caption(error)
    if task["needs_date_confirmation"]:
        st.warning(result["date_reason"])
    with st.form("review_" + doc.source_id):
        st.subheader("Review extracted fields")
        values = {}
        for field, label in (
            ("subject","Subject"), ("activity","Activity"),
            ("deadline_text","Deadline phrase"), ("deadline_time","Deadline time (HH:MM)"),
            ("submission_platform","Submission platform"), ("submission_format","Submission format")):
            values[field] = st.text_input(label, value=task.get(field) or "").strip() or None
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
        reviewed = st.form_submit_button("Review changes")
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
        except (ValidationError, ValueError, TypeError) as exc:
            st.session_state.pop("reviewed", None)
            st.error("Review fields are invalid: " + str(exc).split("\n")[0])
    prepared = st.session_state.get("reviewed")
    if not prepared:
        return
    st.subheader("Confirm reviewed task")
    st.caption("These are the values that will be saved. Submit Review changes again after editing.")
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
                          key="match_" + doc.source_id)
    if target is not None:
        diff = compare_tasks(lookup[target], prepared)
        if not diff.has_conflict:
            st.success("No changes in deadline, submission, group size, or requirements.")
        for change in diff.changes:
            text = f"{change.kind.upper()}: {change.field}\n{change.old}  →  {change.new}"
            {"changed":st.warning,"added":st.success,"removed":st.error}[change.kind](text)
    confirmed = st.checkbox("I reviewed the fields and deadline, including any unknown date.",
                            key="confirm_" + doc.source_id)
    col1, col2, col3 = st.columns(3)
    keep = col1.button("Keep old", disabled=target is None)
    replace = col2.button("Use new", disabled=target is None or not confirmed)
    save = col3.button("Save as new activity", disabled=not confirmed)
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

new_tab, dashboard, data_tools = st.tabs(["New announcement", "Dashboard", "Backup & setup"])
with new_tab:
    if st.session_state.get("notice"):
        st.success(st.session_state.pop("notice"))
    if st.button("Add task manually"):
        doc = ingest_text("Manually entered activity.")
        st.session_state["source"] = doc
        st.session_state.pop("reviewed", None)
        st.session_state["analysis"] = dict(task=blank_task(doc.source_id), valid=True,
            errors=[], latency_s=0, date_reason="Choose a deadline or leave it unknown.")
    with st.form("load_source"):
        mode = st.radio("Input", ["Paste text","Upload file"])
        text = st.text_area("Announcement text", height=150, max_chars=12000)
        upload = st.file_uploader("Screenshot or PDF", type=["png","jpg","jpeg","pdf"], help="Announcements: maximum 20 MB. Backups use a separate 50 MB limit.")
        posted = st.date_input("Announcement date", value=date.today())
        unknown_date = st.checkbox("Announcement date is unknown")
        load = st.form_submit_button("Load source")
    if load:
        posted = None if unknown_date else posted
        if mode == "Paste text":
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
                with st.spinner("Reading source locally…"):
                    doc = ingest_file(str(path), posted)
        st.session_state["source"] = doc
        st.session_state.pop("analysis", None)
        st.session_state.pop("reviewed", None)
    if "source" in st.session_state and "analysis" not in st.session_state:
        doc = st.session_state["source"]
        source_view(doc)
        corrected = st.text_area("Correct source text before analysis", value=doc.text,
                                 key="source_text_" + doc.source_id, max_chars=12000)
        if st.button("Enter task manually"):
            st.session_state["analysis"] = dict(task=blank_task(doc.source_id), valid=True,
                errors=[], latency_s=0, date_reason="Choose a deadline or leave it unknown.")
            st.session_state.pop("reviewed", None)
            st.rerun()
        if st.button("Analyze", disabled=not corrected.strip()):
            # Preserve original OCR/source text; extraction uses the student's corrected copy.
            from dataclasses import replace
            with st.spinner("Running locally — no cloud request…"):
                result = analyze(replace(doc, text=corrected))
            st.session_state["analysis"] = result
            st.rerun()
    if "analysis" in st.session_state:
        render_review()

with dashboard:
    try:
        render_dashboard()
    except (sqlite3.Error, OSError, ValueError) as exc:
        st.error(f"Dashboard could not load: {exc}")

with data_tools:
    render_data_tools()
