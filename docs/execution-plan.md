# Panuto AI: Execution Plan

## Assumptions (correct any that are wrong)
- The hackathon is **24 hours** and the demo is **5 minutes**.
- Every laptop has at least 8 GB RAM, Python 3.11, and a mix of Windows and macOS.
- You pick **one demo laptop** at H0. All timing and accuracy numbers come from that laptop.
- The model can't reliably compute dates, so the LLM returns `deadline_text` only. Python resolves the actual date.
- Dev-only stubs are allowed behind `PANUTO_STUB=1`. The demo build refuses to start with that flag set.
- Ollama's `format` parameter supports JSON schema output, and Qwen3 is run with thinking off. Verify this in the H0-1 smoke test.

**Open question:** what are the demo laptop's RAM and CPU/GPU? If it has 8 GB and no GPU, expect 10-30 s per extraction, and more UI polish should be cut to protect the extraction loop.

---

## 1. Timeline

| Hour | Milestone | Checkpoint (must be true to continue) |
|---|---|---|
| H0-1 | Repo skeleton from M4: `contracts.py`, folders, `requirements.txt`, `check_env.py`. Everyone installs Ollama, runs `ollama pull qwen3:1.7b`, installs Tesseract with `eng` + `fil` data, and runs `pip install`. | **CP1:** `check_env.py` passes on all 4 laptops. Contracts are merged to `main` and frozen. |
| H1-6 | Each member builds their own module against the contract (section 2). | M1 CLI extracts 3 samples with Wi-Fi off. M2 gets text from 1 screenshot and 1 PDF. M3 compares two fixture JSONs. M4's UI renders with stubs. |
| H6 | **CP2: offline smoke test.** Wi-Fi off on the demo laptop. | Each module passes its own definition of done. Merge all branches to `main`. |
| H6-12 | M4 wires the real modules into the UI. M1 tunes prompts. M3 finishes storage and dashboard queries. M2 finishes the deadline resolver. | |
| H12 | **CP3: first end-to-end run.** Upload, extract, edit/confirm, save, dashboard. | Works on the demo laptop with Wi-Fi off. If not, stop everything else and fix this. |
| H12-16 | Compare loop: upload revision, match, diff, highlight, confirm which version is authoritative. | **CP4:** the Oct 12 / Oct 14 sample pair (section 7) produces the right diff. |
| H16-19 | Failure cases (section 7). Measure accuracy on 10 labeled samples and record latency. Naps in shifts of 2 people at a time. | Numbers recorded in `RESULTS.md`. |
| H19 | **Feature freeze.** Only bug fixes after this. | Cut list applied (section 9). |
| H19-21 | Minimal polish: status indicators, source view, empty states. Seed demo data by running the real pipeline, not by hardcoding. | |
| H21 | **Code freeze.** Tag `demo-v1`. | A fresh clone runs on the demo laptop. |
| H21-23 | Rehearsals, Wi-Fi-off run, backup screen recording (section 8). | Two full timed rehearsals under 5:00. |
| H23-24 | Buffer. Final Wi-Fi-off run, charge laptops, back up the recording to 2 devices. | |

---

## 2. Work split

| Member | Module and files | Inputs | Outputs | Definition of done |
|---|---|---|---|---|
| **M1: AI engine** | `extraction.py`, `prompts.py`, `scripts/measure.py` | `text: str`, `announcement_date` | `ExtractionResult` (validated task dict, raw output, latency) | Valid JSON on 9 of 10 samples, retry once on invalid output, never crashes. Works with Wi-Fi off. Accuracy script runs on labeled samples. |
| **M2: Ingestion and dates** | `ingestion.py`, `dates.py` | File path or pasted text | `SourceDoc`; `DeadlineResult` | PNG/JPG, text PDF, scanned PDF and pasted text all return text. Warnings are set when OCR is poor. Date resolver passes the 8 date test cases. |
| **M3: Compare and storage** | `db.py`, `compare.py` | Task dicts | `Diff`, match candidates, DB rows | Pure Python, pytest tests pass on fixtures. Matching and diffing work with no model running. Version history is stored. |
| **M4: UI and integration** | `app.py`, `pipeline.py`, `ui/` | All of the above | Streamlit app | Full flow works on real modules. Edit form, diff highlight and source view are working. Owns `main` health, merges, and demo data. |

**Nobody is blocked** because M4 starts with stubs and M3 starts with fixture JSON. The contract is the only thing everyone depends on, and it is frozen at H1.

---

## 3. Agreed interfaces (`contracts.py`)

