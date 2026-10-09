"""Measure labeled fields against real inference. Never substitutes fixtures for inference."""
import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from statistics import mean
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extraction import extract_task

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default=str(Path(__file__).resolve().parents[1] / "tests/fixtures/ai"))
    parser.add_argument("--output", default="RESULTS.json")
    args = parser.parse_args()
    paths = sorted(Path(args.fixtures).glob("*.json"))
    if not paths:
        parser.error("No labeled fixtures found.")
    correct, total, samples = Counter(), Counter(), []
    for path in paths:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        posted = date.fromisoformat(fixture["announcement_date"]) if fixture.get("announcement_date") else None
        result = extract_task(fixture["input"], posted)
        for field, expected in fixture["expected"].items():
            actual = (result.task or {}).get(field)
            if field == "requirement_numbers" and result.valid:
                actual = sorted(item["number"] for item in result.task["requirements"] if item["number"] is not None)
            total[field] += 1
            if result.valid and actual == expected:
                correct[field] += 1
        samples.append(dict(file=path.name, valid=result.valid, latency_s=result.latency_s,
                            errors=result.errors, task=result.task))
        print(f"{path.name}: {'valid' if result.valid else 'failed'} {result.latency_s:.2f}s", flush=True)
    report = dict(dataset="Synthetic hand-labeled fixtures, not real student announcements",
                  samples=len(samples), valid=sum(item["valid"] for item in samples),
                  field_accuracy={field:dict(correct=correct[field], total=total[field],
                                             accuracy=correct[field]/total[field]) for field in total},
                  attempt_mean_latency_s=mean(item["latency_s"] for item in samples),
                  successful_mean_latency_s=mean(item["latency_s"] for item in samples if item["valid"])
                      if any(item["valid"] for item in samples) else None,
                  results=samples)
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key:value for key,value in report.items() if key != "results"}, indent=2))
    return 0 if report["valid"] == len(samples) else 1

if __name__ == "__main__":
    raise SystemExit(main())
