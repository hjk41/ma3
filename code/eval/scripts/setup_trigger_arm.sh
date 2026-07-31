#!/usr/bin/env bash
# Apply or restore trigger experiment arm (A0–A6, B0).
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$EVAL_ROOT/../.." && pwd)"
STATE_DIR="${HOME}/.ma3/trigger-experiment-backup"
ARM="${1:?usage: setup_trigger_arm.sh <arm-id>|restore}"
ACTION="${2:-apply}"

ARMS_JSON="$EVAL_ROOT/scenarios/trigger/arms.json"
POLICY_TEMPLATE_DIR="$REPO_ROOT/code/client/templates"
HOOKS_TEMPLATE_DIR="$REPO_ROOT/code/client/templates/hooks"
LOCAL_PORT="${MA3_LOCAL_PORT:-8010}"
LOCAL_BASE="${MA3_LOCAL_BASE_URL:-http://127.0.0.1:${LOCAL_PORT}}"

backup_once() {
  mkdir -p "$STATE_DIR"
  if [[ -f "${HOME}/.cursor/mcp.json" ]]; then cp -a "${HOME}/.cursor/mcp.json" "$STATE_DIR/cursor-mcp.json"; fi
  if [[ -f "${HOME}/.cursor/hooks.json" ]]; then cp -a "${HOME}/.cursor/hooks.json" "$STATE_DIR/cursor-hooks.json"; fi
  if [[ -f "${HOME}/.ma3/ma3-client.env" ]]; then cp -a "${HOME}/.ma3/ma3-client.env" "$STATE_DIR/ma3-client.env"; fi
  if [[ -f "${HOME}/.ma3/ma3-client.json" ]]; then cp -a "${HOME}/.ma3/ma3-client.json" "$STATE_DIR/ma3-client.json"; fi
  if [[ -f "${HOME}/.cursor/rules/ma3-agent-policy.mdc" ]]; then
    cp -a "${HOME}/.cursor/rules/ma3-agent-policy.mdc" "$STATE_DIR/ma3-agent-policy.mdc"
  fi
}

