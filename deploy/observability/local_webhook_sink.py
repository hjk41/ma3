#!/usr/bin/env python3
"""Minimal local webhook sink for ma3-probe alerts (Phase 0 on host 202).

Listens on 127.0.0.1 only; appends each POST body as one JSON line to a log file.
Not for public exposure.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.environ.get("MA3_ALERT_SINK_HOST", "127.0.0.1")
PORT = int(os.environ.get("MA3_ALERT_SINK_PORT", "8787"))
LOG_PATH = Path(os.environ.get("MA3_ALERT_SINK_LOG", "/var/log/ma3/probe-alerts.jsonl"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # quieter access log
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {"raw": raw.decode("utf-8", errors="replace")}
        line = {
            "received_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "path": self.path,
            "payload": payload,
        }
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        # Also mirror to journald via stderr for `journalctl -u ma3-alert-sink`
        print(json.dumps(line, ensure_ascii=False), flush=True)
        body = b'{"ok":true}\n'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        body = b'{"service":"ma3-alert-sink","ok":true}\n'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"ma3-alert-sink listening on http://{HOST}:{PORT} log={LOG_PATH}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
