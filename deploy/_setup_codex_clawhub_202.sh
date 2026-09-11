#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
ZIP="${1:-/tmp/ma3-1.6.2.zip}"
STAGE=$(mktemp -d /tmp/ma3_clawhub_bundle.XXXXXX)
trap 'rm -rf "$STAGE"' EXIT

echo "== unzip ClawHub artifact $ZIP =="
test -f "$ZIP"
python3 - <<PY
import zipfile
from pathlib import Path
z=zipfile.ZipFile("$ZIP")
z.extractall("$STAGE")
print("files", sorted(p.as_posix() for p in Path("$STAGE").rglob("*") if p.is_file())[:20])
PY

echo "== backup + remove ma3 mcp =="
CFG="$HOME/.codex/config.toml"
cp -a "$CFG" "$CFG.bak.clawhub-smoke.$(date +%Y%m%d%H%M%S)"
python3 - <<'PY'
from pathlib import Path
p = Path.home() / ".codex/config.toml"
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
out=[]; skip=False
for line in lines:
    if line.startswith("[mcp_servers.ma3"):
        skip=True
        continue
    if skip:
        if line.startswith("[") and not line.startswith("[mcp_servers.ma3"):
            skip=False
            out.append(line)
        continue
    out.append(line)
p.write_text("".join(out), encoding="utf-8")
print("removed mcp_servers.ma3")
PY
echo "mcp list after remove:"
codex mcp list 2>&1 | head -20 || true

echo "== install skill from ClawHub zip =="
mkdir -p "$HOME/.codex/skills/ma3" "$HOME/.agents/skills/ma3"
# zip may nest under package/ or flat
SKILL=$(find "$STAGE" -path '*/skills/ma3/SKILL.md' | head -1)
MCP=$(find "$STAGE" -name mcp.json | head -1)
test -n "$SKILL" && test -n "$MCP"
cp "$SKILL" "$HOME/.codex/skills/ma3/SKILL.md"
cp "$SKILL" "$HOME/.agents/skills/ma3/SKILL.md"
echo "skill from $SKILL"
echo "mcp.json:"; cat "$MCP"
export MCP_PATH="$MCP"
python3 - <<'PY'
import json,os
from pathlib import Path
mcp_path=Path(os.environ["MCP_PATH"])
data=json.loads(mcp_path.read_text(encoding="utf-8"))
url=data["mcpServers"]["ma3"]["url"]
key=os.environ.get("MA3_API_KEY","")
if not key:
    raise SystemExit("MA3_API_KEY missing")
p=Path.home()/".codex/config.toml"
text=p.read_text(encoding="utf-8").rstrip()+"\n\n"
if "[mcp_servers.ma3]" not in text:
    text += f'''[mcp_servers.ma3]
url = "{url}"
enabled = true

[mcp_servers.ma3.http_headers]
X-API-Key = "{key}"
'''
    p.write_text(text, encoding="utf-8")
print("configured", url)
PY
MI="$HOME/.codex/model_instructions.md"
if [[ ! -f "$MI" ]] || ! grep -q 'ClawHub bundle' "$MI" 2>/dev/null; then
  cat >> "$MI" <<'EOF'

# ma3 (ClawHub bundle)
When the user consents to use ma3, follow ~/.codex/skills/ma3/SKILL.md.
Call ma3_context before non-trivial work; ma3_report after verified outcomes.
MCP: https://ma3.io/mcp
EOF
fi

echo "== mcp list after install =="
codex mcp list 2>&1 | head -20
echo "== DONE PREP =="
