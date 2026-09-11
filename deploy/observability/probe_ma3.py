#!/usr/bin/env python3
"""Cross-platform off-host probe for ma3 SaaS (Phase 0 observability).

Mirrors deploy/observability/probe_ma3.sh. Run every ~60s from a host other than
the ma3.io application server.

Required env:
  MA3_BASE_URL
  MA3_EXPECT_INSTANCE_ID

Optional env:
  MA3_EXPECT_PUBLIC_BASE_URL (default: MA3_BASE_URL)
  MA3_PROBE_STATE_DIR
  MA3_PROBE_FAIL_THRESHOLD (default: 3)
  MA3_PROBE_WEBHOOK_URL
  MA3_PROBE_DOCTOR=1 (needs MA3_API_KEY)
  MA3_API_KEY
  MA3_PROBE_DRY_RUN=1

Exit: 0 = ok this tick; 1 = failed this tick.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def default_state_dir() -> Path:
    override = env("MA3_PROBE_STATE_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "ma3-probe"
    return Path("/var/tmp/ma3-probe")


def read_fails(path: Path) -> int:
    if not path.is_file():
        return 0
    raw = path.read_text(encoding="utf-8").strip()
    return int(raw) if raw.isdigit() else 0


def write_fails(path: Path, count: int) -> None:
    path.write_text(str(count), encoding="ascii")


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def notify(
    event: str,
    detail: str,
    *,
    base_url: str,
    instance_id: str,
    webhook_url: str,
    dry_run: bool,
) -> None:
    body = json.dumps(
        {
            "event": event,
            "service": "ma3",
            "base_url": base_url,
            "instance_id": instance_id,
            "detail": detail,
            "ts": utc_ts(),
        },
        ensure_ascii=False,
    )
    print(f"{utc_ts()} notify event={event} detail={detail}", flush=True)
    if not webhook_url:
        print(f"{utc_ts()} WARN: MA3_PROBE_WEBHOOK_URL unset; notification skipped", file=sys.stderr, flush=True)
        return
    if dry_run:
        print(f"DRY_RUN webhook body: {body}", flush=True)
        return
    try:
        http_json("POST", webhook_url, json.loads(body), timeout=15)
    except Exception as exc:
        print(f"{utc_ts()} WARN: webhook POST failed: {exc}", file=sys.stderr, flush=True)


def check_healthz(base_url: str, expect_instance_id: str, expect_public_base_url: str) -> str | None:
    try:
        health = http_json("GET", f"{base_url}/healthz", timeout=15)
    except Exception:
        return "healthz unreachable"

    errs: list[str] = []
    if health.get("status") != "ok":
        errs.append(f"status={health.get('status')}")
    if health.get("instance_id") != expect_instance_id:
        errs.append(f"instance_id={health.get('instance_id')}")
    if health.get("public_base_url") != expect_public_base_url:
        errs.append(f"public_base_url={health.get('public_base_url')}")
    if "dev_auth" in set(health.get("features") or []):
        errs.append("dev_auth present")
    return "; ".join(errs) if errs else None


def mcp_call(base_url: str, tool: str, api_key: str = "", timeout: int = 20) -> dict[str, Any]:
    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": {}},
    }
    return http_json("POST", f"{base_url}/mcp", payload, headers=headers, timeout=timeout)


def check_whoami(base_url: str) -> str | None:
    try:
        resp = mcp_call(base_url, "ma3_whoami")
    except Exception:
        return "mcp whoami unreachable"
    if resp.get("error"):
        return json.dumps(resp["error"], ensure_ascii=False)
    if "result" not in resp:
        return "missing result"
    return None


def check_doctor(base_url: str, api_key: str) -> str | None:
    if not api_key:
        return "doctor requested but MA3_API_KEY unset"
    try:
        resp = mcp_call(base_url, "ma3_doctor", api_key=api_key, timeout=30)
    except Exception:
        return "mcp doctor unreachable"
    if resp.get("error"):
        return json.dumps(resp["error"], ensure_ascii=False)

    result = resp.get("result") or {}
    sc = result.get("structuredContent") or {}
    if sc.get("ok") is False:
        return json.dumps(sc, ensure_ascii=False)

    checks = sc.get("checks") or sc.get("doctor") or {}
    if isinstance(checks, dict):
        bad: list[str] = []
        for key, value in checks.items():
            if isinstance(value, dict) and value.get("ok") is False:
                bad.append(key)
            elif value in ("fail", "error", False):
                bad.append(key)
        if bad:
            return "doctor checks failed: " + ",".join(bad)
    return None


def main() -> int:
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)

    base_url = env("MA3_BASE_URL").rstrip("/")
    expect_instance_id = env("MA3_EXPECT_INSTANCE_ID")
    if not base_url:
        print("set MA3_BASE_URL", file=sys.stderr)
        return 1
    if not expect_instance_id:
        print("set MA3_EXPECT_INSTANCE_ID", file=sys.stderr)
        return 1

    expect_public_base_url = env("MA3_EXPECT_PUBLIC_BASE_URL", base_url)
    state_dir = default_state_dir()
    fail_threshold = int(env("MA3_PROBE_FAIL_THRESHOLD", "3") or "3")
    webhook_url = env("MA3_PROBE_WEBHOOK_URL")
    doctor = env("MA3_PROBE_DOCTOR") == "1"
    api_key = env("MA3_API_KEY")
    dry_run = env("MA3_PROBE_DRY_RUN") == "1"

    state_dir.mkdir(parents=True, exist_ok=True)
    fail_file = state_dir / "consecutive_fails"
    notified_file = state_dir / "notified"
    last_err_file = state_dir / "last_error.txt"

    err = check_healthz(base_url, expect_instance_id, expect_public_base_url)
    if not err:
        err = check_whoami(base_url)
    if not err and doctor:
        err = check_doctor(base_url, api_key)

    if err:
        line = f"{utc_ts()} FAIL {err}"
        print(line, file=sys.stderr, flush=True)
        last_err_file.write_text(line + "\n", encoding="utf-8")
        fails = read_fails(fail_file) + 1
        write_fails(fail_file, fails)
        if fails >= fail_threshold and not notified_file.exists():
            notify(
                "ma3_probe_fail",
                f"{err} (consecutive={fails})",
                base_url=base_url,
                instance_id=expect_instance_id,
                webhook_url=webhook_url,
                dry_run=dry_run,
            )
            notified_file.touch()
        return 1

    suffix = " +doctor" if doctor else ""
    print(f"{utc_ts()} OK healthz+whoami{suffix} instance={expect_instance_id}", flush=True)
    prev = read_fails(fail_file)
    write_fails(fail_file, 0)
    if notified_file.exists():
        notify(
            "ma3_probe_recover",
            f"recovered after consecutive_fails={prev}",
            base_url=base_url,
            instance_id=expect_instance_id,
            webhook_url=webhook_url,
            dry_run=dry_run,
        )
        notified_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