```python
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# What the LLM returns (no resolved dates). Used as Ollama `format` schema.
LLM_SCHEMA = {
  "type": "object",
  "additionalProperties": False,
  "required": ["subject","activity","deadline_text","deadline_time",
               "submission_platform","submission_format","group_size",
               "requirements","extra_instructions","is_revision"],
  "properties": {
    "subject": {"type": ["string","null"]},
    "activity": {"type": ["string","null"]},
    "deadline_text": {"type": ["string","null"]},   # verbatim phrase, e.g. "next Friday"
    "deadline_time": {"type": ["string","null"]},   # "HH:MM" 24h or null
    "submission_platform": {"type": ["string","null"]},
    "submission_format": {"type": ["string","null"]},
    "group_size": {"type": ["integer","null"]},
    "requirements": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["text","number"],
        "properties": {"text": {"type": "string"},
                       "number": {"type": ["integer","null"]}}}},
    "extra_instructions": {"type": ["string","null"]},
    "is_revision": {"type": "boolean"}              # "revised na", "update", "pala"
  }
}

# Final task = LLM fields + these (set by Python, never by the LLM)
#   "deadline": "YYYY-MM-DD" | None
#   "needs_date_confirmation": bool
#   "source_id": str

@dataclass
class SourceDoc:
    source_id: str                 # uuid4 hex
    kind: str                      # "image" | "pdf" | "text"
    text: str
    original_path: Optional[str]   # copy stored under data/sources/
    announcement_date: Optional[date]
    ocr_confidence: Optional[float]  # 0-100 or None
    warnings: list = field(default_factory=list)

@dataclass
class ExtractionResult:
    task: Optional[dict]           # LLM_SCHEMA-valid, or None if failed
    valid: bool
    errors: list
    raw_output: str
    latency_s: float

@dataclass
class DeadlineResult:
    deadline: Optional[date]
    needs_confirmation: bool
    reason: str                    # shown to student

@dataclass
class Change:
    field: str                     # e.g. "deadline", "requirements:dataset"
    old: object
    new: object
    kind: str                      # "changed" | "added" | "removed"

@dataclass
class Diff:
    changes: list                  # list[Change]
    has_conflict: bool

# ---- function signatures ----
# ingestion.py
def ingest_file(path: str, announcement_date: Optional[date] = None) -> SourceDoc: ...
def ingest_text(text: str, announcement_date: Optional[date] = None) -> SourceDoc: ...
# extraction.py
def extract_task(text: str, announcement_date: Optional[date] = None) -> ExtractionResult: ...
# dates.py
def resolve_deadline(deadline_text: Optional[str],
                     announcement_date: Optional[date]) -> DeadlineResult: ...
# pipeline.py (M4)
def analyze(doc: SourceDoc) -> dict:   # extract + resolve dates -> full task dict
# compare.py
def find_matches(new_task: dict, saved: list[dict], top_k: int = 3) -> list[tuple[int, float]]: ...
def compare_tasks(old: dict, new: dict) -> Diff: ...
# db.py
def init_db(path: str = "data/panuto.db") -> None: ...
def save_task(task: dict, source: SourceDoc) -> int: ...                 # creates task + v1
def add_version(task_id: int, task: dict, source: SourceDoc) -> None: ...  # after student confirms
def update_task(task_id: int, task: dict) -> None: ...                   # manual edit
def get_task(task_id: int) -> dict: ...
def list_tasks() -> list[dict]: ...                                       # sorted by deadline, nulls last
def list_versions(task_id: int) -> list[dict]: ...                        # includes source text
```

**Comparison rules (deterministic, M3):**
- Fixed fields (`deadline`, `deadline_time`, `group_size`, `submission_format`, `submission_platform`) are compared by equality after normalization.
- Requirements are paired by `difflib` similarity on the text with digits stripped. A paired requirement with a different `number` is `changed`. Unpaired ones are `added` or `removed`.
- `find_matches` scores subject similarity and activity similarity. Above 0.75 it suggests a match. Between 0.4 and 0.75 it asks the student. The student can always pick manually.

---

## 4. Git workflow

- **Branches:** `main` (always runs), `feat/ai-engine` (M1), `feat/ingestion` (M2), `feat/compare-db` (M3), `feat/ui` (M4).
- **File ownership:** each person edits only their own files. Only M4 touches `contracts.py`, `app.py`, `pipeline.py` and `requirements.txt`. Anyone who needs a contract change asks in chat, and M4 changes it.
- **Test data** goes in `tests/fixtures/<owner>/`, so nobody collides there.
- **Merge schedule:** merge to `main` at H1, H6, H12, H16 and H19, plus any time a module hits its definition of done. Before merging, run `git pull --rebase origin main`, run the tests, then fast-forward merge.
- **Commits:** small and frequent. Never force-push `main`. After H19 only M4 merges, and only bug fixes.
- **Tags:** `cp2`, `cp3`, `cp4` and `demo-v1`, so there is always a known-good fallback to check out.

