#!/usr/bin/env bash

set -euo pipefail

PLUGIN_DIR="${MA3_PLUGIN_DIR:-$HOME/plugins/ma3}"
CLIENT_SCRIPT="$PLUGIN_DIR/skills/ma3/scripts/ma3_client.py"
CODEX_SKILL_LINK="$HOME/.codex/skills/ma3"
CODEX_RULE_FILE="$HOME/.codex/rules/ma3.rules"
CLAUDE_SETTINGS="$HOME/.claude/settings.json"

echo ""
echo "=== ma3 uninstall ==="
echo "Install  : $PLUGIN_DIR"
echo ""

echo "[1/4] Removing Codex skill link ..."
if [[ -L "$CODEX_SKILL_LINK" || -e "$CODEX_SKILL_LINK" ]]; then
  rm -rf "$CODEX_SKILL_LINK"
  echo "      -> removed $CODEX_SKILL_LINK"
else
  echo "      -> no Codex link found"
fi

echo "[2/4] Removing Codex allow rules ..."
if [[ -f "$CODEX_RULE_FILE" ]]; then
  rm -f "$CODEX_RULE_FILE"
  echo "      -> removed $CODEX_RULE_FILE"
else
  echo "      -> no Codex rule file found"
fi

echo "[3/4] Removing Claude permission rules ..."
if [[ -f "$CLAUDE_SETTINGS" ]]; then
  python3 - "$CLAUDE_SETTINGS" "$CLIENT_SCRIPT" <<'PYEOF'
import json
import pathlib
import sys

settings_path = pathlib.Path(sys.argv[1])
script_path = sys.argv[2]

try:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
except Exception:
    settings = {}

permissions = settings.setdefault("permissions", {})
allow = permissions.setdefault("allow", [])
rules_to_remove = {
    f"Bash(python {script_path}*)",
    f"Bash(python3 {script_path}*)",
}
new_allow = [rule for rule in allow if rule not in rules_to_remove]
removed = len(allow) - len(new_allow)
permissions["allow"] = new_allow
settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"      -> removed {removed} rule(s) from {settings_path}")
PYEOF
else
  echo "      -> no Claude settings file found"
fi

echo "[4/4] Removing installed plugin files ..."
if [[ -e "$PLUGIN_DIR" ]]; then
  rm -rf "$PLUGIN_DIR"
  echo "      -> removed $PLUGIN_DIR"
else
  echo "      -> plugin directory already absent"
fi

echo ""
echo "=== Done! ==="
