#!/usr/bin/env python3
"""Fix malformed B0 row in runs.csv and append clean B0 P1-r1 if missing."""
import csv
from pathlib import Path

csv_path = Path(__file__).resolve().parents[1] / "results/trigger/runs.csv"
rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
fields = [
    "run_id", "arm", "runtime", "prompt_id", "scenario_id", "started_at", "session_id",
    "seeded_record_ids", "read_before_mutation", "read_quality", "kb_used",
    "write_occurred", "write_correct", "task_pass", "false_read", "hook_false_block",
    "duration_s", "notes",
]

clean = []
for r in rows:
    if r.get("run_id", "").startswith("B0-local") and "target_product" in str(r.values()):
        clean.append({
            "run_id": "B0-local-skill-mcp-cursor-agent-trigger-p1-r1",
            "arm": "B0-local-skill-mcp",
            "runtime": "cursor-agent",
            "prompt_id": "P1",
            "scenario_id": "trigger-p1",
            "started_at": "2026-07-08T07:14:15Z",
            "session_id": "e81c8a5a-6bca-4ae6-a397-ba89c248be2b",
            "seeded_record_ids": "vk_94552aa6b96e",
            "read_before_mutation": "1",
            "read_quality": "1",
            "kb_used": "",
            "write_occurred": "1",
            "write_correct": "1",
            "task_pass": "1",
            "false_read": "0",
            "hook_false_block": "",
            "duration_s": "198",
            "notes": "ctx=1 write=1 mut=4",
        })
    elif not any("target_product" in str(v) for v in r.values()):
        # normalize old rows missing started_at column
        if "2026-" in r.get("session_id", ""):
            continue  # drop broken row
        clean.append({f: r.get(f, r.get({
            "seeded_record_ids": "seeded_record_ids",
        }.get(f, f), "")) for f in fields})

# map old column names
fixed = []
for r in rows:
    if r.get("run_id", "").startswith("B0-local") and "target_product" in str(r.values()):
        continue
    if "2026-" in (r.get("session_id") or ""):
        continue
    out = {f: "" for f in fields}
    for k, v in r.items():
        if k in out:
            out[k] = v
        elif k == "seeded_record_ids":
            out["seeded_record_ids"] = v
    if out["run_id"]:
        fixed.append(out)

# add clean B0 p1-r1 if not present
ids = {r["run_id"] for r in fixed}
if "B0-local-skill-mcp-cursor-agent-trigger-p1-r1" not in ids:
    fixed.append({
        "run_id": "B0-local-skill-mcp-cursor-agent-trigger-p1-r1",
        "arm": "B0-local-skill-mcp",
        "runtime": "cursor-agent",
        "prompt_id": "P1",
        "scenario_id": "trigger-p1",
        "started_at": "2026-07-08T07:14:15Z",
        "session_id": "e81c8a5a-6bca-4ae6-a397-ba89c248be2b",
        "seeded_record_ids": "vk_94552aa6b96e",
        "read_before_mutation": "1",
        "read_quality": "1",
        "kb_used": "",
        "write_occurred": "1",
        "write_correct": "1",
        "task_pass": "1",
        "false_read": "0",
        "hook_false_block": "",
        "duration_s": "198",
        "notes": "ctx=1 write=1 mut=4",
    })

with csv_path.open("w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(fixed)
print(f"fixed {len(fixed)} rows")
