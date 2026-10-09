"""Real local inference, bounded retry, no cloud fallback."""
import json
import re
import time
from datetime import datetime
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import URLError
from jsonschema import validate, ValidationError
from contracts import LLM_SCHEMA, ExtractionResult
from prompts import messages_for

MODEL = "qwen3:1.7b"
OLLAMA_URL = "http://127.0.0.1:11434"
MAX_TEXT = 12000

def _chat(messages):
    payload = dict(model=MODEL, messages=messages, stream=False, think=False,
                   format=LLM_SCHEMA, options={"temperature":0,"num_predict":2048},
                   keep_alive="10m")
    request = Request(OLLAMA_URL + "/api/chat", data=json.dumps(payload).encode(),
                      headers={"Content-Type":"application/json"})
    with build_opener(ProxyHandler({})).open(request, timeout=120) as response:
        result = json.loads(response.read(2_000_000))
    return result["message"]["content"]

def extract_task(text, announcement_date=None):
    started = time.perf_counter()
    raw, errors = "", []
    def failure(message):
        return ExtractionResult(None, False, errors + [message], raw,
                                time.perf_counter() - started)
    if not isinstance(text, str) or not text.strip():
        return failure("Announcement text is empty.")
    if len(text) > MAX_TEXT:
        return failure(f"Announcement exceeds {MAX_TEXT} characters. Split it first.")
    messages = messages_for(text)
    for attempt in range(2):
        try:
            raw = _chat(messages)
            task = json.loads(raw)
            validate(task, LLM_SCHEMA)
            if task["deadline_text"]:
                match = re.search(re.escape(task["deadline_text"]), text, re.IGNORECASE)
                if not match:
                    raise ValueError("deadline_text must copy a verbatim phrase from the announcement.")
                task["deadline_text"] = match.group(0)
            # A date or assignment quantity is not a clock time.
            clock_in_source = re.search(
                r"\b\d{1,2}:\d{2}\s*(?:[ap]\.?m\.?)?\b|\b\d{1,2}\s*[ap]\.?m\.?\b",
                text, re.IGNORECASE)
            if not clock_in_source:
                task["deadline_time"] = None
            if task["deadline_time"] and not re.fullmatch(
                    r"(?:[01]\d|2[0-3]):[0-5]\d", task["deadline_time"]):
                try:
                    clock = task["deadline_time"].upper().replace(" ", "")
                    task["deadline_time"] = datetime.strptime(clock, "%I:%M%p").strftime("%H:%M")
                except ValueError:
                    raise ValueError("deadline_time must be HH:MM or an explicit AM/PM time.")
            return ExtractionResult(task, True, [], raw, time.perf_counter() - started)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            error = str(exc).split("\n")[0][:300]
            errors.append(error)
            if attempt == 0:
                messages.extend([{"role":"assistant","content":raw},
                                 {"role":"user","content":"Invalid JSON: " + error +
                                  ". Return corrected schema JSON."}])
        except (URLError, OSError, KeyError, TypeError) as exc:
            return failure("Local Ollama unavailable or invalid response: " + str(exc)[:200])
    return failure("Extraction failed after two attempts. Enter the task manually.")
