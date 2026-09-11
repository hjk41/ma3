#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$HOME/ma3"
OUT=/tmp/codex_clawhub_ma3.out
ERR=/tmp/codex_clawhub_ma3.err
MSG=/tmp/codex_clawhub_ma3.last.txt
rm -f "$OUT" "$ERR" "$MSG"

PROMPT='请完成 ClawHub ma3 bundle 验证（Codex on 202）。

背景：本机已用 clawhub package inspect 拉取 ma3 bundle 的 mcp.json + SKILL.md，并写入 Codex MCP（https://ma3.io/mcp）与 ~/.codex/skills/ma3/SKILL.md。

我明确同意：本次任务允许使用 ma3（检索 + 写回）。

请：
1) 先确认能调用 MCP 工具 ma3_whoami
2) 调用 ma3_context，problem 类似「Codex on LAN host installing ma3 via ClawHub bundle」
3) 在 /tmp/ma3-clawhub-smoke-codex/ 创建 hello.txt（写入时间戳）
4) 调用 ma3_report 真实写入个人库（非 dry-run），记录 record_id
5) 最终只输出：
INSTALL_OK=yes|no
MCP_CONNECTED=yes|no
CALLED_CONTEXT=yes|no
CALLED_REPORT=yes|no
RECORD_ID=...
NOTES=...'

# Close stdin so codex does not wait for piped input over SSH
codex exec \
  --skip-git-repo-check \
  --ephemeral \
  --dangerously-bypass-approvals-and-sandbox \
  -m deepseek-flash \
  --json \
  -o "$MSG" \
  "$PROMPT" \
  </dev/null >"$OUT" 2>"$ERR" || true

python3 - <<'PY'
import json, re
from pathlib import Path

def red(s: str) -> str:
    s = re.sub(r"ma3k_[A-Za-z0-9]+", "ma3k_REDACTED", s)
    s = re.sub(r"ma3mcp_[A-Za-z0-9]+", "ma3mcp_REDACTED", s)
    return s

out = Path("/tmp/codex_clawhub_ma3.out").read_text(encoding="utf-8", errors="replace")
err = Path("/tmp/codex_clawhub_ma3.err").read_text(encoding="utf-8", errors="replace")
msg = Path("/tmp/codex_clawhub_ma3.last.txt")
print("OUT_BYTES", len(out), "ERR_BYTES", len(err))
print("=== LAST MESSAGE ===")
print(red(msg.read_text(encoding="utf-8", errors="replace")[:3000]) if msg.exists() else "(missing)")
print("=== ERR TAIL ===")
print(red(err)[-1500:])
print("=== KEY EVENTS ===")
for line in out.splitlines():
    if not line.startswith("{"):
        continue
    try:
        o = json.loads(line)
    except Exception:
        continue
    blob = json.dumps(o, ensure_ascii=False)
    if any(k in blob for k in ("ma3_whoami", "ma3_context", "ma3_report", "INSTALL_OK", "agent_message", "error")):
        print(o.get("type"), red(blob)[:500])
PY
