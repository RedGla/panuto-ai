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
