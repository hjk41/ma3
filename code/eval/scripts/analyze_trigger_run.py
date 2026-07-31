#!/usr/bin/env python3
"""Parse Cursor agent transcript JSONL for trigger experiment metrics."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MUTATING_SHELL = re.compile(
    r"\b(curl|wget|pip3?|npm|apt-get|apt |brew|docker|droid|sed -i|tee |systemctl|cp |mv |chmod)\b",
    re.I,
)
READ_ONLY_SHELL = re.compile(
    r"^\s*(ls|cat|head|tail|find|tree|git status|git diff|grep|pwd|echo)\b",
    re.I,
)
MA3_READ = re.compile(r"ma3_context|mcp_ma3_ma3_context|ma3___ma3_context", re.I)
MA3_WRITE = re.compile(
    r"ma3_report|ma3_feedback|ma3_validate|mcp_ma3_ma3_(report|feedback|validate)|ma3___ma3_(report|feedback|validate)",
    re.I,
)


@dataclass
class TriggerMetrics:
    scenario: str
    transcript: str
    session_id: str | None
    ma3_context_calls: int
    ma3_write_calls: int
    write_tools: list[str]
    shell_commands: list[str]
    first_context_idx: int | None
    first_mutating_idx: int | None
    read_before_mutation: bool | None
    false_read: bool
    read_quality_ok: bool | None
    notes: str


def find_transcript(session_id: str, search_roots: list[Path]) -> Path | None:
    for root in search_roots:
        if not root.exists():
            continue
        direct = root / session_id / f"{session_id}.jsonl"
        if direct.is_file():
            return direct
        flat = root / f"{session_id}.jsonl"
        if flat.is_file():
            return flat
        for hit in root.glob(f"**/{session_id}.jsonl"):
            return hit
    return None


def iter_actions_cursor(events: list[dict]) -> list[dict]:
    actions: list[dict] = []
    for ev in events:
        msg = ev.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "tool_use":
                name = str(part.get("name") or "")
                inp = part.get("input") or {}
                actions.append({"kind": "tool", "name": name, "input": inp})
            elif part.get("type") == "text":
                text = part.get("text") or ""
                if text.strip():
                    actions.append({"kind": "text", "text": text[:500]})
    return actions


def iter_actions_factory(events: list[dict]) -> list[dict]:
    actions: list[dict] = []
    for ev in events:
        if ev.get("type") != "message":
            continue
        msg = ev.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "tool_use":
                continue
            name = str(part.get("name") or "")
            inp = part.get("input") or {}
            actions.append({"kind": "tool", "name": name, "input": inp})
    return actions


def iter_actions_claude(events: list[dict]) -> list[dict]:
    actions: list[dict] = []
    for ev in events:
        if ev.get("type") != "assistant":
            continue
        msg = ev.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "tool_use":
                continue
            name = str(part.get("name") or "")
            inp = part.get("input") or {}
            actions.append({"kind": "tool", "name": name, "input": inp})
    return actions


def iter_actions(events: list[dict]) -> list[dict]:
    factory = sum(1 for e in events if e.get("type") == "message" and (e.get("message") or {}).get("role") == "assistant")
    claude = sum(1 for e in events if e.get("type") == "assistant")
    cursor = sum(1 for e in events if isinstance((e.get("message") or {}).get("content"), list))
    if factory >= claude and factory >= cursor and factory > 0:
        return iter_actions_factory(events)
    if claude > cursor and claude > 0:
        return iter_actions_claude(events)
    return iter_actions_cursor(events)


def is_mutating_tool(name: str, inp: dict) -> bool:
    low = name.lower()
    if low in ("write", "search_replace", "editnotebook", "delete", "applypatch", "create", "edit"):
        return True
    if low in ("execute", "shell", "bash"):
        cmd = str(inp.get("command") or "")
        if not cmd.strip():
            return False
        if READ_ONLY_SHELL.match(cmd.strip()):
            return False
        if MUTATING_SHELL.search(cmd):
            return True
        if any(x in cmd for x in (">", ">>", "| tee")):
            return True
    if low == "shell":
        cmd = str(inp.get("command") or "")
        if not cmd.strip():
            return False
        if READ_ONLY_SHELL.match(cmd.strip()):
            return False
        if MUTATING_SHELL.search(cmd):
            return True
        # non-read-only shell defaults to mutating if it writes files
        if any(x in cmd for x in (">", ">>", "| tee")):
            return True
    if "websearch" in low or low == "web_fetch":
        return True
    return False


def is_ma3_read(name: str) -> bool:
    return bool(MA3_READ.search(name))


def is_ma3_write(name: str) -> bool:
    return bool(MA3_WRITE.search(name))


def context_quality(inp: dict) -> bool:
    if not isinstance(inp, dict):
        return False
    problem = str(inp.get("problem") or "").strip()
    if len(problem) < 8:
        return False
    has_target = any(
        str(inp.get(k) or "").strip()
        for k in ("target", "target_product", "target_component", "task_type", "goal")
    )
    return has_target or len(problem) >= 20


def analyze_transcript(path: Path, scenario: str, expects_read: bool) -> TriggerMetrics:
    events = []
    session_id = path.parent.name
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    actions = iter_actions(events)
    ctx_indices = [i for i, a in enumerate(actions) if a["kind"] == "tool" and is_ma3_read(a["name"])]
    write_tools = [a["name"] for a in actions if a["kind"] == "tool" and is_ma3_write(a["name"])]
    mut_indices = [
        i for i, a in enumerate(actions) if a["kind"] == "tool" and is_mutating_tool(a["name"], a.get("input") or {})
    ]
    shells = [
        str(a.get("input", {}).get("command") or "")
        for a in actions
        if a["kind"] == "tool" and a["name"].lower() in ("shell", "execute", "bash")
    ]

    first_ctx = ctx_indices[0] if ctx_indices else None
    first_mut = mut_indices[0] if mut_indices else None
    read_before = None
    if expects_read:
        if first_mut is None:
            read_before = first_ctx is not None
        else:
            read_before = first_ctx is not None and first_ctx < first_mut
    else:
        read_before = first_ctx is None

    quality = None
    if ctx_indices:
        first_ctx_action = actions[ctx_indices[0]]
        quality = context_quality(first_ctx_action.get("input") or {})

    return TriggerMetrics(
        scenario=scenario,
        transcript=str(path),
        session_id=session_id,
        ma3_context_calls=len(ctx_indices),
        ma3_write_calls=len(write_tools),
        write_tools=write_tools,
        shell_commands=shells,
        first_context_idx=first_ctx,
        first_mutating_idx=first_mut,
        read_before_mutation=read_before,
        false_read=bool(not expects_read and ctx_indices),
        read_quality_ok=quality,
        notes="",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--expects-read", choices=("yes", "no"), default="yes")
    parser.add_argument(
        "--search-root",
        action="append",
        default=[
            str(Path.home() / ".cursor/projects/home-hct-ma3/agent-transcripts"),
            str(Path.home() / ".cursor/projects"),
            str(Path.home() / ".factory/sessions"),
            str(Path.home() / ".claude/projects"),
        ],
    )
    args = parser.parse_args()

    path = args.transcript
    if path is None:
        if not args.session_id:
            print("need --transcript or --session-id", file=sys.stderr)
            return 1
        path = find_transcript(args.session_id, [Path(p) for p in args.search_root])
        if path is None:
            print(json.dumps({"error": "transcript_not_found", "session_id": args.session_id}))
            return 1

    metrics = analyze_transcript(path, args.scenario, expects_read=args.expects_read == "yes")
    print(json.dumps(asdict(metrics), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
