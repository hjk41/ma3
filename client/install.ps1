# ma3 one-line installer (PowerShell / Windows)
#
# Usage:
#   irm http://10.100.193.54:8000/install.ps1 | iex
#
# With API key (recommended — avoids interactive prompt):
#   $env:MA3_API_KEY="YOUR_KEY"; irm http://10.100.193.54:8000/install.ps1 | iex
#
# Or download and run with args:
#   Invoke-WebRequest http://10.100.193.54:8000/install.ps1 -OutFile install.ps1
#   .\install.ps1 -ApiKey YOUR_KEY

param(
    [string]$ApiKey  = $env:MA3_API_KEY,
    [string]$BaseUrl = $(if ($env:MA3_BASE_URL) { $env:MA3_BASE_URL } else { "http://10.100.193.54:8000" }),
    [string]$Dir     = $(if ($env:MA3_PLUGIN_DIR) { $env:MA3_PLUGIN_DIR } else { "$HOME\plugins\ma3\client" })
)

$ClientScript = "$Dir\skills\ma3\scripts\ma3_client.py"

# Prompt if no key provided
if (-not $ApiKey) {
    $ApiKey = Read-Host "ma3 API Key"
}
if (-not $ApiKey) {
    Write-Error "API Key is required."
    exit 1
}

Write-Host ""
Write-Host "=== ma3 install ===" -ForegroundColor Cyan
Write-Host "Base URL : $BaseUrl"
Write-Host "Install  : $Dir"
Write-Host ""

# ── 1. download ma3_client.py and SKILL.md ──────────────────────────────────
Write-Host "[1/3] Downloading ma3_client.py and SKILL.md ..."
New-Item -ItemType Directory -Force -Path (Split-Path $ClientScript) | Out-Null
Invoke-WebRequest "$BaseUrl/client/ma3_client.py" -OutFile $ClientScript -UseBasicParsing
Write-Host "      -> $ClientScript"

$SkillMd = "$Dir\skills\ma3\SKILL.md"
Invoke-WebRequest "$BaseUrl/client/SKILL.md" -OutFile $SkillMd -UseBasicParsing
Write-Host "      -> $SkillMd"

# ── 2. write .env (skip if already exists) ───────────────────────────────────
$EnvFile = "$Dir\.env"
if (Test-Path $EnvFile) {
    Write-Host "[2/3] .env already exists — skipping (edit manually to update)."
} else {
    Write-Host "[2/3] Writing .env ..."
    @"
MA3_BASE_URL=$BaseUrl
MA3_API_KEY=$ApiKey
MA3_AUTH_MODE=x-api-key
MA3_CLIENT_SCRIPT=$ClientScript
"@ | Set-Content $EnvFile -Encoding UTF8
    Write-Host "      -> $EnvFile"
}

# ── 3. patch ~/.claude/settings.json ────────────────────────────────────────
Write-Host "[3/3] Patching ~/.claude/settings.json ..."
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $python) {
    Write-Host "      WARNING: python not found — skipping settings patch." -ForegroundColor Yellow
    Write-Host '      Add manually: "permissions": { "allow": ["Bash(python */ma3_client.py*)"] }'
} else {
    $tmpPy = [System.IO.Path]::GetTempFileName() + ".py"
    @"
import json, pathlib, sys
rule = "Bash(python " + sys.argv[1] + "*)"
sf   = pathlib.Path.home() / ".claude" / "settings.json"
sf.parent.mkdir(parents=True, exist_ok=True)
try:
    s = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else {}
except Exception:
    s = {}
allow = s.setdefault("permissions", {}).setdefault("allow", [])
if rule not in allow:
    allow.append(rule)
    sf.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    print("      -> added rule: " + rule)
else:
    print("      -> rule already present, no change.")
"@ | Set-Content $tmpPy -Encoding UTF8
    & $python.Source $tmpPy $ClientScript
    Remove-Item $tmpPy -ErrorAction SilentlyContinue
}

# ── done ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Done! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Quick test:"
Write-Host "  python `"$ClientScript`" healthz"
Write-Host ""
Write-Host "Restart Claude Code for permission rules to take effect."
