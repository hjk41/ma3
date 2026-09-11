#!/usr/bin/env bash
set -euo pipefail
cd /home/hct/ma3
export PATH="$HOME/.local/bin:$PATH"
OUT=/tmp/codex_ma3_connect.out
ERR=/tmp/codex_ma3_connect.err
MSG=/tmp/codex_ma3_connect.last.txt
rm -f "$OUT" "$ERR" "$MSG"

# IMPORTANT: close stdin so `codex exec` does not wait for piped input over SSH.
codex exec \
  --skip-git-repo-check \
  --ephemeral \
  --dangerously-bypass-approvals-and-sandbox \
  -m deepseek-flash \
  --json \
  -o "$MSG" \
  "请帮我接入 ma3.io 的 ma3 MCP（Codex）。规则：Base 已是 https://ma3.io，禁止再问 URL；MCP 必须是 https://ma3.io/mcp。先 curl -fsSL https://ma3.io/client/connect.md。然后直接调用 MCP 工具 ma3_whoami 验证。不要编造 API key。最终只输出一行：WHOAMI_OK 或 WHOAMI_FAIL 以及简短原因。" \
  </dev/null >"$OUT" 2>"$ERR" || true

python3 - <<'PY'
import json, re
from pathlib import Path

def red(s: str) -> str:
    s = re.sub(r"ma3k_[A-Za-z0-9]+", "ma3k_REDACTED", s)
    s = re.sub(r"ma3mcp_[A-Za-z0-9]+", "ma3mcp_REDACTED", s)
    return s

out = Path("/tmp/codex_ma3_connect.out").read_text(encoding="utf-8", errors="replace")
err = Path("/tmp/codex_ma3_connect.err").read_text(encoding="utf-8", errors="replace")
msg = Path("/tmp/codex_ma3_connect.last.txt")
print("OUT_BYTES", len(out), "ERR_BYTES", len(err))
print("=== LAST MESSAGE ===")
print(red(msg.read_text(encoding="utf-8", errors="replace")[:2000]) if msg.exists() else "(missing)")
print("=== ERR TAIL ===")
print(red(err)[-2000:])
print("=== KEY EVENTS ===")
for line in out.splitlines():
    if not line.startswith("{"):
        continue
    try:
        o = json.loads(line)
    except Exception:
        continue
    blob = json.dumps(o, ensure_ascii=False)
    keep = any(
        k in blob
        for k in (
            "ma3_whoami",
            "WHOAMI",
            "agent_message",
            "error",
            "mcp_tool",
            "tool_call",
            "turn.completed",
            "task_complete",
        )
    )
    if keep:
        print(o.get("type"), red(blob)[:500])
PY
