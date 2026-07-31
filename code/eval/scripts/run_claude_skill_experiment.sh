#!/usr/bin/env bash
# One-shot: Claude Code + ma3 skill + local MCP on trigger-p2.
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$EVAL_ROOT/../.." && pwd)"
export PATH="${HOME}/.npm-global/bin:${HOME}/.local/bin:${PATH}"

# shellcheck disable=SC1091
source "$EVAL_ROOT/scripts/load_secrets.sh"
export MA3_KEY_LOCAL="${MA3_KEY_LOCAL:-ma3dev}"

# Skill-isolated Claude profile (minimal CLAUDE.md + ma3 skill)
mkdir -p "${HOME}/.ma3/skill-experiment-backup" "${HOME}/.claude/skills/ma3"
[[ -f "${HOME}/.claude/CLAUDE.md" && ! -f "${HOME}/.ma3/skill-experiment-backup/CLAUDE.md.bak" ]] && \
  cp -a "${HOME}/.claude/CLAUDE.md" "${HOME}/.ma3/skill-experiment-backup/CLAUDE.md.bak"
cp "$REPO/code/client/skills/ma3/SKILL.md" "${HOME}/.claude/skills/ma3/SKILL.md"
cat > "${HOME}/.claude/CLAUDE.md" <<'EOF'
# Project notes

ma3 MCP server `ma3` is configured. On **non-trivial** tasks (debugging, infra, multi-step fixes),
follow the **ma3** skill: query `ma3_context` before mutating actions, then write back with
`ma3_feedback` / `ma3_report` when done.
EOF

if [[ ! -f "${HOME}/.claude/settings.json" ]]; then
  python3 - <<PY
import json, os
home = os.path.expanduser("~")
deepseek = os.environ.get("DEEPSEEK_API_KEY", "")
settings = {
    "env": {
        "ANTHROPIC_BASE_URL": os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"),
        "ANTHROPIC_AUTH_TOKEN": deepseek,
        "ANTHROPIC_MODEL": os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-pro[1m]"),
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
}
with open(f"{home}/.claude/settings.json", "w") as f:
    json.dump(settings, f, indent=2)
PY
fi

bash "$EVAL_ROOT/scripts/setup_trigger_arm.sh" B0-local-skill-mcp
_SAVED_SESSION_PREFIX="${TRIGGER_SESSION_PREFIX:-no}"
# shellcheck disable=SC1091
source "${HOME}/.ma3/trigger-experiment-backup/current-arm.env"
export TRIGGER_SESSION_PREFIX="$_SAVED_SESSION_PREFIX"
export NO_PROXY="127.0.0.1,localhost,192.168.0.0/16,10.0.0.0/8,${NO_PROXY:-}"
export no_proxy="$NO_PROXY"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

if command -v claude >/dev/null 2>&1; then
  claude mcp remove ma3 2>/dev/null || true
  claude mcp add --scope user --transport http ma3 \
    "${MA3_BASE_URL%/}/mcp" \
    --header "X-API-Key: ${MA3_API_KEY}"
fi

export TRIGGER_ARM=B0-local-skill-mcp
export TRIGGER_RUNTIME=claude
export TRIGGER_SCENARIOS=trigger-p2
export TRIGGER_ROUNDS=1
export TRIGGER_ROUND="${TRIGGER_ROUND:-1}"
export TRIGGER_CSV="${TRIGGER_CSV:-$EVAL_ROOT/results/trigger/skill-experiment-runs.csv}"
export TRIGGER_TIMEOUT_SEC="${TRIGGER_TIMEOUT_SEC:-600}"
export TRIGGER_SESSION_PREFIX="${TRIGGER_SESSION_PREFIX:-no}"
export TRIGGER_USE_SANDBOX="${TRIGGER_USE_SANDBOX:-1}"

echo "=== Claude skill experiment: arm=$TRIGGER_ARM base=$MA3_BASE_URL sandbox=$TRIGGER_USE_SANDBOX ==="
claude mcp list 2>&1 | head -5 || true

TRIGGER_WORKER_MODE=1 bash "$EVAL_ROOT/scripts/run_trigger_experiment.sh"

SEEDED_FILE="$EVAL_ROOT/scenarios/trigger-p2/workspace/seeded_record_ids.json"
if [[ -f "$SEEDED_FILE" ]]; then
  export TRIGGER_SEEDED_RECORD
  TRIGGER_SEEDED_RECORD="$(python3 -c "import json; r=json.load(open('$SEEDED_FILE')).get('records',[]); print(r[0].get('record_id','') if r else '')" 2>/dev/null || true)"
fi

echo ""
echo "=== transcript metrics (latest claude jsonl) ==="
LATEST_TX=$(find "${HOME}/.claude/projects" -name '*.jsonl' -mmin -30 2>/dev/null | sort | tail -1 || true)
if [[ -n "$LATEST_TX" ]]; then
  python3 "$EVAL_ROOT/scripts/analyze_trigger_run.py" \
    --transcript "$LATEST_TX" --scenario trigger-p2 --expects-read yes 2>/dev/null || true
  echo "transcript: $LATEST_TX"
else
  echo "no recent claude transcript"
fi

echo ""
echo "=== seeded record feedback ==="
python3 - <<'PY'
import json, os, urllib.request
base = os.environ.get("MA3_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
key = os.environ["MA3_API_KEY"]
# list recent writes via ma3_list_my_writes if dev key
payload = {
    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
    "params": {"name": "ma3_list_my_writes", "arguments": {"limit": 10, "client_version": "1.0.0"}},
}
req = urllib.request.Request(
    f"{base}/mcp",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "X-API-Key": key},
    method="POST",
)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(req, timeout=60) as resp:
    data = json.load(resp)
text = (data.get("result") or {}).get("content", [{}])[0].get("text", "")
print(text[:4000] if text else json.dumps(data, indent=2)[:2000])
seeded = os.environ.get("TRIGGER_SEEDED_RECORD", "")
if seeded:
    payload2 = {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "ma3_locate_by_id", "arguments": {"id": seeded, "client_version": "1.0.0"}},
    }
    req2 = urllib.request.Request(
        f"{base}/mcp",
        data=json.dumps(payload2).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    with opener.open(req2, timeout=60) as resp2:
        data2 = json.load(resp2)
    text2 = (data2.get("result") or {}).get("content", [{}])[0].get("text", "")
    if "feedback" in text2:
        print("--- feedback for", seeded, "---")
        print(text2[:1500])
PY
