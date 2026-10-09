"""Personal task organization and portable exports; no model or network calls."""
import csv
import io
import re
from datetime import date, datetime, timedelta, timezone

STATUSES = ("To do", "In progress", "Done")
PRIORITIES = ("Low", "Normal", "High")
DEFAULT_STATE = dict(status="To do", priority="Normal", notes="", archived=False)


def validate_state(state):
    if not isinstance(state, dict):
        raise ValueError("Invalid task organization data.")
    result = {key: state.get(key, value) for key, value in DEFAULT_STATE.items()}
    if result["status"] not in STATUSES or result["priority"] not in PRIORITIES:
        raise ValueError("Invalid task status or priority.")
    if not isinstance(result["notes"], str) or len(result["notes"]) > 5000:
        raise ValueError("Notes must be text with at most 5,000 characters.")
    if type(result["archived"]) is not bool:
        raise ValueError("Invalid archive state.")
    return result


def due_label(task, today=None):
    today = today or date.today()
    if task.get("status") == "Done":
        return "Completed"
    if not task.get("deadline"):
        return "Date unknown"
    deadline = date.fromisoformat(task["deadline"])
    if deadline < today:
        return "Overdue"
    if deadline == today:
        return "Due today"
    if deadline <= today + timedelta(days=7):
        return "Due this week"
    return "Upcoming"


def filter_tasks(tasks, states, query="", subject="All subjects", status="All",
                 due="All dates", archive="Active", sort="Deadline", today=None):
    result = []
    for task in tasks:
        item = dict(task, **{key: states.get(task["id"], {}).get(key, value)
                            for key, value in DEFAULT_STATE.items()})
        item["due_label"] = due_label(item, today)
        if archive == "Active" and item["archived"] or archive == "Archived" and not item["archived"]:
            continue
        if subject != "All subjects" and (item.get("subject") or "Unknown subject") != subject:
            continue
        if status != "All" and item["status"] != status:
            continue
        if due != "All dates" and item["due_label"] != due:
            continue
        haystack = " ".join(str(item.get(key) or "") for key in
                            ("subject", "activity", "extra_instructions", "notes"))
        haystack += " " + " ".join(req["text"] for req in item.get("requirements", []))
        if query.strip().casefold() not in haystack.casefold():
            continue
        result.append(item)
    if sort == "Priority":
        result.sort(key=lambda item: (-PRIORITIES.index(item["priority"]),
                                     item.get("deadline") or "9999-12-31", item["id"]))
    else:
        result.sort(key=lambda item: (item.get("deadline") is None,
                                     item.get("deadline") or "", item["id"]))
    return result


def csv_export(tasks):
    output = io.StringIO(newline="")
    fields = ("subject", "activity", "deadline", "deadline_time", "status", "priority",
              "submission_platform", "submission_format", "group_size", "requirements", "notes")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for task in tasks:
        row = {key: task.get(key) for key in fields}
        row["requirements"] = "; ".join(req["text"] for req in task.get("requirements", []))
        # Neutralize spreadsheet formulas in student-supplied text.
        for key, value in row.items():
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                row[key] = "'" + value
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")


def _ical_text(value):
    return str(value or "").replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace(
        "\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def _fold(line):
    chunks, current = [], ""
    for character in line:
        if len((current + character).encode("utf-8")) > 75:
            chunks.append(current)
            current = " " + character
        else:
            current += character
    chunks.append(current)
    return "\r\n".join(chunks)


def calendar_export(tasks):
    """Export calendar events in local floating time, with stable task UIDs."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Panuto AI//Tasks//EN", "CALSCALE:GREGORIAN"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for task in tasks:
        if not task.get("deadline") or task.get("archived") or task.get("status") == "Done":
            continue
        day = date.fromisoformat(task["deadline"])
        lines += ["BEGIN:VEVENT", f"UID:panuto-{task['id']}@panuto.local", f"DTSTAMP:{stamp}"]
        clock = task.get("deadline_time")
        if clock and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock):
            lines.append(f"DTSTART:{day:%Y%m%d}T{clock.replace(':', '')}00")
        else:
            lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
        lines += ["SUMMARY:" + _ical_text(f"{task.get('subject') or ''}: {task.get('activity') or 'Activity'}"),
                  "DESCRIPTION:" + _ical_text("\n".join(req["text"] for req in task.get("requirements", []))),
                  "END:VEVENT"]
    lines += ["END:VCALENDAR"]
    return ("\r\n".join(_fold(line) for line in lines) + "\r\n").encode("utf-8")
