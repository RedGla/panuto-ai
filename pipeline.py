"""Extract first; Python resolves dates; failed extraction permits manual entry."""
import os
from contracts import LLM_SCHEMA
from extraction import extract_task
from dates import resolve_deadline

def blank_task(source_id):
    task = {field:None for field in LLM_SCHEMA["required"]}
    task.update(requirements=[], is_revision=False, deadline=None,
                needs_date_confirmation=True, source_id=source_id)
    return task

def analyze(doc):
    if os.environ.get("PANUTO_DEMO") == "1" and os.environ.get("PANUTO_STUB") == "1":
        raise RuntimeError("Demo mode refuses development stubs.")
    if os.environ.get("PANUTO_STUB") == "1":
        from stubs.extraction import extract_task as extractor
    else:
        extractor = extract_task
    result = extractor(doc.text, doc.announcement_date)
    task = dict(result.task) if result.valid else blank_task(doc.source_id)
    deadline = resolve_deadline(task.get("deadline_text"), doc.announcement_date)
    task.update(deadline=deadline.deadline.isoformat() if deadline.deadline else None,
                needs_date_confirmation=deadline.needs_confirmation, source_id=doc.source_id)
    return dict(task=task, valid=result.valid, errors=result.errors, raw_output=result.raw_output,
                latency_s=result.latency_s, date_reason=deadline.reason)
