#!/usr/bin/env python3
"""Append parallel matrix progress snapshot."""
from __future__ import annotations

import csv
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

CSV = Path("/home/hct/ma3/code/eval/results/trigger/runs.csv")
LOG = Path("/home/hct/ma3/code/eval/results/trigger/experiment-matrix.log")
OUT = Path("/home/hct/ma3/code/eval/results/trigger/progress.log")

text = LOG.read_text(errors="replace") if LOG.exists() else ""
rows = list(csv.DictReader(CSV.open())) if CSV.exists() else []
non_b0 = [r for r in rows if r.get("arm") != "B0-local-skill-mcp"]
by_arm: dict[str, int] = defaultdict(int)
for r in non_b0:
    by_arm[r["arm"]] += 1

dones = re.findall(r"\] DONE (\S+)", text)
fails = re.findall(r"\] FAIL (\S+)", text)
runs = re.findall(r"\] RUN (\S+) \(worker=(\d+)\)", text)
durations = [int(m.group(1)) for m in re.finditer(r"^done \S+ task_pass=\d+ duration=(\d+)s", text, re.M)]
avg = sum(durations) / len(durations) if durations else 0
pending = max(0, 378 - len(non_b0))  # 7 arms × 3 rt × 6 sc × 3 rounds
eta_h = pending * avg / 3600 / 4 if avg else 0  # rough 4-way speedup
running = subprocess.run(["pgrep", "-f", "run_trigger_parallel_matrix.py"], capture_output=True).returncode == 0
active = len(subprocess.run(["pgrep", "-f", "run_trigger_cell.sh"], capture_output=True, text=True).stdout.strip().splitlines())

line = (
    f"{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')} "
    f"CSV={len(rows)} nonB0={len(non_b0)}/378 DONE_log={len(dones)} FAIL_log={len(fails)} "
    f"avg={avg:.0f}s eta~{eta_h:.1f}h sched={'on' if running else 'off'} workers={active}"
)
if runs:
    line += f" last_RUN={runs[-1][0]}@w{runs[-1][1]}"
if dones:
    line += f" last_DONE={dones[-1]}"
print(line)
OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("a", encoding="utf-8") as f:
    f.write(line + "\n")
for arm, cnt in sorted(by_arm.items()):
    print(f"  {arm}: {cnt}")
