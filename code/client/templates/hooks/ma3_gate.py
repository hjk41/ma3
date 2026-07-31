#!/usr/bin/env python3
"""Cursor hook: deny-once before mutating shell if ma3_context not yet called (fail-open)."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

STATE_DIR = Path(os.environ.get("MA3_HOOK_STATE_DIR", Path.home() / ".ma3" / "session-state"))
LOG_PATH = Path(os.environ.get("MA3_HOOK_LOG", Path.home() / ".ma3" / "logs" / "hooks.jsonl"))

MUTATING = re.compile(
    r"\b(curl|wget|pip3?|npm|apt-get|\bapt\b|brew|docker|droid|sed -i|tee |systemctl|cp |mv |chmod)\b",
    re.I,
)
READ_ONLY = re.compile(
    r"^\s*(ls|cat|head|tail|find|tree|git status|git diff|grep|pwd|echo|python3 -c|wc |stat )\b",
    re.I,
)
CONTEXT_TOOLS = re.compile(r"ma3_context|ma3___ma3_context", re.I)


def _log(entry: dict) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _session_id(payload: dict) -> str:
    for key in ("session_id", "conversation_id", "sessionId", "conversationId"):
        val = payload.get(key)
        if val:
            return str(val)
    return "unknown"


def _state_path(session: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", session)
    return STATE_DIR / f"{safe}.json"


def _load_state(session: str) -> dict:
    path = _state_path(session)
    if not path.is_file():
        return {"context_called": False, "denied_once": False}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"context_called": False, "denied_once": False}


def _save_state(session: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = time.time()
    _state_path(session).write_text(json.dumps(state), encoding="utf-8")


def _is_mutating(command: str) -> bool:
    cmd = command.strip()
    if not cmd:
        return False
    if READ_ONLY.match(cmd):
        return False
    if MUTATING.search(cmd):
        return True
    if any(x in cmd for x in (">", ">>", "| tee")):
        return True
    return False


def _allow() -> None:
    print(json.dumps({"permission": "allow"}))
    sys.exit(0)


def _deny(agent_message: str) -> None:
    print(
        json.dumps(
            {
                "permission": "deny",
                "user_message": "ma3 policy: call ma3_context before mutating commands.",
                "agent_message": agent_message,
            }
        )
    )
    sys.exit(0)


def handle_before_shell(payload: dict) -> None:
    session = _session_id(payload)
    command = str(payload.get("command") or "")
    state = _load_state(session)
    if state.get("context_called"):
        _log({"event": "beforeShellExecution", "session": session, "result": "allow_context_ok", "command": command[:200]})
        _allow()
    if not _is_mutating(command):
        _log({"event": "beforeShellExecution", "session": session, "result": "allow_readonly", "command": command[:200]})
        _allow()
    if state.get("denied_once"):
        _log({"event": "beforeShellExecution", "session": session, "result": "allow_after_deny_once", "command": command[:200]})
        _allow()
    state["denied_once"] = True
    _save_state(session, state)
    _log({"event": "beforeShellExecution", "session": session, "result": "deny_once", "command": command[:200]})
    _deny(
        "Stop: call ma3_context with a real problem/target before this mutating shell command. "
        "This is a one-time deny; after you call ma3_context, mutating commands will be allowed."
    )


def handle_after_mcp(payload: dict) -> None:
    session = _session_id(payload)
    tool = str(payload.get("tool_name") or payload.get("tool") or payload.get("name") or "")
    if not CONTEXT_TOOLS.search(tool):
        _allow()
    state = _load_state(session)
    state["context_called"] = True
    _save_state(session, state)
    _log({"event": "afterMCPExecution", "session": session, "result": "context_marked", "tool": tool})
    _allow()


def main() -> None:
    hook_event = os.environ.get("CURSOR_HOOK_EVENT", "")
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        _log({"event": hook_event or "unknown", "result": "fail_open_allow", "error": "bad_json"})
        _allow()

    try:
        if hook_event == "beforeShellExecution" or payload.get("hook_event_name") == "beforeShellExecution":
            handle_before_shell(payload)
        elif hook_event in ("afterMCPExecution", "postToolUse") or "mcp" in hook_event.lower():
            handle_after_mcp(payload)
        else:
            # Infer from payload shape
            if "command" in payload:
                handle_before_shell(payload)
            else:
                _allow()
    except Exception as exc:  # noqa: BLE001 — fail-open by design
        _log({"event": hook_event or "unknown", "result": "fail_open_allow", "error": str(exc)})
        _allow()


if __name__ == "__main__":
    main()
