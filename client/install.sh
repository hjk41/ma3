#!/usr/bin/env bash
# ma3 one-line installer (bash / Git Bash / WSL / Linux / macOS)
#
# Usage:
#   curl -fsSL http://10.100.193.54:8000/install.sh | bash -s -- --api-key YOUR_KEY
#   curl -fsSL http://10.100.193.54:8000/install.sh | bash -s -- --api-key YOUR_KEY --base-url http://other:8000
#
# Or set env vars before piping:
#   MA3_API_KEY=xxx curl -fsSL http://10.100.193.54:8000/install.sh | bash

set -euo pipefail

# ── defaults ────────────────────────────────────────────────────────────────
BASE_URL="${MA3_BASE_URL:-http://10.100.193.54:8000}"
API_KEY="${MA3_API_KEY:-}"
PLUGIN_DIR="${MA3_PLUGIN_DIR:-$HOME/plugins/ma3}"

# ── parse args ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-key)  API_KEY="$2";  shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    --dir)      PLUGIN_DIR="$2"; shift 2 ;;
    *) shift ;;
  esac
done

CLIENT_SCRIPT="$PLUGIN_DIR/skills/ma3/scripts/ma3_client.py"

# ── prompt for key if missing (reads from /dev/tty so pipe-safe) ─────────────
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

# ── 1. download all client files ─────────────────────────────────────────────
echo "[1/4] Downloading client files ..."
mkdir -p "$(dirname "$CLIENT_SCRIPT")"
curl -fsSL "$BASE_URL/client/ma3_client.py" -o "$CLIENT_SCRIPT"
chmod +x "$CLIENT_SCRIPT"
echo "      → $CLIENT_SCRIPT"

SKILL_MD="$PLUGIN_DIR/skills/ma3/SKILL.md"
curl -fsSL "$BASE_URL/client/SKILL.md" -o "$SKILL_MD"
echo "      → $SKILL_MD"

AGENTS_MD="$PLUGIN_DIR/AGENTS.md"
curl -fsSL "$BASE_URL/client/AGENTS.md" -o "$AGENTS_MD"
echo "      → $AGENTS_MD"

mkdir -p "$PLUGIN_DIR/examples"
curl -fsSL "$BASE_URL/client/examples/search-payload.example.json" \
     -o "$PLUGIN_DIR/examples/search-payload.example.json"
echo "      → $PLUGIN_DIR/examples/search-payload.example.json"

curl -fsSL "$BASE_URL/client/examples/ingest-payload.example.json" \
     -o "$PLUGIN_DIR/examples/ingest-payload.example.json"
echo "      → $PLUGIN_DIR/examples/ingest-payload.example.json"

# ── 2. create plugin metadata ─────────────────────────────────────────────────
echo "[2/4] Writing plugin metadata ..."
PLUGIN_JSON_DIR="$PLUGIN_DIR/.codex-plugin"
mkdir -p "$PLUGIN_JSON_DIR"
cat > "$PLUGIN_JSON_DIR/plugin.json" << EOF
{
  "name": "ma3",
  "version": "0.1.0",
  "description": "Use ma3 for verified agent search, record lookup, and reusable result write-back.",
  "skills": "../skills/"
}
EOF
echo "      → $PLUGIN_JSON_DIR/plugin.json"

# ── 3. write .env (skip if already exists) ───────────────────────────────────
ENV_FILE="$PLUGIN_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  echo "[3/4] .env already exists — skipping (edit manually to update)."
else
  echo "[3/4] Writing .env ..."
  cat > "$ENV_FILE" << EOF
MA3_BASE_URL=$BASE_URL
MA3_API_KEY=$API_KEY
MA3_AUTH_MODE=x-api-key
MA3_CLIENT_SCRIPT=$CLIENT_SCRIPT
EOF
  echo "      → $ENV_FILE"
fi

# ── 4. patch ~/.claude/settings.json ────────────────────────────────────────
echo "[4/4] Patching ~/.claude/settings.json ..."
PYTHON=$(command -v python3 || command -v python || echo "")
if [[ -z "$PYTHON" ]]; then
  echo "      WARNING: python not found — skipping settings patch."
  echo "      Add this manually to ~/.claude/settings.json:"
  echo '      "permissions": { "allow": ["Bash(python */ma3_client.py*)"] }'
else
  "$PYTHON" - "$CLIENT_SCRIPT" << 'PYEOF'
import json, pathlib, sys

rule = f"Bash(python {sys.argv[1]}*)"
sf   = pathlib.Path.home() / ".claude" / "settings.json"
sf.parent.mkdir(parents=True, exist_ok=True)
try:
    s = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else {}
except json.JSONDecodeError:
    s = {}
allow = s.setdefault("permissions", {}).setdefault("allow", [])
if rule not in allow:
    allow.append(rule)
    sf.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"      → added rule: {rule}")
else:
    print("      → rule already present, no change.")
PYEOF
fi

# ── done ─────────────────────────────────────────────────────────────────────
echo ""
echo "=== Done! ==="
echo ""
echo "Quick test:"
echo "  python \"$CLIENT_SCRIPT\" warmup"
echo ""
echo "Restart Claude Code for permission rules to take effect."
