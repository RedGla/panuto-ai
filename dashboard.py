"""Offline task management and data recovery screens."""
import json
import sqlite3
import zipfile
from datetime import date
import streamlit as st
from jsonschema import ValidationError
import db
import ui
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
        submit = st.form_submit_button("Save task edits", type="primary", icon=":material/save:")
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


def reset_filters():
    for key, value in (("filter_subject", "All subjects"), ("filter_status", "All"),
                       ("filter_due", "All dates"), ("filter_archive", "Active"),
                       ("task_search", "")):
        st.session_state[key] = value


def render_dashboard():
    ui.notice("dashboard_notice")
    tasks, states = db.list_tasks(), db.get_states()
    active = filter_tasks(tasks, states)
    open_tasks = [task for task in active if task["status"] != "Done"]
    with st.container(key="summary_strip"):
        cols = st.columns(4)
        cols[0].metric("Open activities", len(open_tasks))
        cols[1].metric("Due today", sum(task["due_label"] == "Due today" for task in open_tasks))
        cols[2].metric("Overdue", sum(task["due_label"] == "Overdue" for task in open_tasks))
        cols[3].metric("Completed", sum(task["status"] == "Done" for task in active))
    if not tasks:
        main, aside = st.columns([1.8, 1], gap="large")
        with main, st.container(key="empty_workspace"):
            st.subheader("Your next clear step starts here.")
            st.write("Turn a class announcement into a task you can trust. Review the details, keep the source, and track every confirmed change.")
            st.button("Add your first announcement", type="primary", icon=":material/add:",
                      on_click=ui.navigate, args=("New announcement",))
            st.caption("No saved activities yet. Paste text, upload a screenshot, or enter a task manually.")
        with aside, st.container(key="focus_panel"):
            st.subheader("Made for the follow-up.")
            st.write("A deadline moved. A requirement changed. Another message arrived.")
            st.caption("Panuto puts the old and new instructions side by side. You choose which version to keep.")
        return
    main, aside = st.columns([2.3, 1], gap="large")
    with aside, st.container(key="focus_panel"):
        st.subheader("Up next")
        next_tasks = [item for item in open_tasks if item.get("deadline")]
        if next_tasks:
            first = next_tasks[0]
            st.text(first.get("activity") or "Untitled activity")
            st.caption(first.get("subject") or "Unknown subject")
            st.markdown("**" + date.fromisoformat(first["deadline"]).strftime("%A, %d %B") + "**")
            st.badge(first["due_label"], color=ui.STATUS_COLORS.get(first["due_label"], "green"),
                     icon=":material/schedule:")
        elif open_tasks:
            st.write("Your open activities need a deadline.")
            st.caption("Open activity details to confirm the date when you know it.")
        else:
            st.write("All active activities are done.")
            st.caption("A little breathing room. Your completed work is still below.")
        st.button("Add announcement", icon=":material/add:", width="stretch",
                  on_click=ui.navigate, args=("New announcement",))
    with main:
        st.subheader("Your activities")
        query = st.text_input("Search activities", placeholder="Search subject, activity, requirement, or note",
                              key="task_search", label_visibility="collapsed")
        with st.container(horizontal=True, vertical_alignment="center"):
            with st.popover("Filters", icon=":material/filter_list:"):
                subject = st.selectbox("Subject filter", ["All subjects"] + sorted({task.get("subject") or "Unknown subject" for task in tasks}), key="filter_subject")
                status = st.selectbox("Status filter", ["All"] + list(STATUSES), key="filter_status")
                due = st.selectbox("Due filter", ["All dates", "Overdue", "Due today", "Due this week", "Upcoming", "Date unknown", "Completed"], key="filter_due")
                archive = st.selectbox("Show activities", ["Active", "Archived", "All"], key="filter_archive")
                st.button("Reset filters", on_click=reset_filters, type="tertiary", icon=":material/filter_alt_off:")
            sort = st.selectbox("Sort by", ["Deadline", "Priority"], label_visibility="collapsed")
            compact = st.toggle("Compact view", key="compact_tasks")
        visible = filter_tasks(tasks, states, query, subject, status, due, archive, sort)
        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption(f"{len(visible)} of {len(tasks)} activities")
            with st.popover("Export", icon=":material/download:"):
                st.download_button("Export visible activities (CSV)", csv_export(visible), "panuto-tasks.csv", "text/csv", icon=":material/table_view:")
                st.download_button("Export visible deadlines (calendar)", calendar_export(visible), "panuto-deadlines.ics", "text/calendar", icon=":material/calendar_month:")
                st.caption("Calendar export includes open, dated activities. Times use your calendar's local timezone.")
        if not visible:
            st.info("No activities match these filters.", icon=":material/search_off:")
        pages = max(1, (len(visible) + 19) // 20)
        page = st.number_input("Page", min_value=1, max_value=pages, value=1, step=1, key=f"page_{pages}") if pages > 1 else 1
        for item in visible[(page - 1) * 20:page * 20]:
            task_id = item["id"]
            task = next(task for task in tasks if task["id"] == task_id)
            title = f"{item.get('subject') or 'Unknown subject'} — {item.get('activity') or 'Untitled'}"
            if not compact:
                ui.task_summary(item)
            with st.expander(title + " · " + item["due_label"], icon=":material/assignment:"):
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
                    saved = st.form_submit_button("Save organization", type="primary", icon=":material/check:")
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
    backup_tab, setup_tab = st.tabs(["Backup & recovery", "Local setup & help"])
    with backup_tab:
        st.subheader("Backup and recovery")
        st.write("Backups include activities, confirmed history, source text, available original files, and personal organization.")
        st.caption("Backups contain personal data. Store them somewhere you trust. Maximum ZIP size: 50 MB.")
        if st.button("Prepare backup", type="primary", icon=":material/backup:"):
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

    with setup_tab:
        st.subheader("Local setup")
        st.write("Start Ollama, download qwen3:1.7b, and install Tesseract with English and Filipino language data.")
        st.caption("Internet is needed for initial downloads and updates. Saved activities, OCR, extraction, and backups run locally.")
        if st.button("Check local setup", icon=":material/troubleshoot:"):
            from diagnostics import check_setup
            st.session_state["setup_checks"] = check_setup()
        for check in st.session_state.get("setup_checks", []):
            (st.success if check["ok"] else st.warning)(check["name"] + ": " + check["detail"])
        with st.expander("How to use Panuto"):
            st.write("Load an announcement, correct OCR text, then Analyze or Enter task manually. Review fields and confirm the deadline before saving.")
            st.write("Revisions suggest a matching activity. Inspect highlighted changes before choosing Use new. Dashboard keeps every confirmed version.")
            st.write("Use status and priority to organize work. Archive hides activities without deleting them. Search Archived activities to recover them.")
            st.write("One activity per announcement. AI and OCR can be wrong. Verify requirements against the original source.")
