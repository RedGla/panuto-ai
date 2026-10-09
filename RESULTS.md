# Verification results

Verified October 10, 2026, on this Windows PC.
Python 3.12.5; Ollama 0.40.2; Qwen3 1.7B (model ID 8f68893c685c),
llamacpp runner on the GTX 1650 GPU; Ryzen 5 4600H; 7,916,032,000 bytes of physical memory.
Tesseract 5.4.0 with English and Filipino tessdata_fast models.

## Real model measurements

- Valid schema extraction: 10/10 synthetic samples.
- Mean warm extraction latency: 1.57 seconds.
- Exact matches on selected labeled fields: 51/54. This is not full-task accuracy.
- Every label counts independently; requirement_numbers compares numeric quantities only.
- The same samples were used during prompt tuning, and some overlap with few-shot examples.
  These measurements are development checks, not an independent accuracy benchmark.

| Field | Exact matches |
|---|---|
| subject | 10/10 |
| activity | 7/7 |
| group_size | 5/5 |
| submission_format | 6/6 |
| submission_platform | 8/8 |
| is_revision | 4/6 |
| deadline_time | 4/4 |
| deadline_text | 4/5 |
| requirement_numbers | 3/3 |

Full measured outputs: [RESULTS.json](RESULTS.json).

## Startup behavior

The first-ever setup request timed out at 120.07 seconds; server logs showed 80.72
seconds just to initialize the model runner. The next warm smoke extraction passed
in 2.03 seconds. After explicitly unloading and reloading the model, the smoke
check passed in 8.31 seconds. Pre-warm the model before the presentation.
The app preserves manual entry when startup or inference fails.

## Completed acceptance checks

- 49 automated tests pass, including schema retry, source grounding, explicit
  clock normalization, absent-clock protection, date ambiguity, matching, SQLite
  transactions, confirmation, history, manual fallback, and demo/stub refusal.
- Real screenshot OCR passes on original.png and revised.png, with mean word
  confidences of 95.74 and 95.41 respectively. These are synthetic screenshots.
- Real text PDF and scanned PDF ingestion pass; blank-image warnings pass.
- Real inference through Streamlit AppTest: original announcement, explicit
  October 16 date confirmation, save, revised screenshot OCR, changed deadline
  and dataset quantity, added data dictionary, confirmed update, and persistence
  after restarting the app all pass.
- One demo activity with two real-model versions is seeded only if storage is empty.
- Environment smoke check passes with both OCR languages and the real model.
- Local Streamlit health endpoint reports ok.

Detailed synthetic-source evidence: [docs/verification](docs/verification).

## Remaining human-run gates

Physical Wi-Fi-off operation, timed five-minute rehearsals, and backup screen
recording remain unverified. Browser visual inspection was unavailable; UI behavior
was exercised through Streamlit AppTest with real model and OCR boundaries.
No demo-v1 or offline checkpoint tag is published before those gates pass.
See [demo checklist](docs/demo-checklist.md).
