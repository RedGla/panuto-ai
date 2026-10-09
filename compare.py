"""Deterministic matching and diffs. Students choose the authoritative version."""
import re
import unicodedata
from difflib import SequenceMatcher
from contracts import Change, Diff
FIXED = ("deadline", "deadline_time", "group_size", "submission_format", "submission_platform")
ALIASES = {"ml":"machine learning"}

def normalize(value):
    if isinstance(value, str):
        value = unicodedata.normalize("NFKD", value.casefold())
        value = "".join(c for c in value if not unicodedata.combining(c))
        return " ".join(value.split()) or None
    return value

def similarity(a, b):
    a, b = normalize(a), normalize(b)
    return SequenceMatcher(None, str(a), str(b)).ratio() if a and b else 0.0

def find_matches(new_task, saved, top_k=3):
    subject = ALIASES.get(normalize(new_task.get("subject")), normalize(new_task.get("subject")))
    scored = []
    for task in saved:
        old_subject = ALIASES.get(normalize(task.get("subject")), normalize(task.get("subject")))
        s = similarity(subject, old_subject)
        a = similarity(new_task.get("activity"), task.get("activity"))
        score = s * (0.25 + 0.75 * a)
        if task.get("id") is not None and score >= 0.4:
            scored.append((task["id"], score))
    return sorted(scored, key=lambda item: (-item[1], item[0]))[:max(0, top_k)]

def _key(requirement):
    return re.sub(r"\d+", "", normalize(requirement.get("text")) or "")

def compare_tasks(old, new):
    changes = []
    for field in FIXED:
        if normalize(old.get(field)) != normalize(new.get(field)):
            changes.append(Change(field, old.get(field), new.get(field), "changed"))
    old_req, new_req = old.get("requirements") or [], new.get("requirements") or []
    pairs = [(similarity(_key(a), _key(b)), i, j)
             for i, a in enumerate(old_req) for j, b in enumerate(new_req)
             if similarity(_key(a), _key(b)) >= 0.6]
    used_old, used_new = set(), set()
    for _, i, j in sorted(pairs, key=lambda pair: (-pair[0], pair[1], pair[2])):
        if i in used_old or j in used_new:
            continue
        used_old.add(i)
        used_new.add(j)
        a, b = old_req[i], new_req[j]
        if a.get("number") != b.get("number") or normalize(a["text"]) != normalize(b["text"]):
            changes.append(Change("requirements:" + b["text"], a, b, "changed"))
    for i, item in enumerate(old_req):
        if i not in used_old:
            changes.append(Change("requirements:" + item["text"], item, None, "removed"))
    for j, item in enumerate(new_req):
        if j not in used_new:
            changes.append(Change("requirements:" + item["text"], None, item, "added"))
    return Diff(changes, bool(changes))
