"""Check prerequisites; --smoke performs one real schema extraction."""
import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extraction import OLLAMA_URL, MODEL, extract_task

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    failures = []
    def check(name, success, detail=""):
        print(f"{'PASS' if success else 'FAIL'} {name}: {detail}")
        if not success:
            failures.append(name)
    check("Python", sys.version_info >= (3,11), sys.version.split()[0])
    check("SQLite", sqlite3.connect(":memory:").execute("SELECT 1").fetchone()[0] == 1)
    try:
        with build_opener(ProxyHandler({})).open(OLLAMA_URL + "/api/tags", timeout=5) as response:
            models = json.load(response)["models"]
        check("Ollama", True, OLLAMA_URL)
        check("Model", any(item["name"] == MODEL for item in models), MODEL)
    except Exception as exc:
        check("Ollama", False, str(exc))
    executable = shutil.which("tesseract")
    check("Tesseract", bool(executable), executable or "Install and add to PATH")
    if executable:
        result = subprocess.run([executable,"--list-langs"], capture_output=True, text=True, timeout=10)
        languages = set(result.stdout.splitlines()[1:])
        check("OCR languages", {"eng","fil"}.issubset(languages), ", ".join(sorted(languages)))
    if args.smoke:
        result = extract_task("ML activity: next Friday na deadline. By group of 3. PDF sa LMS.")
        check("Real schema extraction", result.valid, f"{result.latency_s:.2f}s; {result.errors}")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
