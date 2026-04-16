# ma3 one-line installer (PowerShell / Windows)
#
# Usage:
#   irm http://10.100.193.54:8000/install.ps1 | iex
#
# With API key (recommended - avoids interactive prompt):
#   $env:MA3_API_KEY="YOUR_KEY"; irm http://10.100.193.54:8000/install.ps1 | iex
#
# Or download and run with args:
#   Invoke-WebRequest http://10.100.193.54:8000/install.ps1 -OutFile install.ps1
#   .\install.ps1 -ApiKey YOUR_KEY

param(
    [string]$ApiKey = $env:MA3_API_KEY,
    [string]$BaseUrl = $(if ($env:MA3_BASE_URL) { $env:MA3_BASE_URL } else { "http://10.100.193.54:8000" }),
    [string]$Dir = $(if ($env:MA3_PLUGIN_DIR) { $env:MA3_PLUGIN_DIR } else { "$HOME\plugins\ma3" })
)

$ClientScript = "$Dir\skills\ma3\scripts\ma3_client.py"
$SkillMd = "$Dir\skills\ma3\SKILL.md"
$AgentsMd = "$Dir\AGENTS.md"
$UninstallPs1 = "$Dir\uninstall.ps1"
$SearchExample = "$Dir\examples\search-payload.example.json"
$IngestExample = "$Dir\examples\ingest-payload.example.json"
$CodexRulesDir = "$HOME\.codex\rules"
$CodexRuleFile = "$CodexRulesDir\ma3.rules"
$EscapedClientScript = $ClientScript.Replace('\', '\\')
$ClientScriptForward = $ClientScript.Replace('\', '/')

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

Write-Host "[1/5] Downloading client files ..."
New-Item -ItemType Directory -Force -Path (Split-Path $ClientScript) | Out-Null
New-Item -ItemType Directory -Force -Path "$Dir\examples" | Out-Null
Invoke-WebRequest "$BaseUrl/client/ma3_client.py" -OutFile $ClientScript -UseBasicParsing
Write-Host "      -> $ClientScript"
Invoke-WebRequest "$BaseUrl/client/SKILL.md" -OutFile $SkillMd -UseBasicParsing
Write-Host "      -> $SkillMd"
Invoke-WebRequest "$BaseUrl/client/AGENTS.md" -OutFile $AgentsMd -UseBasicParsing
Write-Host "      -> $AgentsMd"
Invoke-WebRequest "$BaseUrl/client/uninstall.ps1" -OutFile $UninstallPs1 -UseBasicParsing
Write-Host "      -> $UninstallPs1"
Invoke-WebRequest "$BaseUrl/client/examples/search-payload.example.json" -OutFile $SearchExample -UseBasicParsing
Write-Host "      -> $SearchExample"
Invoke-WebRequest "$BaseUrl/client/examples/ingest-payload.example.json" -OutFile $IngestExample -UseBasicParsing
Write-Host "      -> $IngestExample"

Write-Host "[2/5] Writing plugin metadata ..."
$PluginJsonDir = "$Dir\.codex-plugin"
New-Item -ItemType Directory -Force -Path $PluginJsonDir | Out-Null
@'
{
  "name": "ma3",
  "version": "0.1.0",
  "description": "Use ma3 for verified agent search, record lookup, and reusable result write-back.",
  "skills": "../skills/"
}
'@ | Set-Content "$PluginJsonDir\plugin.json" -Encoding UTF8
Write-Host "      -> $PluginJsonDir\plugin.json"

$EnvFile = "$Dir\.env"
if (Test-Path -LiteralPath $EnvFile) {
    Write-Host "[3/5] .env already exists - skipping (edit manually to update)."
} else {
    Write-Host "[3/5] Writing .env ..."
    @"
MA3_BASE_URL=$BaseUrl
MA3_API_KEY=$ApiKey
MA3_AUTH_MODE=x-api-key
MA3_CLIENT_SCRIPT=$ClientScript
"@ | Set-Content $EnvFile -Encoding UTF8
    Write-Host "      -> $EnvFile"
}

Write-Host "[4/5] Linking skill into ~/.codex/skills/ ..."
$CodexSkillsDir = "$HOME\.codex\skills"
New-Item -ItemType Directory -Force -Path $CodexSkillsDir | Out-Null
$CodexSkillLink = "$CodexSkillsDir\ma3"
$SkillTarget = "$Dir\skills\ma3"
if (Test-Path -LiteralPath $CodexSkillLink) {
    Remove-Item -LiteralPath $CodexSkillLink -Force -Recurse
}
New-Item -ItemType Junction -Path $CodexSkillLink -Target $SkillTarget | Out-Null
Write-Host "      -> $CodexSkillLink => $SkillTarget"

Write-Host "      -> writing Codex allow rules to $CodexRuleFile"
New-Item -ItemType Directory -Force -Path $CodexRulesDir | Out-Null
$codexRules = @"
prefix_rule(pattern=["python", "$EscapedClientScript"], decision="allow")
prefix_rule(pattern=["python3", "$EscapedClientScript"], decision="allow")
prefix_rule(pattern=["python", "$ClientScriptForward"], decision="allow")
prefix_rule(pattern=["python3", "$ClientScriptForward"], decision="allow")
"@
[System.IO.File]::WriteAllText(
    $CodexRuleFile,
    $codexRules,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "[5/5] Patching ~/.claude/settings.json ..."
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $python) {
    Write-Host "      WARNING: python not found - skipping settings patch." -ForegroundColor Yellow
    Write-Host '      Add manually: "permissions": { "allow": ["Bash(python */ma3_client.py*)"] }'
} else {
    $tmpPy = [System.IO.Path]::GetTempFileName() + ".py"
    @"
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
        print("      -> added rule: " + rule)
else:
    print("      -> rules already present, no change.")
"@ | Set-Content $tmpPy -Encoding UTF8
    & $python.Source $tmpPy $ClientScript
    Remove-Item $tmpPy -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "=== Done! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Quick test:"
Write-Host "  python `"$ClientScript`" warmup"
Write-Host ""
Write-Host "Restart Codex / Claude Code for the skill and permission rules to take effect."
Write-Host "Uninstall later with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$UninstallPs1`""
