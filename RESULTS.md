# Verification results

Verified on October 10, 2026, with Python 3.12.5 on Windows.

## Completed

- 43 automated tests pass.
- Streamlit UI tests cover review, explicit confirmation, revision diffs and saving,
  version history persistence after restart, manual fallback, development mode,
  and refusal of development stubs in demo mode.
- Date tests cover relative dates, absent anchors, named and numeric dates,
  next-Friday ambiguity, invalid dates, ranges, and negation.
- Comparison tests cover the 300-to-500 dataset revision, added requirements,
  unchanged submission fields, normalization, and matching suggestions.
- SQLite tests cover round trips, version history, sorted unknown deadlines,
  manual edit auditing, and transaction rollback.
- Extraction tests mock only the Ollama boundary to verify schema validation,
  bounded retry, stopped-server handling, empty/large input, invalid times,
  and rejection of non-verbatim deadline phrases.
- Ingestion tests verify embedded PDF text and source retention, invalid input,
  and mocked OCR paths for screenshots, scanned PDFs, and blank images.
- Python dependency check reports no broken requirements.
- Local Streamlit server health endpoint reports `ok`.

## Not yet verified

The current PC has no installed Ollama or Tesseract detected, and nothing listens
on localhost:11434. The environment checker correctly reports those failures.
Real model accuracy, real model latency, actual Tesseract OCR accuracy, and
Wi-Fi-off operation have not been measured. Browser visual inspection was
unavailable in this execution environment; UI behavior was tested through
Streamlit AppTest.

The 10 AI fixtures are synthetic hand-labeled examples, not real student data.
No accuracy percentage or inference timing should be quoted from mocked tests.

## Remaining gates

1. Install runtime prerequisites and Filipino OCR data, then run
   `python scripts/check_env.py --smoke`.
2. Run `python scripts/measure.py` against the real model. Record successful
   extraction rate, labeled field scores, successful inference latency, hardware,
   Ollama/model version, and the exact sample set.
3. Test real screenshots and scanned PDFs with Tesseract.
4. Complete fresh-clone and Wi-Fi-off verification on the selected demo laptop.
5. Perform timed rehearsals and save a backup recording.

Checkpoint tags and `demo-v1` are intentionally absent until their acceptance
conditions pass.
