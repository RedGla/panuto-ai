# Demo verification

## Before disconnecting

- Install Ollama, pull `qwen3:1.7b`, and install Tesseract with `eng+fil`.
- Run `python scripts/check_env.py --smoke`.
- Run `python scripts/measure.py`; record the model, machine, dataset, and successful inference latency in RESULTS.md.
- Start from a fresh clone and install requirements.
- Unset PANUTO_STUB. Set PANUTO_DEMO=1.
- Use real inference to seed demo data. Test data in tests/fixtures is never a production shortcut.

## Wi-Fi-off acceptance

1. Disable Wi-Fi on the selected demo laptop and cold-start Streamlit and Ollama.
2. Load the original announcement from examples/original.txt, posted October 12, 2026.
3. Analyze; confirm October 16 rather than accepting the ambiguous "next Friday" candidate.
4. Save only after review and explicit confirmation.
5. Load examples/revised.txt, posted October 14, 2026.
6. Compare against the saved activity. Expect the changed deadline, 300 to 500 dataset rows,
   and added data dictionary requirement. The new 23:59 time can also be highlighted.
7. Confirm the revised task, inspect both source versions, restart, and verify persistence.
8. Try a clear screenshot, text PDF, scanned PDF, blurry image, no deadline,
   duplicate announcement, and different activity in the same subject.
9. Stop Ollama and verify manual entry still works.

## Rehearsals

Run three timed five-minute rehearsals, including two with Wi-Fi off.
Record one successful real-model run with Wi-Fi visibly off and store copies
on two devices. Then tag the verified commit demo-v1.
Checkpoint tags should reflect completed acceptance gates, not just implementation.
