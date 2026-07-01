#!/usr/bin/env bash
# Run all 10 eval scenarios with ma3_context/report (Cursor manual eval).
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$EVAL_ROOT/scripts/load_secrets.sh"

MA3_KEY="${MA3_KEY_CURSOR_CLI:-}"
[[ -n "$MA3_KEY" ]] || { echo "MA3_KEY_CURSOR_CLI required"; exit 1; }

MA3_MCP="${MA3_BASE_URL:-http://127.0.0.1:8000}/mcp"
RESULTS=()

mcp_call() {
  local tool="$1"
  local args="$2"
  curl -sf -H "X-API-Key: $MA3_KEY" -H "Content-Type: application/json" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$tool\",\"arguments\":$args}}" \
    "$MA3_MCP"
}

ma3_context() {
  local comp="$1"
  local args
  args=$(python3 -c "import json; print(json.dumps({'problem': 'Fix eval scenario $comp', 'task_type': 'debug', 'goal': 'Resolve broken config in $comp scenario', 'target_product': 'ma3-eval', 'target_component': '$comp', 'observations': ['Running cursor manual eval'], 'max_cases': 3}))"
  mcp_call ma3_context "$args" | python3 -c "
import sys, json
r = json.load(sys.stdin)
c = (r.get('result') or {}).get('content') or [{}]
print('ma3_context:', (c[0].get('text') or str(r))[:200])
" 2>/dev/null || echo "ma3_context: (call failed)"
}

ma3_report() {
  local comp="$1" summary="$2"
  local payload args
  payload=$(python3 -c "import json; print(json.dumps({'problem': 'Fix eval scenario $comp', 'outcome': 'resolved', 'result_summary': '''$summary''', 'target_product': 'ma3-eval', 'target_component': '$comp', 'actions': [{'action': 'Fixed broken workspace config', 'rationale': 'verify.sh pass'}], 'tags': ['ma3-eval', '$comp'], 'redaction_mode': 'auto'}))")
  args=$(python3 -c "import json; print(json.dumps({'tool_name': 'ma3_report', 'arguments': json.loads('''$payload''')}))")
  mcp_call ma3_validate "$args" >/dev/null 2>&1 || true
  mcp_call ma3_report "$payload" | python3 -c "
import sys, json
r = json.load(sys.stdin)
c = (r.get('result') or {}).get('content') or [{}]
print('ma3_report:', (c[0].get('text') or 'ok')[:120])
" 2>/dev/null || echo "ma3_report: (call failed)"
}

apply_fix() {
  local scenario="$1"
  local dir="$EVAL_ROOT/scenarios/$scenario"
  case "$scenario" in
    nginx-reverse-proxy)
      sed 's|http://wrong-backend:9999|http://backend:5678|' "$dir/broken/nginx.conf" > "$dir/workspace/nginx.conf"
      ;;
    compose-network-fix)
      sed 's|http://wrong-backend:5678|http://backend:5678|' "$dir/broken/default.conf" > "$dir/workspace/default.conf"
      ;;
    supervisord-service)
      cp "$dir/broken/supervisord.conf" "$dir/workspace/supervisord.conf"
      sed -i 's|/app/wrong-app.py|/app/app.py|' "$dir/workspace/supervisord.conf"
      cp "$dir/broken/app.py" "$dir/workspace/app.py"
      ;;
    postgres-backup)
      cat > "$dir/workspace/backup.sh" <<'SH'
#!/bin/sh
pg_dump -h db -U evaluser evaldb > /backup/dump.sql
SH
      chmod +x "$dir/workspace/backup.sh"
      ;;
    ssh-key-only)
      sed 's/PasswordAuthentication yes/PasswordAuthentication no/' "$dir/broken/sshd_config" > "$dir/workspace/sshd_config"
      ;;
    http-proxy-apt)
      cat > "$dir/workspace/env.sh" <<'SH'
