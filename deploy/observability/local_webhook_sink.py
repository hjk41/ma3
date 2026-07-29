#!/usr/bin/env python3
"""Local webhook sink + optional Feishu (Lark) forwarder for ma3-probe.

Listens on 127.0.0.1 only. Always appends each POST to a JSONL log.
When FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_CHAT_ID are set, also sends
a text message via Feishu Open API (tenant_access_token).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = os.environ.get("MA3_ALERT_SINK_HOST", "127.0.0.1")
PORT = int(os.environ.get("MA3_ALERT_SINK_PORT", "8787"))
LOG_PATH = Path(os.environ.get("MA3_ALERT_SINK_LOG", "/var/log/ma3/probe-alerts.jsonl"))

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "").strip()
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "").strip()
FEISHU_CHAT_ID = os.environ.get("FEISHU_CHAT_ID", "").strip()
# Comma-separated extra chat ids (optional)
FEISHU_CHAT_IDS = [
    c.strip()
    for c in os.environ.get("FEISHU_CHAT_IDS", FEISHU_CHAT_ID).split(",")
    if c.strip()
]
FEISHU_API = os.environ.get("FEISHU_API_BASE", "https://open.feishu.cn").rstrip("/")

_token: str | None = None
_token_expire_at = 0.0


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json; charset=utf-8")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body}") from e
    return json.loads(body) if body else {}


def get_tenant_token() -> str:
    global _token, _token_expire_at
    now = time.time()
    if _token and now < _token_expire_at - 60:
        return _token
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        raise RuntimeError("FEISHU_APP_ID/SECRET not configured")
    d = _http_json(
        "POST",
        f"{FEISHU_API}/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
    )
    if d.get("code") not in (0, None) and "tenant_access_token" not in d:
        raise RuntimeError(f"token error: {d}")
    token = d.get("tenant_access_token")
    if not token:
        raise RuntimeError(f"token missing: {d}")
    _token = token
    _token_expire_at = now + float(d.get("expire") or 7200)
    return token


def format_alert_text(payload: dict[str, Any]) -> str:
    event = str(payload.get("event") or "ma3_alert")
    detail = str(payload.get("detail") or "")
    base = str(payload.get("base_url") or "")
    instance = str(payload.get("instance_id") or "")
    ts = str(payload.get("ts") or "")
    if event == "ma3_probe_fail":
        title = "🔴 ma3 probe FAIL"
    elif event == "ma3_probe_recover":
        title = "🟢 ma3 probe RECOVERED"
    else:
        title = f"ℹ️ ma3 {event}"
    lines = [title, f"instance: {instance}", f"base_url: {base}", f"detail: {detail}", f"ts: {ts}"]
    return "\n".join(lines)


def send_feishu_text(text: str) -> list[dict[str, Any]]:
    if not FEISHU_CHAT_IDS:
        return []
    token = get_tenant_token()
    results = []
    for chat_id in FEISHU_CHAT_IDS:
        d = _http_json(
            "POST",
            f"{FEISHU_API}/open-apis/im/v1/messages?receive_id_type=chat_id",
            {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        results.append({"chat_id": chat_id, "code": d.get("code"), "msg": d.get("msg")})
        if d.get("code") not in (0, None):
            raise RuntimeError(f"send to {chat_id} failed: {d}")
    return results


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {"raw": raw.decode("utf-8", errors="replace")}

        feishu_status: dict[str, Any] = {"skipped": True}
        if FEISHU_APP_ID and FEISHU_APP_SECRET and FEISHU_CHAT_IDS:
            try:
                text = format_alert_text(payload if isinstance(payload, dict) else {"detail": str(payload)})
                results = send_feishu_text(text)
                feishu_status = {"ok": True, "results": results}
            except Exception as e:
                feishu_status = {"ok": False, "error": str(e)}

        line = {
            "received_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "path": self.path,
            "payload": payload,
            "feishu": feishu_status,
        }
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        print(json.dumps(line, ensure_ascii=False), flush=True)

        body = json.dumps({"ok": True, "feishu": feishu_status}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        info = {
            "service": "ma3-alert-sink",
            "ok": True,
            "feishu_configured": bool(FEISHU_APP_ID and FEISHU_APP_SECRET and FEISHU_CHAT_IDS),
            "chat_count": len(FEISHU_CHAT_IDS),
        }
        body = json.dumps(info, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(
        f"ma3-alert-sink listening on http://{HOST}:{PORT} log={LOG_PATH} "
        f"feishu={'on' if FEISHU_CHAT_IDS else 'off'}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
