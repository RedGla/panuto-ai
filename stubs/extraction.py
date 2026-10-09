"""Explicit development output, not model inference."""
from contracts import ExtractionResult
def extract_task(text, announcement_date=None):
    return ExtractionResult(dict(subject="Development fixture", activity="Review flow",
        deadline_text=None, deadline_time=None, submission_platform=None, submission_format=None,
        group_size=None, requirements=[], extra_instructions="DEVELOPMENT STUB: edit fields manually.",
        is_revision=False), True, [], "", 0.0)
