"""Shared presentation for the local Panuto workspace.

Native widgets own interactions and accessibility. HTML is limited to escaped,
read-only summaries; styles add the requested layout and restrained motion.
"""
from datetime import date
from html import escape
from pathlib import Path
import streamlit as st
from organizer import filter_tasks

ROOT = Path(__file__).resolve().parent
PAGES = {"Dashboard": "space_dashboard", "New announcement": "add_comment",
         "Backup & setup": "settings"}
STATUS_COLORS = {"Overdue": "red", "Due today": "orange",
                 "Date unknown": "orange", "Completed": "green"}


def text(value):
    return escape(str(value if value is not None else "Not specified"))


def styles():
    st.html(ROOT / "ui.css")


def navigate(page):
    st.session_state["workspace"] = page


def clear_confirmation(key):
    st.session_state[key] = False


def notice(key):
    message = st.session_state.pop(key, None)
    if message:
        st.success(message, icon=":material/check_circle:")
        st.toast(message, icon=":material/check_circle:")


def sidebar(tasks, states):
    st.session_state.setdefault("workspace", "Dashboard")
    with st.sidebar:
        st.html('<div class="brand"><span class="brand-mark" aria-hidden="true">p.</span>'
                '<div><strong>panuto<span>ai</span></strong><small>A little more clarity.</small></div></div>')
        st.button("Capture announcement", icon=":material/add:", width="stretch",
                  key="quick_capture", on_click=navigate, args=("New announcement",),
                  type="primary")
        st.caption("Workspace")
        for page, icon in PAGES.items():
            st.button(page, key="nav_" + icon, icon=f":material/{icon}:",
                      width="stretch", type="secondary" if
                      st.session_state["workspace"] == page else "tertiary",
                      on_click=navigate, args=(page,))
        active = filter_tasks(tasks, states)
        done = sum(item["status"] == "Done" for item in active)
        with st.container(key="sidebar_progress"):
            st.markdown("**One task at a time.**")
            st.caption(f"{done} of {len(active)} active activities completed")
            st.progress(done / len(active) if active else 0)
        with st.popover("How Panuto works", icon=":material/help_outline:", width="stretch"):
            st.markdown("**Capture. Check. Keep track.**")
            st.write("Paste an announcement or upload a screenshot or PDF. Check the source, review the fields, then confirm.")
            st.write("A revision never replaces a saved activity until you choose Use new.")
            st.caption("One activity per announcement. AI and OCR can make mistakes.")
        with st.container(key="local_note"):
            st.markdown(":material/laptop: **On your laptop**")
            st.caption("Your sources and activities stay here. Processing works offline after setup.")
    return st.session_state["workspace"]


def header(title, subtitle, tasks=None, states=None):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption("My workspace / " + st.session_state.get("workspace", "Dashboard"))
        st.caption(date.today().strftime("%A, %d %B %Y"))
        if tasks is not None:
            active = filter_tasks(tasks, states or {})
            attention = [item for item in active if item["status"] != "Done"
                         and item["due_label"] in ("Overdue", "Due today", "Date unknown")]
            with st.popover(f"Attention · {len(attention)}", icon=":material/notifications:",
                            help="Deadline notices from your saved activities"):
                st.markdown("**Needs your attention**")
                if not attention:
                    st.caption("No overdue, due-today, or undated activities.")
                for item in attention[:8]:
                    st.text(item.get("activity") or "Untitled activity")
                    st.caption((item.get("subject") or "Unknown subject") + " · " + item["due_label"])
                if len(attention) > 8:
                    st.caption(f"{len(attention) - 8} more. Use the deadline filter in Dashboard.")
                st.caption("Notices refresh on interaction. Calendar reminders require an exported calendar.")
    st.title(title)
    st.caption(subtitle)


def stepper():
    current = 3 if "reviewed" in st.session_state else 2 if "analysis" in st.session_state else 1 if "source" in st.session_state else 0
    labels = ("Capture", "Check source", "Review fields", "Confirm")
    steps = []
    for i, label in enumerate(labels):
        state = "current" if i == current else "complete" if i < current else ""
        aria = ' aria-current="step"' if i == current else ""
        steps.append(f'<li class="{state}"{aria}><span>{i + 1}</span>{label}</li>')
    st.html('<ol class="steps" aria-label="Announcement progress">' + "".join(steps) + '</ol>')



def task_summary(task, *, compact=False):
    subject = text(task.get("subject") or "Unknown subject")
    activity = text(task.get("activity") or "Untitled activity")
    deadline = task.get("deadline")
    when = date.fromisoformat(deadline).strftime("%d %b") if deadline else "Unconfirmed"
    clock = (" · " + text(task["deadline_time"])) if task.get("deadline_time") else ""
    due = task.get("due_label", "Date unknown" if not deadline else "Confirmed")
    tone = "urgent" if due == "Overdue" else "pending" if due in ("Due today", "Date unknown") else "calm"
    status = text(task.get("status", "To do"))
    priority = f'<span class="tag priority">High priority</span>' if task.get("priority") == "High" else ""
    st.html(f'<article class="task-summary {"compact" if compact else ""}">'
            f'<div class="task-copy"><span class="subject">{subject}</span>'
            f'<h3>{activity}</h3><div class="task-tags"><span class="tag">{status}</span>'
            f'{priority}<span class="tag {tone}">{text(due)}</span></div></div>'
            f'<div class="task-date"><strong>{text(when)}</strong><small>{clock.lstrip(" ·") or "Deadline"}</small></div>'
            '</article>')


def review_summary(task):
    st.html('<div class="review-summary"><h3>' + text(task.get("activity") or "Untitled activity") +
            '</h3><p>' + text(task.get("subject") or "Unknown subject") + '</p>'
            '<dl><div><dt>Deadline</dt><dd>' + text(task.get("deadline") or "Unknown — confirm with your teacher") +
            (' · ' + text(task["deadline_time"]) if task.get("deadline_time") else '') + '</dd></div>'
            '<div><dt>Submit</dt><dd>' + text(task.get("submission_format") or "Unspecified format") +
            ' · ' + text(task.get("submission_platform") or "Unspecified platform") + '</dd></div>'
            '<div><dt>Group size</dt><dd>' + text(task.get("group_size") or "Not specified") +
            '</dd></div></dl></div>')
    for requirement in task.get("requirements", []):
        st.text("• " + requirement["text"])
    if task.get("extra_instructions"):
        st.text(task["extra_instructions"])


def change_value(value):
    if isinstance(value, dict):
        wording = text(value.get("text") or "Requirement")
        quantity = value.get("number")
        return wording + (f" · Quantity: {text(quantity)}" if quantity is not None else "")
    return text(value)


def change_table(diff):
    labels = {"deadline": "Deadline", "deadline_time": "Time", "group_size": "Group size",
              "submission_format": "Format", "submission_platform": "Platform"}
    rows = []
    for change in diff.changes:
        label = labels.get(change.field, change.field.replace("requirements:", "Requirement: "))
        rows.append(f'<tr class="{text(change.kind)}"><th scope="row">{text(label)}'
                    f'<span class="change-kind">{text(change.kind)}</span></th>'
                    f'<td>{change_value(change.old)}</td><td>{change_value(change.new)}</td></tr>')
    st.html('<div class="comparison" role="region" aria-label="Instruction changes" tabindex="0"><table><caption>What changed</caption><thead><tr>'
            '<th scope="col">Field</th><th scope="col">Saved version</th><th scope="col">New announcement</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')