---

## 5. Agent prompts (paste into each member's coding agent)

### M1: AI engine
```
Project: Panuto AI, an offline Streamlit app that extracts structured task info from Filipino Taglish class announcements using Ollama + Qwen3 1.7B (quantized), Python only, no cloud.
Read contracts.py first; do not change it. You own extraction.py, prompts.py, scripts/measure.py.

Task: implement extract_task(text, announcement_date) -> ExtractionResult.
- Call Ollama locally (python `ollama` package or HTTP localhost:11434) with model qwen3:1.7b, thinking disabled, temperature 0, and the LLM_SCHEMA passed as the structured-output `format`.
- Prompt must handle Taglish (e.g. "next Friday na deadline", "by group of 3", "revised na yung instructions"). Copy deadline_text verbatim; never convert to a date. Use null when a field is absent; never invent values. Include 2-3 few-shot examples in prompts.py.
- Validate output with jsonschema. On invalid JSON, retry once with the error appended. If it still fails return valid=False with errors; never raise.
- Record latency_s. No hardcoded extraction results anywhere.
- scripts/measure.py: run extract_task over tests/fixtures/ai/*.json (each has input text + expected fields) and print per-field accuracy and mean latency. Report only what it measures.

Acceptance tests:
1. With Wi-Fi disabled, extract_task works on the sample announcement "Guys, yung activity sa ML, next Friday na deadline. By group of 3. PDF submission sa LMS. Yung dataset kailangan minimum 300 rows." and returns subject ML/Machine Learning, group_size 3, submission_format PDF, platform LMS, deadline_text "next Friday", a requirement with number 300.
2. Empty string and gibberish input return valid results with nulls or valid=False, no exception.
3. Output always passes jsonschema when valid=True.
4. pytest tests mock the Ollama call for schema/retry logic only; a separate manual test hits the real model.
```

### M2: Ingestion and dates
```
Project: Panuto AI, offline Streamlit app for reading Filipino class announcements. Read contracts.py first; do not change it. You own ingestion.py and dates.py.

Task A, ingestion.py: implement ingest_file(path, announcement_date) and ingest_text(text, announcement_date) returning SourceDoc.
- Images (png/jpg): Tesseract via pytesseract, lang "eng+fil", with light preprocessing (grayscale, upscale small images). Set ocr_confidence from mean word confidence; add a warning if below 60 or text is under 20 chars.
- PDFs: PyMuPDF; extract embedded text per page. If a page has almost no text, rasterize it and OCR it.
- Copy the original file to data/sources/<source_id>.<ext> so it can be shown later.
- Never raise on bad input; return a SourceDoc with a warning.

Task B, dates.py: resolve_deadline(deadline_text, announcement_date) -> DeadlineResult, pure Python (datetime, regex, optionally dateparser if allowed).
- Handle: "bukas", "ngayon", "mamaya", "Friday", "next Friday", "Oct 16", "October 16", "10/16", "sa susunod na meeting", "next week", None.
- If announcement_date is None and the text is relative, return deadline=None, needs_confirmation=True.
- "next Friday" is ambiguous (this coming Friday vs the Friday of next week): return the later Friday candidate but needs_confirmation=True with a reason string.
- "sa susunod na meeting" and anything vague: deadline=None, needs_confirmation=True.
- Never invent a date.

Acceptance tests (pytest, fixed announcement_date 2026-10-12, a Monday):
bukas -> 2026-10-13 (no confirm); "Oct 16" -> 2026-10-16 (no confirm); "next Friday" -> needs_confirmation True; "sa susunod na meeting" -> None + confirm; None -> None + confirm; with announcement_date None "bukas" -> None + confirm.
Ingestion tests: one clear screenshot, one text PDF, one scanned PDF, one pasted text all produce non-empty text; a blank image produces a warning.
```

