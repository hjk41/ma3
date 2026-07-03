#!/usr/bin/env python3
"""Parse ma3 op-log JSONL and summarize MCP tool usage for an eval run."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MCP_TOOLS = ("ma3_context", "ma3_report", "ma3_validate", "ma3_whoami", "ma3_doctor")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Summarize ma3 MCP calls from op logs")
    p.add_argument("--log-dir", default=None, help="MA3_OP_LOG_DIR (default: ma3/data/ops)")
    p.add_argument("--since-line", type=int, default=0, help="Start line offset in today's log")
    p.add_argument("--run-id", default=None, help="Optional run_id filter in payload")
    return p.parse_args()


def find_log_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    candidates = [
        Path("/home/hct/ma3/data/ops"),
        Path(__file__).resolve().parents[2] / "data" / "ops",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    raise SystemExit("op log dir not found; set --log-dir")


def main() -> int:
    args = parse_args()
    log_dir = find_log_dir(args.log_dir)
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = log_dir / f"{today}.jsonl"
    if not log_file.exists():
        print(json.dumps({"error": "log_missing", "path": str(log_file), "counts": {}}))
        return 0

    counts: dict[str, int] = {t: 0 for t in MCP_TOOLS}
    latencies: dict[str, list[float]] = {t: [] for t in MCP_TOOLS}
    lines_read = 0

    with log_file.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i < args.since_line:
                continue
            lines_read += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("event_type") != "mcp_tool_call":
                continue
            tool = row.get("tool", "")
            if tool in counts:
                counts[tool] += 1
                if row.get("latency_ms") is not None:
                    latencies[tool].append(float(row["latency_ms"]))

    summary = {
        "log_file": str(log_file),
        "since_line": args.since_line,
        "lines_scanned": lines_read,
        "counts": counts,
        "avg_latency_ms": {
            k: (sum(v) / len(v) if v else None) for k, v in latencies.items()
        },
        "called_ma3_context": counts["ma3_context"] > 0,
        "called_ma3_report": counts["ma3_report"] > 0,
        "called_ma3_validate": counts["ma3_validate"] > 0,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
