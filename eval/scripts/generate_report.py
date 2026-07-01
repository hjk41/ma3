#!/usr/bin/env python3
"""Aggregate eval/results/*.json into summary CSV and markdown snippet."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parents[1]
RESULTS = EVAL_ROOT / "results"
OUT_CSV = RESULTS / "summary.csv"
OUT_MD = EVAL_ROOT / "report" / "RUN_SUMMARY.md"


def main() -> int:
    rows = []
    for p in sorted(RESULTS.glob("eval-*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        ma3 = data.get("ma3") or {}
        counts = ma3.get("counts") or {}
        rows.append(
            {
                "run_id": data.get("run_id", p.stem),
                "scenario": data.get("scenario", ""),
                "agent": data.get("agent", ""),
                "round": data.get("round", ""),
                "verify_pass": data.get("verify_pass", False),
                "duration_s": data.get("duration_s", ""),
                "ma3_context": counts.get("ma3_context", 0),
                "ma3_report": counts.get("ma3_report", 0),
                "ma3_validate": counts.get("ma3_validate", 0),
            }
        )

    RESULTS.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        OUT_MD.write_text("# Run summary\n\nNo result files yet.\n", encoding="utf-8")
        print("no results")
        return 0

    fieldnames = list(rows[0].keys())
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    lines = ["# Run summary", "", f"Total runs: {len(rows)}", "", "| run_id | verify | ctx | report | validate | dur_s |", "|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(
            f"| {r['run_id']} | {r['verify_pass']} | {r['ma3_context']} | {r['ma3_report']} | {r['ma3_validate']} | {r['duration_s']} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_CSV} and {OUT_MD} ({len(rows)} runs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
