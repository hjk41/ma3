#!/usr/bin/env bash
# ma3 one-line installer (bash / Git Bash / WSL / Linux / macOS)
#
# Usage:
#   curl -fsSL http://10.100.193.54:8000/install.sh | bash -s -- --api-key YOUR_KEY
#   curl -fsSL http://10.100.193.54:8000/install.sh | bash -s -- --api-key YOUR_KEY --base-url http://other:8000
#
# Note: avoid `MA3_API_KEY=xxx curl ... | bash` — the variable assignment applies
# only to curl, not to bash in the pipeline.  Use --api-key or export first:
#   export MA3_API_KEY=xxx && curl -fsSL .../install.sh | bash

set -euo pipefail

BASE_URL="${MA3_BASE_URL:-http://10.100.193.54:8000}"
API_KEY="${MA3_API_KEY:-}"
PLUGIN_DIR="${MA3_PLUGIN_DIR:-$HOME/plugins/ma3}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-key) API_KEY="$2"; shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    --dir) PLUGIN_DIR="$2"; shift 2 ;;
    *) shift ;;
  esac
done

CLIENT_SCRIPT="$PLUGIN_DIR/skills/ma3/scripts/ma3_client.py"
SKILL_MD="$PLUGIN_DIR/skills/ma3/SKILL.md"
AGENTS_MD="$PLUGIN_DIR/AGENTS.md"
UNINSTALL_SH="$PLUGIN_DIR/uninstall.sh"
SEARCH_EXAMPLE="$PLUGIN_DIR/examples/search-payload.example.json"
INGEST_EXAMPLE="$PLUGIN_DIR/examples/ingest-payload.example.json"
CODEX_RULES_DIR="$HOME/.codex/rules"
CODEX_RULE_FILE="$CODEX_RULES_DIR/ma3.rules"
CLIENT_SCRIPT_FORWARD="${CLIENT_SCRIPT//\\//}"

if [[ -z "$API_KEY" ]]; then
  if [[ -e /dev/tty ]]; then
    read -rp "ma3 API Key: " API_KEY < /dev/tty
  else
    echo "ERROR: MA3_API_KEY not set and no TTY available." >&2
    echo "Run: curl ... | bash -s -- --api-key YOUR_KEY" >&2
    exit 1
  fi
fi

echo ""
echo "=== ma3 install ==="
echo "Base URL : $BASE_URL"
echo "Install  : $PLUGIN_DIR"
echo ""

echo "[1/5] Downloading client files ..."
mkdir -p "$(dirname "$CLIENT_SCRIPT")"
mkdir -p "$PLUGIN_DIR/examples"
curl -fsSL "$BASE_URL/client/ma3_client.py" -o "$CLIENT_SCRIPT"
chmod +x "$CLIENT_SCRIPT"
echo "      -> $CLIENT_SCRIPT"
curl -fsSL "$BASE_URL/client/SKILL.md" -o "$SKILL_MD"
echo "      -> $SKILL_MD"
curl -fsSL "$BASE_URL/client/AGENTS.md" -o "$AGENTS_MD"
echo "      -> $AGENTS_MD"
curl -fsSL "$BASE_URL/client/uninstall.sh" -o "$UNINSTALL_SH"
chmod +x "$UNINSTALL_SH"
echo "      -> $UNINSTALL_SH"
curl -fsSL "$BASE_URL/client/examples/search-payload.example.json" -o "$SEARCH_EXAMPLE"
echo "      -> $SEARCH_EXAMPLE"
curl -fsSL "$BASE_URL/client/examples/ingest-payload.example.json" -o "$INGEST_EXAMPLE"
echo "      -> $INGEST_EXAMPLE"

echo "[2/5] Writing plugin metadata ..."
PLUGIN_JSON_DIR="$PLUGIN_DIR/.codex-plugin"
mkdir -p "$PLUGIN_JSON_DIR"
cat > "$PLUGIN_JSON_DIR/plugin.json" <<'EOF'
{
  "name": "ma3",
  "version": "0.1.0",
  "description": "Use ma3 for verified agent search, record lookup, and reusable result write-back.",
  "skills": "../skills/"
}
EOF
echo "      -> $PLUGIN_JSON_DIR/plugin.json"

ENV_FILE="$PLUGIN_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  echo "[3/5] .env already exists - skipping (edit manually to update)."
else
  echo "[3/5] Writing .env ..."
  cat > "$ENV_FILE" <<EOF
MA3_BASE_URL=$BASE_URL
MA3_API_KEY=$API_KEY
MA3_AUTH_MODE=x-api-key
MA3_CLIENT_SCRIPT=$CLIENT_SCRIPT
EOF
  echo "      -> $ENV_FILE"
fi

echo "[4/5] Linking skill into ~/.codex/skills/ ..."
CODEX_SKILLS_DIR="$HOME/.codex/skills"
if [[ -d "$CODEX_SKILLS_DIR" || ! -e "$CODEX_SKILLS_DIR" ]]; then
  mkdir -p "$CODEX_SKILLS_DIR"
  ln -sf "$PLUGIN_DIR/skills/ma3" "$CODEX_SKILLS_DIR/ma3"
  echo "      -> $CODEX_SKILLS_DIR/ma3 => $PLUGIN_DIR/skills/ma3"
  mkdir -p "$CODEX_RULES_DIR"
  cat > "$CODEX_RULE_FILE" <<EOF
prefix_rule(pattern=["python", "$CLIENT_SCRIPT"], decision="allow")
prefix_rule(pattern=["python3", "$CLIENT_SCRIPT"], decision="allow")
prefix_rule(pattern=["python", "$CLIENT_SCRIPT_FORWARD"], decision="allow")
prefix_rule(pattern=["python3", "$CLIENT_SCRIPT_FORWARD"], decision="allow")
EOF
  echo "      -> $CODEX_RULE_FILE"
else
  echo "      WARNING: $CODEX_SKILLS_DIR exists but is not a directory - skipping."
fi

echo "[5/5] Patching ~/.claude/settings.json ..."
PYTHON="$(command -v python3 || command -v python || echo "")"
if [[ -z "$PYTHON" ]]; then
  echo "      WARNING: python not found - skipping settings patch."
  echo '      Add manually: "permissions": { "allow": ["Bash(python */ma3_client.py*)"] }'
else
  "$PYTHON" - "$CLIENT_SCRIPT" <<'PYEOF'
import json
import pathlib
import sys

script = sys.argv[1]
rules = [f"Bash(python {script}*)", f"Bash(python3 {script}*)"]
settings_file = pathlib.Path.home() / ".claude" / "settings.json"
settings_file.parent.mkdir(parents=True, exist_ok=True)
try:
    settings = json.loads(settings_file.read_text(encoding="utf-8")) if settings_file.exists() else {}
except Exception:
    settings = {}
allow = settings.setdefault("permissions", {}).setdefault("allow", [])
added = []
for rule in rules:
    if rule not in allow:
        allow.append(rule)
        added.append(rule)
if added:
    settings_file.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    for rule in added:
        print(f"      -> added rule: {rule}")
else:
    print("      -> rules already present, no change.")
PYEOF
fi

echo ""
echo "=== Done! ==="
echo ""
echo "Quick test:"
echo "  python3 \"$CLIENT_SCRIPT\" warmup"
echo ""
echo "Restart Codex / Claude Code for the skill and permission rules to take effect."
echo "Uninstall later with:"
echo "  bash \"$UNINSTALL_SH\""