restore_backup() {
  [[ -f "$STATE_DIR/cursor-mcp.json" ]] && cp -a "$STATE_DIR/cursor-mcp.json" "${HOME}/.cursor/mcp.json"
  if [[ -f "$STATE_DIR/cursor-hooks.json" ]]; then
    cp -a "$STATE_DIR/cursor-hooks.json" "${HOME}/.cursor/hooks.json"
  elif [[ -f "${HOME}/.cursor/hooks.json" ]]; then
    rm -f "${HOME}/.cursor/hooks.json"
  fi
  [[ -f "$STATE_DIR/ma3-client.env" ]] && cp -a "$STATE_DIR/ma3-client.env" "${HOME}/.ma3/ma3-client.env"
  [[ -f "$STATE_DIR/ma3-client.json" ]] && cp -a "$STATE_DIR/ma3-client.json" "${HOME}/.ma3/ma3-client.json"
  [[ -f "$STATE_DIR/ma3-agent-policy.mdc" ]] && mkdir -p "${HOME}/.cursor/rules" && cp -a "$STATE_DIR/ma3-agent-policy.mdc" "${HOME}/.cursor/rules/ma3-agent-policy.mdc"
  rm -rf "${HOME}/.ma3/session-state"/*.json 2>/dev/null || true
  echo "restored ma3 client + MCP + hooks from $STATE_DIR"
}

arm_config() {
  python3 - <<PY
import json, sys
arm = "$ARM"
for a in json.load(open("$ARMS_JSON"))["arms"]:
    if a["id"] == arm:
        print(json.dumps(a))
        sys.exit(0)
print("unknown arm", arm, file=sys.stderr)
sys.exit(1)
PY
}

ensure_local_ma3() {
  local flags=("$@")
  if curl -sf --noproxy '*' "${LOCAL_BASE}/healthz" >/dev/null 2>&1; then
    if [[ ${#flags[@]} -gt 0 ]]; then
      bash "$EVAL_ROOT/scripts/restart_local_ma3.sh" "${flags[@]}"
    else
      echo "local ma3 ok: ${LOCAL_BASE}/healthz"
      curl -sf --noproxy '*' "${LOCAL_BASE}/healthz" | python3 -c "import sys,json; h=json.load(sys.stdin); print('  skill_bundle_version:', h.get('skill_bundle_version'))"
    fi
    return 0
  fi
  bash "$EVAL_ROOT/scripts/restart_local_ma3.sh" "${flags[@]}"
}

install_hooks() {
  mkdir -p "${HOME}/.cursor/hooks" "${HOME}/.ma3/logs" "${HOME}/.ma3/session-state"
  cp "$HOOKS_TEMPLATE_DIR/ma3_gate.py" "${HOME}/.cursor/hooks/ma3_gate.py"
  chmod +x "${HOME}/.cursor/hooks/ma3_gate.py"

  cat >"${HOME}/.cursor/hooks/ma3_before_shell.sh" <<'EOF'
#!/usr/bin/env bash
export CURSOR_HOOK_EVENT=beforeShellExecution
exec python3 "${HOME}/.cursor/hooks/ma3_gate.py"
EOF
  cat >"${HOME}/.cursor/hooks/ma3_after_mcp.sh" <<'EOF'
#!/usr/bin/env bash
export CURSOR_HOOK_EVENT=afterMCPExecution
exec python3 "${HOME}/.cursor/hooks/ma3_gate.py"
EOF
  chmod +x "${HOME}/.cursor/hooks/ma3_before_shell.sh" "${HOME}/.cursor/hooks/ma3_after_mcp.sh"

  cat >"${HOME}/.cursor/hooks.json" <<'EOF'
{
  "version": 1,
  "hooks": {
    "beforeShellExecution": [
      {
        "command": "./hooks/ma3_before_shell.sh"
      }
    ],
    "afterMCPExecution": [
      {
        "command": "./hooks/ma3_after_mcp.sh"
      }
    ]
  }
}
EOF
  echo "installed trigger hooks -> ~/.cursor/hooks.json"
}

remove_hooks() {
  rm -f "${HOME}/.cursor/hooks.json" 2>/dev/null || true
}

clear_hook_session_state() {
  rm -f "${HOME}/.ma3/session-state"/*.json 2>/dev/null || true
}

apply_arm() {
  local arm="$1"
  local cfg base url_key api_key policy_override hooks_enabled session_prefix
  cfg="$(arm_config)"
  base="$(echo "$cfg" | python3 -c "import sys,json; print(json.load(sys.stdin)['ma3_base_url'])")"
  url_key="$(echo "$cfg" | python3 -c "import sys,json; print(json.load(sys.stdin)['api_key_env'])")"
  policy_override="$(echo "$cfg" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('policy_override_template',''))")"
  hooks_enabled="$(echo "$cfg" | python3 -c "import sys,json; print('yes' if json.load(sys.stdin).get('hooks') else 'no')")"
  session_prefix="$(echo "$cfg" | python3 -c "import sys,json; print('yes' if json.load(sys.stdin).get('session_prompt_prefix') else 'no')")"

  backup_once

  # Local server flags (A2, A5, B0)
  local -a server_flags=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && server_flags+=("$line")
  done < <(echo "$cfg" | python3 -c 'import json,sys; d=json.load(sys.stdin); [print(f"{k}={v}") for k,v in (d.get("local_server_flags") or {}).items()]')

  case "$arm" in
    A0-baseline|A1-gate|C0-skill|C1-gate-skill)
      # Local-only 4-arm matrix: always hit self-host / local ma3, never ma3.io.
      if ! curl -sf --noproxy '*' "${base}/healthz" >/dev/null 2>&1; then
        echo "local ma3 unhealthy at ${base} (start self-host or uvicorn first)" >&2
        exit 1
      fi
      export MA3_BASE_URL="$base"
      api_key="${MA3_KEY_LOCAL:-${MA3_DEV_API_KEY:-}}"
      ;;
    A1-policy-1.6|A3-hooks|A4-policy-hooks|A6-session-prompt)
      export MA3_BASE_URL="${MA3_BASE_URL:-https://ma3.io}"
      api_key="${MA3_KEY_REMOTE:-${MA3_API_KEY:-${MA3_KEY_CURSOR_CLI:-}}}"
      ;;
    A2-tooldesc|A5-soft-signal|B0-local-skill-mcp)
      ensure_local_ma3 "${server_flags[@]}"
      export MA3_BASE_URL="$LOCAL_BASE"
      api_key="${MA3_KEY_LOCAL:-${MA3_DEV_API_KEY:-ma3dev}}"
      ;;
    *)
      echo "unknown arm: $arm" >&2
      exit 1
      ;;
  esac

  [[ -n "$api_key" ]] || { echo "missing API key for arm $arm (set $url_key)" >&2; exit 1; }
  export MA3_API_KEY="$api_key"
  export NO_PROXY="127.0.0.1,localhost,192.168.0.0/16,10.0.0.0/8,${NO_PROXY:-}"
  export no_proxy="$NO_PROXY"
  if [[ "$base" == http://127.0.0.1:* || "$base" == http://localhost:* ]]; then
    export HTTP_PROXY="" HTTPS_PROXY="" ALL_PROXY="" http_proxy="" https_proxy="" all_proxy=""
  fi

  if [[ "$hooks_enabled" == "yes" ]]; then
    install_hooks
  else
    remove_hooks
  fi
  clear_hook_session_state

  mkdir -p "${HOME}/.ma3/bin" "${HOME}/.ma3/lib" "${HOME}/.cursor/rules"
  cat >"${HOME}/.ma3/ma3-client.env" <<EOF
MA3_BASE_URL=${MA3_BASE_URL}
MA3_CLIENT_CONFIG=\${HOME}/.ma3/ma3-client.env
MA3_CLIENT_INSTALL_DIR=\${HOME}/.ma3
MA3_CLIENT_STATE=\${HOME}/.ma3/ma3-client.json
MA3_BIN_DIR=\${HOME}/.ma3/bin
MA3_LIB_DIR=\${HOME}/.ma3/lib
MA3_ONBOARDING_REL=ma3-agent-onboarding.md
MA3_POLICY_REL=policy/ma3-agent-policy.mdc
MA3_MCP_TOOLS_REL=mcp-tools.json
EOF

  if [[ ! -x "${HOME}/.ma3/bin/sync_ma3_client.sh" ]]; then
    env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY curl -fsSL "${MA3_BASE_URL}/client/scripts/sync_ma3_client.sh" -o "${HOME}/.ma3/bin/sync_ma3_client.sh"
    env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY curl -fsSL "${MA3_BASE_URL}/client/scripts/sync_ma3_client.py" -o "${HOME}/.ma3/bin/sync_ma3_client.py"
    env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY curl -fsSL "${MA3_BASE_URL}/client/lib/ma3_sync_core.py" -o "${HOME}/.ma3/lib/ma3_sync_core.py"
    chmod +x "${HOME}/.ma3/bin/sync_ma3_client.sh"
  fi

  env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY bash "${HOME}/.ma3/bin/sync_ma3_client.sh" sync

  if [[ -n "$policy_override" && -f "$POLICY_TEMPLATE_DIR/$policy_override" ]]; then
    cp "$POLICY_TEMPLATE_DIR/$policy_override" "${HOME}/.cursor/rules/ma3-agent-policy.mdc"
    cp "$POLICY_TEMPLATE_DIR/$policy_override" "${HOME}/.ma3/policy/ma3-agent-policy.mdc"
    echo "policy override -> $policy_override"
  else
    cp "${HOME}/.ma3/policy/ma3-agent-policy.mdc" "${HOME}/.cursor/rules/ma3-agent-policy.mdc"
  fi

  # Non-Cursor runtimes: mirror policy into AGENTS.md / CLAUDE.md
  if [[ -f "${HOME}/.cursor/rules/ma3-agent-policy.mdc" ]]; then
    mkdir -p "${HOME}/.factory"
    {
      echo "<coding_guidelines>"
      cat "${HOME}/.cursor/rules/ma3-agent-policy.mdc"
      echo "</coding_guidelines>"
    } >"${HOME}/.factory/AGENTS.md"
    # Claude Code / Codex both honor AGENTS.md in many setups; also write CLAUDE.md
    cp "${HOME}/.cursor/rules/ma3-agent-policy.mdc" "${HOME}/.claude/CLAUDE.md" 2>/dev/null \
      || { mkdir -p "${HOME}/.claude"; cp "${HOME}/.cursor/rules/ma3-agent-policy.mdc" "${HOME}/.claude/CLAUDE.md"; }
    mkdir -p "${HOME}/.codex"
    cp "${HOME}/.cursor/rules/ma3-agent-policy.mdc" "${HOME}/.codex/AGENTS.md"
  fi

  skill_install="$(echo "$cfg" | python3 -c "import sys,json; print('yes' if json.load(sys.stdin).get('skill_install') else 'no')")"
  SKILL_SRC="$REPO_ROOT/code/client/skills/ma3/SKILL.md"
  install_or_remove_skill() {
    local want="$1"
    if [[ "$want" == "yes" && -f "$SKILL_SRC" ]]; then
      mkdir -p "${HOME}/.cursor/skills/ma3" "${HOME}/.claude/skills/ma3" "${HOME}/.codex/skills/ma3"
      cp "$SKILL_SRC" "${HOME}/.cursor/skills/ma3/SKILL.md"
      cp "$SKILL_SRC" "${HOME}/.claude/skills/ma3/SKILL.md"
      cp "$SKILL_SRC" "${HOME}/.codex/skills/ma3/SKILL.md"
      echo "skill installed -> cursor/claude/codex skills/ma3/SKILL.md"
    else
      rm -f "${HOME}/.cursor/skills/ma3/SKILL.md" "${HOME}/.claude/skills/ma3/SKILL.md" "${HOME}/.codex/skills/ma3/SKILL.md" 2>/dev/null || true
      echo "skill removed (arm without skill_install)"
    fi
  }
  install_or_remove_skill "$skill_install"

  python3 - <<PY
import json, os
mcp_path = os.path.expanduser("~/.cursor/mcp.json")
data = {
    "mcpServers": {
        "ma3": {
            "url": os.environ["MA3_BASE_URL"].rstrip("/") + "/mcp",
            "headers": {"X-API-Key": os.environ["MA3_API_KEY"]},
        }
    }
}
with open(mcp_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print("mcp.json ->", data["mcpServers"]["ma3"]["url"])

droid_mcp_path = os.path.expanduser("~/.factory/mcp.json")
droid_data = {
    "mcpServers": {
        "ma3": {
            "type": "http",
            "url": os.environ["MA3_BASE_URL"].rstrip("/") + "/mcp",
            "headers": {"X-API-Key": os.environ["MA3_API_KEY"]},
            "disabled": False,
        }
    }
}
os.makedirs(os.path.dirname(droid_mcp_path), exist_ok=True)
with open(droid_mcp_path, "w", encoding="utf-8") as f:
    json.dump(droid_data, f, indent=2)
    f.write("\n")
print("droid mcp.json ->", droid_data["mcpServers"]["ma3"]["url"])
PY

  if command -v claude >/dev/null 2>&1; then
    claude mcp remove ma3 2>/dev/null || true
    claude mcp add --scope user --transport http ma3 \
      "${MA3_BASE_URL%/}/mcp" \
      --header "X-API-Key: ${MA3_API_KEY}" 2>/dev/null || echo "warn: claude mcp add failed" >&2
  fi

  if command -v codex >/dev/null 2>&1; then
    # Codex HTTP MCP does not reliably support X-API-Key headers; use stdio bridge.
    BRIDGE="$REPO_ROOT/code/eval/scripts/ma3_mcp_stdio_bridge.py"
    python3 - <<PY
import os
from pathlib import Path

cfg = Path.home() / ".codex" / "config.toml"
cfg.parent.mkdir(parents=True, exist_ok=True)
key = os.environ["MA3_API_KEY"]
url = os.environ["MA3_BASE_URL"].rstrip("/") + "/mcp"
bridge = "$BRIDGE"
text = f'''model = "gpt-5.4"
model_provider = "duckcoding"
approval_policy = "never"
sandbox_mode = "danger-full-access"

[model_providers.duckcoding]
name = "DuckCoding"
base_url = "https://api.duckcoding.ai/v1"
env_key = "DUCKCODING_CODEX_TOKEN"
wire_api = "responses"

[mcp_servers.ma3]
command = "python3"
args = ["{bridge}"]
env = {{ MA3_MCP_URL = "{url}", MA3_API_KEY = "{key}" }}
'''
cfg.write_text(text)
print("codex config.toml mcp_servers.ma3 ->", url)
PY
  fi

  echo "arm=$arm base=$MA3_BASE_URL skill_install=$skill_install skill_bundle=$(python3 -c "import json; print(json.load(open('${HOME}/.ma3/ma3-client.json')).get('skill_bundle_version'))") hooks=$hooks_enabled session_prefix=$session_prefix"
  cat >"$STATE_DIR/current-arm.env" <<EOF
TRIGGER_ARM_APPLIED=$arm
MA3_BASE_URL=$MA3_BASE_URL
MA3_API_KEY=$MA3_API_KEY
TRIGGER_HOOKS_ENABLED=$hooks_enabled
TRIGGER_SESSION_PREFIX=$session_prefix
EOF
}

if [[ "$ARM" == "restore" ]]; then
  restore_backup
  exit 0
fi

if [[ "$ACTION" == "restore" ]]; then
  restore_backup
else
  apply_arm "$ARM"
fi
