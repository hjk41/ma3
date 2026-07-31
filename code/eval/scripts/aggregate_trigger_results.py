#!/usr/bin/env python3
"""Aggregate trigger experiment metrics from runs.csv.

Usage:
  aggregate_trigger_results.py --runs code/eval/results/trigger/runs.csv \\
      --out code/eval/results/trigger/summary.md
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def pct(num: int, den: int) -> str:
    if den == 0:
        return "n/a"
    return f"{100.0 * num / den:.1f}%"


def aggregate(runs_path: Path) -> str:
    rows = list(csv.DictReader(runs_path.open(encoding="utf-8")))
    if not rows:
        return "# Trigger experiment summary\n\nNo runs yet.\n"

    by_arm: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if not row.get("run_id"):
            continue
        by_arm[row.get("arm") or "unknown"].append(row)

    lines = ["# Trigger experiment summary", "", f"Total runs: {len(rows)}", ""]
    lines.append("| Arm | Runs | Read before mutation | Write occurred | Task pass |")
    lines.append("|---|---:|---:|---:|---:|")

    for arm, group in sorted(by_arm.items()):
        n = len(group)
        read_ok = sum(1 for r in group if r.get("read_before_mutation") in ("1", "true", "True", "yes"))
        write_ok = sum(1 for r in group if r.get("write_occurred") in ("1", "true", "True", "yes"))
        task_ok = sum(1 for r in group if r.get("task_pass") in ("1", "true", "True", "yes"))
        lines.append(f"| {arm} | {n} | {pct(read_ok, n)} | {pct(write_ok, n)} | {pct(task_ok, n)} |")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    text = aggregate(args.runs)
    args.out.write_text(text, encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
