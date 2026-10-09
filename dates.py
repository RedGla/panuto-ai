"""Conservative date resolution: uncertainty always requires confirmation."""
import calendar
import re
from datetime import date, timedelta
from contracts import DeadlineResult
DAYS = {name.lower(): i for i, name in enumerate(calendar.day_name)}
MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})

def resolve_deadline(deadline_text, announcement_date):
    def unknown(reason):
        return DeadlineResult(None, True, reason)
    if not deadline_text or not isinstance(deadline_text, str):
        return unknown("No deadline stated. Confirm a date or leave it unknown.")
    text = deadline_text.strip().lower()
    if re.search(r"\b(?:or|either|between|until|not)\b", text):
        return unknown("Multiple candidates, a range, or a negated date needs confirmation.")
    if re.search(r"next week|susunod na (meeting|linggo)|soon|later|this week", text):
        return unknown("Deadline is vague. Confirm the exact date.")
    relative = re.search(r"\b(bukas|tomorrow|ngayon|today|mamaya|tonight)\b", text)
    if relative:
        if announcement_date is None:
            return unknown("Relative deadline needs the announcement date.")
        offset = 1 if relative.group(1) in ("bukas", "tomorrow") else 0
        return DeadlineResult(announcement_date + timedelta(days=offset), False,
                              "Resolved from the announcement date.")
    weekdays = re.findall(r"\b(" + "|".join(DAYS) + r")\b", text)
    if len(weekdays) == 1:
        if announcement_date is None:
            return unknown("Weekday deadline needs the announcement date.")
        day = DAYS[weekdays[0]]
        if "next" in text:
            monday = announcement_date - timedelta(days=announcement_date.weekday())
            return DeadlineResult(monday + timedelta(days=7 + day), True,
                                  "'Next' weekday is ambiguous. Confirm the intended date.")
        return DeadlineResult(announcement_date + timedelta(
            days=(day - announcement_date.weekday()) % 7), False,
            "Resolved to the upcoming weekday, including today.")
    confirm = False
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    named = re.search(r"\b(" + "|".join(MONTHS) +
                      r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", text)
    numeric = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", text)
    if iso:
        year, month, day = map(int, iso.groups())
    elif named:
        month, day = MONTHS[named[1]], int(named[2])
        year = int(named[3]) if named[3] else None
    elif numeric:
        month, day = int(numeric[1]), int(numeric[2])
        year = int(numeric[3]) if numeric[3] else None
        confirm = month <= 12 and day <= 12
    else:
        return unknown("Date phrase unsupported or ambiguous. Confirm it manually.")
    if year is None:
        if announcement_date is None:
            return unknown("Date lacks a year and announcement date. Confirm the year.")
        year = announcement_date.year
    try:
        resolved = date(year, month, day)
    except ValueError:
        return unknown("Date is invalid. Confirm it manually.")
    if announcement_date and resolved < announcement_date:
        confirm = True
    reason = "Confirm month/day order or a date before the announcement." if confirm else "Resolved explicit date."
    return DeadlineResult(resolved, confirm, reason)
