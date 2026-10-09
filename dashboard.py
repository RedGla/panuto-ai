"""Offline task management and data recovery screens."""
import json
import sqlite3
import zipfile
from datetime import date
import streamlit as st
from jsonschema import ValidationError
import db
from backup import create_backup, inspect_backup, restore_backup
from organizer import STATUSES, PRIORITIES, DEFAULT_STATE, filter_tasks, csv_export, calendar_export
from validation import validate_task


def edit_saved(task):
    task_id = task["id"]
    with st.form(f"edit_saved_{task_id}"):
        st.caption("Edit confirmed instructions. Saving adds a version and preserves the announcement source.")
        values = {}
        for field, label in (("subject", "Subject"), ("activity", "Activity"),
                             ("deadline_text", "Deadline phrase"), ("deadline_time", "Deadline time (HH:MM)"),
                             ("submission_platform", "Submission platform"), ("submission_format", "Submission format")):
            values[field] = st.text_input(label, task.get(field) or "", key=f"edit_{field}_{task_id}").strip() or None
        chosen = st.date_input("Confirmed deadline", value=date.fromisoformat(task["deadline"]) if task.get("deadline") else None,
                               key=f"edit_deadline_{task_id}")
        group = st.number_input("Group size (0 means unspecified)", min_value=0, step=1,
                                value=task.get("group_size") or 0, key=f"edit_group_{task_id}")
        values["group_size"] = group or None
        requirements = st.data_editor(task.get("requirements") or [{"text": "", "number": None}],
                                       num_rows="dynamic", key=f"edit_requirements_{task_id}",
                                       column_config={"number": st.column_config.NumberColumn("Quantity", step=1)})
        values["extra_instructions"] = st.text_area("Extra instructions", task.get("extra_instructions") or "",
                                                  key=f"edit_extra_{task_id}").strip() or None
        values["is_revision"] = st.checkbox("This is a revision", value=task["is_revision"], key=f"edit_revision_{task_id}")
        confirm = st.checkbox("Confirm task edits", key=f"edit_confirm_{task_id}")
        submit = st.form_submit_button("Save task edits")
    if submit:
        if not confirm:
            st.warning("Confirm task edits before saving.")
            return
        try:
            values["requirements"] = [{"text": str(row.get("text") or "").strip(), "number": row.get("number")}
                                      for row in requirements if str(row.get("text") or "").strip()]
            values.update(source_id=task["source_id"], deadline=chosen.isoformat() if chosen else None,
                          needs_date_confirmation=chosen is None)
            db.update_task(task_id, validate_task(values))
            st.session_state["dashboard_notice"] = "Task edits saved as a new version."
            st.rerun()
        except (sqlite3.Error, ValueError, TypeError, ValidationError) as exc:
            st.error("Could not save edits: " + str(exc).split("\n")[0])