### M3: Compare and storage
```
Project: Panuto AI, offline Streamlit app that tracks class announcements and highlights changes between versions. Read contracts.py first; do not change it. You own db.py and compare.py. These must be pure Python, no LLM calls.

Task:
- db.py (sqlite3): tables sources, tasks (current confirmed version), task_versions (each confirmed version with source_id and source text). Implement init_db, save_task, add_version, update_task, get_task, list_tasks (sorted by deadline, nulls last), list_versions per the signatures in contracts.py. Store tasks as JSON plus indexed subject/activity/deadline columns.
- compare.py: compare_tasks(old, new) -> Diff. Compare deadline, deadline_time, group_size, submission_format, submission_platform by normalized equality. Pair requirements by difflib similarity on text with digits stripped (threshold ~0.6); a paired requirement with a different number is "changed" (e.g. dataset rows 300 -> 500); unpaired are "added"/"removed". has_conflict is True if any change exists.
- find_matches(new_task, saved, top_k): score subject + activity similarity (normalize case, accents, "ML" vs "Machine Learning" via a small alias dict you can extend). Return (task_id, score) sorted descending.

Acceptance tests (pytest with fixtures in tests/fixtures/compare/):
1. Old: deadline 2026-10-16, group 3, PDF, requirement "dataset minimum 300 rows" (300). New: deadline 2026-10-23, group 3, PDF, "dataset minimum 500 rows" (500), plus added "include data dictionary". Diff = deadline changed, requirement changed 300->500, requirement added; group size and format NOT flagged.
2. Identical tasks -> no changes, has_conflict False.
3. Different activity in same subject scores lower than a match and falls below 0.75.
4. DB round trip: save, add_version, list_versions returns 2 versions in order; survives closing and reopening the db file.
```

### M4: UI and integration
```
Project: Panuto AI, offline Streamlit app. Read contracts.py first; you are the only one who may edit it, plus app.py, pipeline.py, requirements.txt, ui/. Other members are building ingestion.py/dates.py (M2), extraction.py (M1), db.py/compare.py (M3) in parallel; until their branches merge, build against stub implementations in stubs/ that are used only when env PANUTO_STUB=1. The app must refuse to start in "demo mode" (PANUTO_DEMO=1) if PANUTO_STUB=1 is set. No hardcoded extraction results in the real path.

Task:
1. Repo skeleton first (within the first hour): contracts.py (paste from team doc), folders, requirements.txt, scripts/check_env.py (checks python version, ollama reachable, model pulled, tesseract on PATH with fil data, sqlite).
2. pipeline.analyze(doc): extract_task, then resolve_deadline on deadline_text, then set deadline/needs_date_confirmation/source_id.
3. app.py (Streamlit), tabs: New announcement | Dashboard.
 - New announcement: file upload or paste text, announcement date picker (default today, optional), "Analyze" with spinner and visible "running locally, offline" status.
 - Review form: editable fields, date picker if needs_date_confirmation (highlighted), OCR warnings, expandable original source text.
 - If find_matches returns a candidate: show "This looks like <activity>. Same activity?" with the diff table (changed/added/removed colored), and buttons "Keep old", "Use new", "Save as new activity".
 - Save only after explicit confirm.
 - Dashboard: upcoming tasks sorted by deadline, per-task detail with version history and original announcement text.
4. Handle extraction failure with an error message and manual entry form; never crash.

Acceptance tests:
1. With stubs: full flow clickable end to end.
2. With real modules and Wi-Fi off: paste the sample announcement, review, confirm, appears in dashboard.
3. Paste the revised announcement: diff shows deadline and dataset rows changed; confirming updates the task and adds a version.
4. Closing and relaunching the app keeps saved tasks.
```

---

## 6. Risks and fallbacks

| Risk | Early signal | Fallback |
|---|---|---|
| **Slow inference on a low-end laptop** | More than 30 s per extraction at H6 | Shorten the prompt and few-shots, cap input length, set `num_predict`, use a smaller quant, keep the model loaded between runs (`keep_alive`). Show a progress state. For the demo, use the strongest laptop and pre-warm the model before going on stage. Report the latency you measured. |
| **Bad OCR** | Low `ocr_confidence`, garbled text | Upscale and threshold the image, use `eng+fil`, crop to the message. UI shows the OCR text so the student can correct it before extraction. Demo with a clean screenshot and keep paste as the backup path. |
| **Wrong deadline parsing** | Resolver test failures, or the model returns dates | The LLM never outputs dates. Python resolves them. If anything is ambiguous, the student must confirm. A null deadline is better than a wrong one. |
| **Ollama setup problems** | `check_env.py` fails at H1 | Install early, pull the model once and copy the model folder by USB to other laptops. Check the version supports structured output, and if not, fall back to prompting for JSON plus validation and retry. A wrong `OLLAMA_HOST` or a port conflict is the usual culprit. |
| **Duplicate or mismatched announcement matching** | A revision isn't matched to the original | Matching only suggests. The student always confirms or picks the task manually. Use the alias dict for course names. In the demo, choose a pair that matches cleanly. |
| **Model returns bad JSON** | Validation failures | The schema is passed to Ollama, then one retry, then manual entry form. |
| **Merge breakage near the end** | `main` doesn't run | Tags at each checkpoint, and M4 owns `main`. Roll back to the last tag if needed. |

