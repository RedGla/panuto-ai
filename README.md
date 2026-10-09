# Panuto AI

Panuto AI turns Filipino, Taglish, and English class announcements into tasks
you review and confirm. It compares revised instructions, highlights changes,
and stores confirmed versions in SQLite.

## Run locally

Requirements: Python 3.11+, [Ollama](https://docs.ollama.com/windows), and
[Tesseract](https://tesseract-ocr.github.io/tessdoc/Installation.html) with
English (`eng`) and Filipino (`fil`) language data. Install these prerequisites
and download the model while connected. Once installed, inference and storage
work locally without a cloud API or API key.

```bash
git clone https://github.com/RedGla/panuto-ai.git
cd panuto-ai
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull qwen3:1.7b
# Start Ollama if it is not already running: ollama serve
python scripts/check_env.py --smoke
python -m streamlit run app.py
```

Open http://127.0.0.1:8501. The server binds to localhost. All data lives in
`data/` relative to the directory where you start the app; run from the repo root.
Keep a backup of that directory. It contains personal announcements and is
excluded from Git. Keep the app local; it does not implement multi-user auth.

On Windows, add Tesseract's installation directory to PATH. For missing Filipino
data, download `fil.traineddata` from the official
[tessdata repository](https://github.com/tesseract-ocr/tessdata_fast) into
Tesseract's `tessdata` directory. Check `tesseract --list-langs` for both languages.

## Review an announcement

1. Open **New announcement** in the sidebar. Paste text or upload a PNG, JPG, or PDF. Set the announcement date, or mark it unknown.
2. Load the source. Review OCR warnings and correct the source text before analysis.
3. Analyze locally. If Ollama fails, complete the manual entry form.
4. Edit the extracted fields and choose the intended deadline. An empty deadline remains unknown.
5. Submit **Review changes**, inspect the saved-value preview, and select a saved activity to compare.
6. Check the confirmation box. Choose **Use new**, **Save as new activity**, or **Keep old**.
7. Open Dashboard for confirmed tasks, source text, and version history.

The original source is preserved even if you correct its OCR text before analysis.
Edits in the review form apply to the save preview only after **Review changes**.
No task is saved just by analyzing or matching.

## Manage activities and protect your data

Dashboard supports status, priority, personal notes, search, subject/status/due-date filters,
deadline or priority ordering, and archive/unarchive. Editing saved instructions requires
confirmation and adds a source-backed version. **Add task manually** works without Ollama.

Export the filtered list to CSV or import its deadlines into a calendar with the ICS download.
Calendar dates use your calendar's local timezone; reminder notifications depend on that
calendar. Panuto shows overdue and due-today counts while open.

Use **Backup & setup** to prepare a portable ZIP containing activities, history, source text,
available original files, and organization. Recovery validates the backup and adds copies
after confirmation; it never replaces existing activities. Recovering twice creates duplicates.
Backups are limited to 50 MB. For larger collections, stop the app and copy the entire data
directory. This page also checks local prerequisites and provides usage help.

Existing databases upgrade additively. Extracted announcement fields and the original contract
stay separate from personal status and notes. See [production features](docs/production-features.md)
for behavior, limits, inspirations, and remaining production work.

## Architecture

- `contracts.py`: schema and shared dataclasses from the team plan.
- `ingestion.py`: image OCR, embedded PDF text, scanned-page OCR, pasted text.
- `extraction.py` / `prompts.py`: Qwen3 1.7B through Ollama's localhost HTTP API.
  Requests use schema output, `think=false`, temperature zero, and one validation retry.
  Python normalizes explicit AM/PM clocks and clears clock values when the source has no clock.
- `dates.py`: conservative Python calendar resolution. Ambiguous phrases require confirmation.
- `compare.py`: deterministic matching suggestions and requirement/field diffs.
- `db.py`: transactional SQLite writes with an immutable source snapshot per version.
- `pipeline.py` / `app.py`: review, confirmation, revision, and dashboard flow.

Only the model extracts fields. Python resolves calendar dates. Matching never
automatically updates a saved task. Network proxy variables are bypassed for
Ollama; the extraction endpoint is fixed to 127.0.0.1. Streamlit telemetry is disabled.

## Tests and measurements

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/check_env.py --smoke
python scripts/measure.py --output RESULTS.json
```

Automated unit and UI tests mock inference and OCR; they prove integration behavior,
not model quality or OCR accuracy. The measurement script always calls the real
model and evaluates 10 synthetic, hand-labeled fixtures. Replace or supplement
these with real consented samples before quoting accuracy in a pitch.
See [RESULTS.md](RESULTS.md) for what has actually been verified.

For development UI checks only, set `PANUTO_STUB=1`. A visible warning identifies
stub mode. Setting both `PANUTO_DEMO=1` and `PANUTO_STUB=1` refuses startup.
Do not use stub results as demo data.

## Limits and demo checklist

- One activity per announcement. Multiple activities require separate review.
- OCR can be wrong. Inspect the source and extracted fields.
- Numeric dates use month/day order and ambiguous orders require confirmation.
- A weekday without an announcement date cannot be resolved.
- "Next Friday" requires confirmation even when a candidate date is shown.
- Uploads: 20 MB maximum, 30 PDF pages, bounded raster dimensions.
- No accuracy or inference-latency claim is valid until the real-model run succeeds.

Use [the original execution plan](docs/execution-plan.md) for team ownership,
rehearsals, the cut list, and the five-minute presentation. See
[demo checklist](docs/demo-checklist.md) for remaining human-run gates.
Do not label a release `demo-v1` until the demo laptop passes a fresh-clone,
real-model, Wi-Fi-off run.

The [submission draft](docs/submission-draft.md) records known disclosures and missing video, team, and public-repository information from the organizer slides.

## Frontend design

The workspace uses a responsive sidebar, task summaries, attention notices, compact filters, and a four-step announcement review. Confirmed revisions show saved and new values side by side; the edit form remains available in an accordion. Motion is brief and respects reduced-motion preferences. All fonts and widgets work locally.

Requires Streamlit 1.65 or newer. After upgrading, restart the app to load the updated theme and imported UI modules. See [design system](DESIGN.md) for tokens, GitHub inspirations, and UX decisions.

Frontend verification: 71 tests pass, including navigation, revision confirmation, draft retention after review, discard/cancel, filters, and HTML escaping. Desktop and mobile browser checks used isolated synthetic fixtures; the real local AI/OCR pipeline was not re-benchmarked for this visual redesign.