def render_dashboard():
    if st.session_state.get("dashboard_notice"):
        st.success(st.session_state.pop("dashboard_notice"))
    tasks, states = db.list_tasks(), db.get_states()
    active = filter_tasks(tasks, states)
    open_tasks = [task for task in active if task["status"] != "Done"]
    cols = st.columns(3)
    cols[0].metric("Open activities", len(open_tasks))
    cols[1].metric("Overdue", sum(task["due_label"] == "Overdue" for task in open_tasks))
    cols[2].metric("Due today", sum(task["due_label"] == "Due today" for task in open_tasks))
    st.caption("Due indicators update while the app is open. Calendar export can support reminders in your calendar app.")
    if not tasks:
        st.info("No saved activities yet. Review and confirm an announcement to start.")
        return
    query = st.text_input("Search activities", placeholder="Subject, activity, requirement, or personal note")
    cols = st.columns(3)
    subject = cols[0].selectbox("Subject filter", ["All subjects"] + sorted({task.get("subject") or "Unknown subject" for task in tasks}))
    status = cols[1].selectbox("Status filter", ["All"] + list(STATUSES))
    due = cols[2].selectbox("Due filter", ["All dates", "Overdue", "Due today", "Due this week", "Upcoming", "Date unknown", "Completed"])
    cols = st.columns(2)
    archive = cols[0].selectbox("Show activities", ["Active", "Archived", "All"])
    sort = cols[1].selectbox("Sort by", ["Deadline", "Priority"])
    visible = filter_tasks(tasks, states, query, subject, status, due, archive, sort)
    st.caption(f"{len(visible)} of {len(tasks)} activities")
    cols = st.columns(2)
    cols[0].download_button("Export visible activities (CSV)", csv_export(visible), "panuto-tasks.csv", "text/csv")
    cols[1].download_button("Export visible deadlines (calendar)", calendar_export(visible), "panuto-deadlines.ics", "text/calendar")
    st.caption("Calendar export includes open, dated activities. Times use your calendar's local timezone.")
    if not visible:
        st.info("No activities match these filters.")
    # Keep history and editing bounded per render; filters can narrow large collections.
    pages = max(1, (len(visible) + 19) // 20)
    page = st.number_input("Page", min_value=1, max_value=pages, value=1, step=1, key=f"page_{pages}")
    for item in visible[(page - 1) * 20:page * 20]:
        task_id = item["id"]
        task = next(task for task in tasks if task["id"] == task_id)
        title = f"{item.get('subject') or 'Unknown subject'} — {item.get('activity') or 'Untitled'}"
        with st.expander(title + " · " + item["due_label"]):
            st.caption(f"{item['status']} · {item['priority']} priority · " + (item.get("deadline") or "Deadline unknown") +
                       (" " + item["deadline_time"] if item.get("deadline_time") else ""))
            st.write("Submission: " + " · ".join(str(item.get(key) or "Unspecified") for key in
                                               ("submission_format", "submission_platform")))
            if item.get("group_size"):
                st.write(f"Group size: {item['group_size']}")
            for requirement in item.get("requirements", []):
                st.write("• " + requirement["text"])
            if item.get("extra_instructions"):
                st.write(item["extra_instructions"])
            with st.form(f"organize_{task_id}"):
                status_value = st.selectbox("Status", STATUSES, index=STATUSES.index(item["status"]), key=f"status_{task_id}")
                priority = st.selectbox("Priority", PRIORITIES, index=PRIORITIES.index(item["priority"]), key=f"priority_{task_id}")
                notes = st.text_area("Personal notes", item["notes"], max_chars=5000, key=f"notes_{task_id}")
                archived = st.checkbox("Archived", value=item["archived"], key=f"archived_{task_id}",
                                       help="Hide this activity from the active list. Uncheck to recover it.")
                saved = st.form_submit_button("Save organization")
            if saved:
                try:
                    db.set_state(task_id, status_value, priority, notes, archived)
                    st.session_state["dashboard_notice"] = "Organization saved."
                    st.rerun()
                except (sqlite3.Error, ValueError, KeyError) as exc:
                    st.error(f"Could not save organization: {exc}")
            with st.expander("Edit saved instructions"):
                edit_saved(task)
            st.subheader("Version history")
            for version in reversed(db.list_versions(task_id)):
                st.caption(f"Version {version['version']} · {version['created_at']} UTC")
                st.json(version["task"], expanded=False)
                st.text(version["source_text"])


def render_data_tools():
    st.subheader("Backup and recovery")
    st.write("Backups include activities, confirmed history, source text, available original files, and personal organization.")
    st.caption("Backups contain personal data. Store them somewhere you trust. Maximum ZIP size: 50 MB.")
    if st.button("Prepare backup"):
        try:
            st.session_state["backup_download"] = create_backup()
        except (ValueError, OSError, sqlite3.Error, ValidationError) as exc:
            st.error(f"Could not prepare backup: {exc}")
    if "backup_download" in st.session_state:
        st.download_button("Download prepared backup", st.session_state["backup_download"],
                           f"panuto-backup-{date.today().isoformat()}.zip", "application/zip")
        st.caption("This is a snapshot from when you clicked Prepare backup. Prepare again after changing activities.")
    upload = st.file_uploader("Recover a Panuto backup", type=["zip"], key="backup_upload")
    if upload:
        try:
            data = upload.getvalue()
            snapshot = inspect_backup(data)
            st.info(f"Backup contains {len(snapshot['tasks'])} activities. Recovery adds copies and preserves existing activities.")
            confirm = st.checkbox("Add these backup activities to my data", key="confirm_restore_" + str(hash(data)))
            if st.button("Recover backup", disabled=not confirm):
                count = restore_backup(data)
                st.session_state.pop("backup_download", None)
                st.session_state["dashboard_notice"] = f"Recovered {count} activities. Existing activities are preserved."
                st.success(f"Recovered {count} activities. Open Dashboard to review them.")
        except (ValueError, TypeError, KeyError, OSError, sqlite3.Error, ValidationError,
                zipfile.BadZipFile, RuntimeError, json.JSONDecodeError) as exc:
            st.error("Backup was not recovered: " + str(exc).split("\n")[0])
    st.divider()
    st.subheader("Local setup")
    st.write("Start Ollama, download qwen3:1.7b, and install Tesseract with English and Filipino language data.")
    st.caption("Internet is needed for initial downloads and updates. Saved activities, OCR, extraction, and backups run locally.")
    if st.button("Check local setup"):
        from diagnostics import check_setup
        st.session_state["setup_checks"] = check_setup()
    for check in st.session_state.get("setup_checks", []):
        (st.success if check["ok"] else st.warning)(check["name"] + ": " + check["detail"])
    with st.expander("How to use Panuto"):
        st.write("Load an announcement, correct OCR text, then Analyze or Enter task manually. Review fields and confirm the deadline before saving.")
        st.write("Revisions suggest a matching activity. Inspect highlighted changes before choosing Use new. Dashboard keeps every confirmed version.")
        st.write("Use status and priority to organize work. Archive hides activities without deleting them. Search Archived activities to recover them.")
        st.write("One activity per announcement. AI and OCR can be wrong. Verify requirements against the original source.")
