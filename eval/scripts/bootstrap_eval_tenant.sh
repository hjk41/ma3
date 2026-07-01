#!/usr/bin/env bash
# Bootstrap eval org + library on local ma3 v4; issue three agent API keys.
# Writes key values to stdout AND updates agent-keys.env if writable.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/load_secrets.sh"

BASE="${MA3_BASE_URL:-http://127.0.0.1:8000}"
LOGIN="${MA3_EVAL_LOGIN:-eval-admin}"
COOKIE="$(mktemp)"
KEYS_FILE="${EVAL_SECRETS_DIR}/agent-keys.env"
ORG_SLUG="${MA3_EVAL_ORG_SLUG:-ma3-eval}"
trap 'rm -f "$COOKIE"' EXIT

curl -sf -X POST "$BASE/v4/auth/dev/login?login_name=$LOGIN" -c "$COOKIE" >/dev/null

ORG_JSON=$(curl -sf -b "$COOKIE" -X POST "$BASE/v4/orgs" \
  -H 'Content-Type: application/json' \
  -d "{\"slug\":\"$ORG_SLUG\",\"name\":\"ma3 Eval\"}" 2>/dev/null || true)

if [[ -z "$ORG_JSON" || "$ORG_JSON" == *"org_slug_taken"* ]]; then
  ORG_JSON=$(curl -sf -b "$COOKIE" "$BASE/v4/orgs" | python3 -c "
import sys, json
orgs = json.load(sys.stdin)
for o in orgs:
    if o.get('slug') == '$ORG_SLUG':
        print(json.dumps(o))
        break
")
fi

ORG_ID=$(echo "$ORG_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['org_id'])")

LIB_JSON=$(curl -sf -b "$COOKIE" -X POST "$BASE/v4/orgs/$ORG_ID/libraries" \
  -H 'Content-Type: application/json' \
  -d '{"name":"eval-knowledge","description":"agent eval harness","is_public":false}' 2>/dev/null || true)

if [[ -z "$LIB_JSON" ]]; then
  LIB_JSON=$(curl -sf -b "$COOKIE" "$BASE/v4/orgs/$ORG_ID/libraries" | python3 -c "
import sys, json
libs = json.load(sys.stdin)
print(json.dumps(libs[0] if libs else {}))
")
fi

LIB_ID=$(echo "$LIB_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['library_id'])")

issue_key() {
  local label="$1"
  curl -sf -b "$COOKIE" -X POST "$BASE/v4/auth/keys" \
    -H 'Content-Type: application/json' \
    -d "{\"label\":\"$label\",\"library_grants\":[{\"library_id\":\"$LIB_ID\",\"role\":\"writer\"}]}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['raw'])"
}

KEY_CC=$(issue_key "eval-claude-code")
KEY_DROID=$(issue_key "eval-droid")
KEY_CURSOR=$(issue_key "eval-cursor-cli")

cat <<EOF
# Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) — do not commit
MA3_EVAL_ORG_ID=$ORG_ID
MA3_EVAL_LIBRARY_ID=$LIB_ID
MA3_KEY_CLAUDE_CODE=$KEY_CC
MA3_KEY_DROID=$KEY_DROID
MA3_KEY_CURSOR_CLI=$KEY_CURSOR
EOF

if [[ -w "${EVAL_SECRETS_DIR}" ]]; then
  cat > "$KEYS_FILE" <<EOF
# Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) — do not commit
MA3_EVAL_ORG_ID=$ORG_ID
MA3_EVAL_LIBRARY_ID=$LIB_ID
MA3_KEY_CLAUDE_CODE=$KEY_CC
MA3_KEY_DROID=$KEY_DROID
MA3_KEY_CURSOR_CLI=$KEY_CURSOR
EOF
  chmod 600 "$KEYS_FILE"
  echo "wrote $KEYS_FILE" >&2
fi
