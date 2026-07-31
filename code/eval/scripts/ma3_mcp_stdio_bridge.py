#!/usr/bin/env python3
"""Minimal stdio MCP <-> HTTP JSON-RPC bridge for Codex (adds X-API-Key)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

URL = os.environ.get("MA3_MCP_URL", "http://127.0.0.1:8010/mcp").rstrip("/")
API_KEY = os.environ.get("MA3_API_KEY", "")


def post(payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            if body.startswith("event:") or "data:" in body.split("\n", 1)[0]:
                # naive SSE: take last data: line
                for line in reversed(body.splitlines()):
                    if line.startswith("data:"):
                        return json.loads(line[5:].strip())
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id"),
            "error": {"code": e.code, "message": err[:500]},
        }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        # notifications: still forward
        out = post(msg)
        if out:
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