export HTTP_PROXY=http://127.0.0.1:8888
export HTTPS_PROXY=http://127.0.0.1:8888
SH
      ;;
    mihomo-proxy)
      sed -e 's/mixed-port: 7899/mixed-port: 7890/' \
          -e 's/allow-lan: false/allow-lan: true/' \
          -e 's/bind-address: "127.0.0.1"/bind-address: "*"/' \
          "$dir/broken/config.yaml" > "$dir/workspace/config.yaml"
      ;;
    transparent-gateway)
      sed 's/--to-port 8889/--to-port 8888/' "$dir/broken/redirect.sh" > "$dir/workspace/redirect.sh"
      chmod +x "$dir/workspace/redirect.sh"
      ;;
    claude-deepseek-byok)
      python3 - <<PY
import json, os
cfg = {
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": os.environ["DEEPSEEK_API_KEY"],
    "ANTHROPIC_MODEL": "deepseek-v4-pro[1m]",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
  }
}
with open("$dir/workspace/.claude/settings.json", "w") as f:
    json.dump(cfg, f, indent=2)
PY
      ;;
    droid-deepseek-byok)
      python3 - <<PY
import json, os
cfg = {
  "model": "deepseek-v4-pro",
  "customModels": [{
    "model": "deepseek-v4-pro",
    "displayName": "DeepSeek V4 Pro",
    "baseUrl": "https://api.deepseek.com/v1",
    "apiKey": os.environ["DEEPSEEK_API_KEY"],
    "provider": "generic-chat-completion-api",
    "extraArgs": {"thinking": {"type": "disabled"}},
  }]
}
with open("$dir/workspace/.factory/settings.json", "w") as f:
    json.dump(cfg, f, indent=2)
PY
      ;;
    *) echo "unknown scenario: $scenario"; return 1 ;;
  esac
}

run_scenario() {
  local scenario="$1"
  local dir="$EVAL_ROOT/scenarios/$scenario"
  echo ""
  echo "========== $scenario =========="
  ma3_context "$scenario"

  if [[ -x "$dir/setup.sh" ]]; then
    (cd "$dir" && bash setup.sh)
  fi
  apply_fix "$scenario"

  local verify_ok=no compose_err=""
  if [[ -f "$dir/docker-compose.yml" ]]; then
    export MIHOMO_SUBSCRIPTION_URL="${MIHOMO_SUBSCRIPTION_URL:-}"
    if ! (cd "$dir" && docker compose up -d --build 2>&1); then
      compose_err="compose_up_failed"
    fi
    sleep 3
  fi

  local verify_exit=1
  if [[ -z "$compose_err" && -x "$dir/verify.sh" ]]; then
    if (cd "$dir" && bash verify.sh); then
      verify_exit=0
      verify_ok=yes
    fi
  elif [[ -x "$dir/verify.sh" && ! -f "$dir/docker-compose.yml" ]]; then
    if (cd "$dir" && bash verify.sh); then
      verify_exit=0
      verify_ok=yes
    fi
  fi

  if [[ "$verify_ok" == yes ]]; then
    ma3_report "$scenario" "Fixed broken config; verify.sh passed for $scenario"
  fi

  if [[ -f "$dir/docker-compose.yml" ]]; then
    (cd "$dir" && docker compose down -v) >/dev/null 2>&1 || true
  fi

  RESULTS+=("$scenario:$verify_ok:${compose_err:-}")
  echo "RESULT $scenario verify=$verify_ok compose_err=${compose_err:-none}"
}

SCENARIOS=(
  claude-deepseek-byok
  mihomo-proxy
  transparent-gateway
  droid-deepseek-byok
  nginx-reverse-proxy
  supervisord-service
  postgres-backup
  ssh-key-only
  http-proxy-apt
  compose-network-fix
)

for s in "${SCENARIOS[@]}"; do
  run_scenario "$s" || true
done

echo ""
echo "========== SUMMARY =========="
for r in "${RESULTS[@]}"; do echo "$r"; done
