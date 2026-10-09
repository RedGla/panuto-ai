"""On-demand local checks; no cloud requests or inference."""
import json
import shutil
import sqlite3
import subprocess
import sys
from urllib.request import build_opener, ProxyHandler
import db
from extraction import OLLAMA_URL, MODEL


def check_setup():
    checks = []
    def add(name, ok, detail):
        checks.append(dict(name=name, ok=bool(ok), detail=detail))
    add("Python", sys.version_info >= (3, 11), sys.version.split()[0])
    try:
        with db._connect() as connection:
            ok = connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        add("Storage", ok, "Local database is readable." if ok else "Database integrity check failed.")
    except (sqlite3.Error, OSError):
        add("Storage", False, "Local storage could not be read. Preserve your data directory and recover a backup.")
    try:
        with build_opener(ProxyHandler({})).open(OLLAMA_URL + "/api/tags", timeout=2) as response:
            models = json.load(response)["models"]
        available = any(item.get("name") == MODEL for item in models)
        add("Local model", available, MODEL + " is installed." if available else "Run ollama pull " + MODEL)
    except (OSError, ValueError, KeyError, TypeError):
        add("Local model", False, "Start Ollama. Manual entry and saved activities remain available.")
    executable = shutil.which("tesseract")
    if not executable:
        add("OCR", False, "Install Tesseract and add it to PATH. Paste text works without OCR.")
    else:
        try:
            result = subprocess.run([executable, "--list-langs"], capture_output=True, text=True, timeout=5)
            languages = set(result.stdout.splitlines())
            ok = result.returncode == 0 and {"eng", "fil"} <= languages
            add("OCR", ok, "English and Filipino data are ready." if ok else "Install both eng and fil language data.")
        except (OSError, subprocess.TimeoutExpired):
            add("OCR", False, "Tesseract could not be checked. Paste text remains available.")
    return checks
