#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    return xs[round((len(xs) - 1) * p)]


def load_requests(path: Path) -> list[dict[str, Any]]:
    reqs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            reqs.append(json.loads(line))
    return reqs


def count_results(route: str, body: Any) -> int:
    if not isinstance(body, dict):
        return 0
    if route == "/search":
        return len(body.get("primary_records") or []) + len(body.get("contrasting_records") or [])
    cases = body.get("cases") or []
    ungrouped = body.get("ungrouped_records") or []
    return sum(len(case.get("records") or []) for case in cases) + len(ungrouped)


def post_json(base_url: str, route: str, payload: dict, api_key: str | None, timeout: float) -> tuple[int, float, Any, str | None]:
    url = base_url.rstrip("/") + route
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("X-API-Key", api_key)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                body = raw.decode("utf-8", errors="replace")[:500]
            return resp.status, elapsed_ms, body, None
    except urllib.error.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        raw = exc.read().decode("utf-8", errors="replace")[:1000]
        return exc.code, elapsed_ms, raw, raw
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return 0, elapsed_ms, None, repr(exc)


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row["phase"] == "measure":
            by_name.setdefault(row["name"], []).append(row)
    for name, items in sorted(by_name.items()):
        lat = [float(item["latency_ms"]) for item in items]
        statuses = {}
        for item in items:
            statuses[str(item["status"])] = statuses.get(str(item["status"]), 0) + 1
        out.append({
            "name": name,
            "route": items[0]["route"],
            "count": len(items),
            "avg_ms": round(statistics.mean(lat), 3) if lat else 0.0,
            "p50_ms": round(pct(lat, 0.50), 3),
            "p95_ms": round(pct(lat, 0.95), 3),
            "max_ms": round(max(lat), 3) if lat else 0.0,
            "statuses": statuses,
            "avg_result_count": round(statistics.mean([item["result_count"] for item in items]), 3) if items else 0.0,
            "errors": sum(1 for item in items if item.get("error")),
        })
    return out


def write_markdown(path: Path, label: str, base_url: str, summary: list[dict[str, Any]]) -> None:
    lines = [
        f"# ma3 search performance benchmark: {label}",
        "",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"- base_url: `{base_url}`",
        "",
        "| request | route | n | avg ms | p50 ms | p95 ms | max ms | statuses | avg results | errors |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for item in summary:
        lines.append(
            f"| {item['name']} | `{item['route']}` | {item['count']} | {item['avg_ms']} | {item['p50_ms']} | {item['p95_ms']} | {item['max_ms']} | `{json.dumps(item['statuses'], sort_keys=True)}` | {item['avg_result_count']} | {item['errors']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--requests", default=str(Path(__file__).resolve().parents[1] / "benchmarks" / "perf_requests.jsonl"))
    ap.add_argument("--label", default="benchmark")
    ap.add_argument("--warmups", type=int, default=5)
    ap.add_argument("--iterations", type=int, default=20)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--output-dir", default="reports/perf")
    ap.add_argument("--api-key", default=os.environ.get("MA3_API_KEY"))
    args = ap.parse_args()

    requests = load_requests(Path(args.requests))
    rows = []
    for phase, reps in [("warmup", args.warmups), ("measure", args.iterations)]:
        for _ in range(reps):
            for item in requests:
                status, elapsed_ms, body, error = post_json(args.base_url, item["route"], item["payload"], args.api_key, args.timeout)
                rows.append({
                    "phase": phase,
                    "name": item["name"],
                    "route": item["route"],
                    "status": status,
                    "latency_ms": round(elapsed_ms, 3),
                    "result_count": count_results(item["route"], body),
                    "error": error,
                })
    summary = summarize(rows)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{ts}_{args.label}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps({"label": args.label, "base_url": args.base_url, "summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, args.label, args.base_url, summary)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "summary": summary}, ensure_ascii=False, indent=2))
    return 0 if all(item["errors"] == 0 for item in summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