---

## 7. Testing checklist

### Core demo pair (same activity)

*Original, posted Mon Oct 12, 2026:*
> Guys, yung activity sa ML, next Friday na deadline. By group of 3. PDF submission sa LMS. Yung dataset kailangan minimum 300 rows.

*Revised, posted Wed Oct 14, 2026:*
> Update po sa ML activity: revised na yung instructions. Moved na yung deadline sa Oct 23, 11:59 PM. Dataset minimum 500 rows na, tapos kailangan may data dictionary. Same pa rin, group of 3, PDF sa LMS.

**Expected:** the first extraction sets `needs_date_confirmation=True` ("next Friday" is ambiguous) and the student confirms Oct 16. The diff then shows deadline Oct 16 to Oct 23, dataset 300 to 500 rows, and an added data dictionary requirement. Group size and format are not flagged.

### Other cases

| # | Case | Pass condition |
|---|---|---|
| 1 | "Bukas na po ang submission ng lab report sa Physics, ipasa sa email." | Resolves to next day from the announcement date, no confirm needed |
| 2 | "Sa susunod na meeting na lang yung quiz." | No date invented, confirmation required |
| 3 | No deadline at all | `deadline` null, dashboard handles it |
| 4 | English-only announcement | Extracts correctly |
| 5 | Mixed announcement with two activities | Flag as a limitation, no crash |
| 6 | Duplicate paste of the same announcement | Shows no changes |
| 7 | Same subject, different activity | Does not auto-match |
| 8 | Blurry or cropped screenshot | OCR warning appears, student can edit |
| 9 | Scanned PDF | OCR path works |
| 10 | Wi-Fi off, cold app start | App launches, extraction and dashboard work |
| 11 | Ollama not running | Clear error, manual entry still possible |
| 12 | Close and reopen app | Saved tasks persist |

**Accuracy:** label 10 or more real or realistic samples by hand, run `scripts/measure.py`, and put the results in `RESULTS.md`. Quote only those numbers in the pitch.

---

## 8. Demo prep

**Presenters:** M2 opens with the problem and closes with limitations. M4 drives the live demo. M1 explains the architecture. M3 explains the conflict logic and operates the backup recording.

| Time | What happens | Who |
|---|---|---|
| 0:00-0:40 | Problem: scattered announcements, revisions, missed requirements | M2 |
| 0:40-1:10 | Introduce Panuto AI and turn Wi-Fi off on screen | M4 |
| 1:10-2:10 | Upload the original, show extraction, resolve "next Friday", confirm and save | M4 (M3 narrates) |
| 2:10-3:00 | Upload the revision, matched to the original, highlight the changed deadline and rows and added requirement | M4 (M3 narrates) |
| 3:00-3:40 | Dashboard, version history, original source | M4 |
| 3:40-4:20 | Local architecture, privacy, SQLite storage | M1 |
| 4:20-5:00 | Limitations, measured results, what's next | M2 |

**Prep steps**
- **Rehearse at least three times** with a timer. Two of those runs must be with Wi-Fi off on the demo laptop.
- **Pre-warm** the model before going on stage with one throwaway extraction.
- **Prepare the inputs** in a folder: the two screenshots, plus the same text ready to paste.
- **Backup screen recording** of a full successful run, Wi-Fi visibly off. Keep copies on two devices. Record it by H22 and re-record if the code changes.
- **Live failure plan:** if extraction stalls, say so, switch to the recording, and continue talking over it.
- Charge everything, turn on Do Not Disturb, close other apps.

---

## 9. Cut list (drop in this order)

1. UI polish (colors, layout, animations)
2. Scanned PDF OCR path (keep screenshots and text PDFs)
3. Alias dictionary and fuzzy-match tuning (keep manual match picking)
4. Version history view (keep the latest diff and source text)
5. Dashboard sorting and filtering extras
6. Manual entry form on extraction failure (keep an error message)
7. PDF input (keep screenshot and paste)
8. Screenshot input (keep paste only, but say so honestly in the pitch)

**Never cut:** real local extraction, the confirmation step, compare and highlight, SQLite save, and the Wi-Fi-off demonstration.