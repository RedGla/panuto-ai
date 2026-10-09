"""Validate confirmed task edits at the storage boundary."""
import re
from datetime import date
from jsonschema import validate
from contracts import LLM_SCHEMA


def validate_task(task):
    result = {key: value for key, value in task.items() if key != "id"}
    validate({key: result.get(key) for key in LLM_SCHEMA["required"]}, LLM_SCHEMA)
    if set(result) != set(LLM_SCHEMA["required"]) | {"deadline", "needs_date_confirmation", "source_id"}:
        raise ValueError("Invalid task fields.")
    if not isinstance(result["source_id"], str) or not result["source_id"]:
        raise ValueError("A confirmed task must have a source.")
    if type(result["needs_date_confirmation"]) is not bool:
        raise ValueError("Invalid date confirmation flag.")
    if result["deadline"] is not None:
        date.fromisoformat(result["deadline"])
    if result["deadline_time"] and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", result["deadline_time"]):
        raise ValueError("Time must use 24-hour HH:MM.")
    return result
