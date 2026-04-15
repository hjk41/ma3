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
PLUGIN_DIR="${MA3_PLUGIN_DIR:-$HOME/plugins/ma3/client}"

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

# ── 1. download ma3_client.py ────────────────────────────────────────────────
echo "[1/3] Downloading ma3_client.py ..."
mkdir -p "$(dirname "$CLIENT_SCRIPT")"
curl -fsSL "$BASE_URL/client/ma3_client.py" -o "$CLIENT_SCRIPT"
chmod +x "$CLIENT_SCRIPT"
echo "      → $CLIENT_SCRIPT"

# ── 2. write .env (skip if already exists) ───────────────────────────────────
ENV_FILE="$PLUGIN_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  echo "[2/3] .env already exists — skipping (edit manually to update)."
else
  echo "[2/3] Writing .env ..."
  cat > "$ENV_FILE" << EOF
MA3_BASE_URL=$BASE_URL
MA3_API_KEY=$API_KEY
MA3_AUTH_MODE=x-api-key
MA3_CLIENT_SCRIPT=$CLIENT_SCRIPT
EOF
  echo "      → $ENV_FILE"
fi

# ── 3. patch ~/.claude/settings.json ────────────────────────────────────────
echo "[3/3] Patching ~/.claude/settings.json ..."
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
echo "  python \"$CLIENT_SCRIPT\" healthz"
echo ""
echo "Restart Claude Code for permission rules to take effect."
