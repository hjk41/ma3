# Fast ma3.io patch deploy (Windows → prod SSH).
# Use for small code/UI changes. Skips WSL staging, full-tree rsync, and pip.
#
# Usage:
#   .\deploy\patch_ma3_io.ps1
#   .\deploy\patch_ma3_io.ps1 -Paths code/server/app/api/ui_theme.py,code/server/app/api/routes_portal.py
#   .\deploy\patch_ma3_io.ps1 -NoCutover   # upload only
#
# Full/risky changes (deps, migrations, env) still use:
#   wsl bash deploy/run_ma3_io_deploy_wsl.sh
param(
    [string[]]$Paths = @(),
    [switch]$NoCutover,
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$RemoteHost = "ma3-prod"
$RemoteDir = "/opt/ma3_deploy"
$Commit = (git -C $RepoRoot rev-parse --short HEAD).Trim()

if ($Paths.Count -eq 1 -and $Paths[0] -match ",") {
    $Paths = @($Paths[0] -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

if ($Paths.Count -eq 0) {
    $Paths = @(
        "code/server/app/api/ui_theme.py",
        "code/server/app/api/routes_portal.py",
        "code/server/app/api/i18n/zh-CN.json",
        "code/server/app/api/i18n/en-US.json",
        "code/server/tests/integration/test_public_landing.py"
    )
}

Write-Host "==> patch ma3.io commit=$Commit files=$($Paths.Count)"

foreach ($rel in $Paths) {
    $rel = ($rel -replace "\\", "/").Trim()
    if ([string]::IsNullOrWhiteSpace($rel)) { continue }
    $local = Join-Path $RepoRoot ($rel -replace "/", [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $local)) { throw "missing local file: $local" }
    $remotePath = "$RemoteDir/$rel"
    $remoteParent = ($remotePath -replace "/[^/]+$", "")
    ssh -o BatchMode=yes -o ConnectTimeout=15 $RemoteHost "mkdir -p '$remoteParent'"
    scp -o BatchMode=yes -o ConnectTimeout=15 $local "${RemoteHost}:${remotePath}"
    Write-Host "    uploaded $rel"
}

ssh -o BatchMode=yes $RemoteHost "grep -q '^MA3_GIT_COMMIT=' $RemoteDir/ma3.env && sed -i 's/^MA3_GIT_COMMIT=.*/MA3_GIT_COMMIT=$Commit/' $RemoteDir/ma3.env || echo MA3_GIT_COMMIT=$Commit >> $RemoteDir/ma3.env; grep '^MA3_GIT_COMMIT=' $RemoteDir/ma3.env"

if ($NoCutover) {
    Write-Host "==> uploaded only (-NoCutover); restart manually when ready"
    exit 0
}

Write-Host "==> sync bluegreen helper + cutover (no pip)"
$bgLocal = Join-Path $RepoRoot "deploy\common\bluegreen_remote.sh"
# Strip CRLF into a temp LF file so remote bash is happy.
$bgTmp = Join-Path $env:TEMP "bluegreen_remote.sh"
[IO.File]::WriteAllText($bgTmp, ([IO.File]::ReadAllText($bgLocal) -replace "`r", ""))
scp -o BatchMode=yes $bgTmp "${RemoteHost}:/tmp/bluegreen_remote.sh"

$remoteCmd = @"
set -euo pipefail
chmod +x /tmp/bluegreen_remote.sh
export REMOTE_DIR=$RemoteDir
export UVICORN_HOST=127.0.0.1
export HEALTHZ_TIMEOUT=240
export REQUIRE_VECTOR=1
export BLUE_GREEN_PORT_A=8000
export BLUE_GREEN_PORT_B=8001
export BLUE_GREEN_DRAIN_SEC=5
export CADDY_UPSTREAM_FILE=$RemoteDir/data/bluegreen/upstream.caddy
export CADDY_RELOAD_CMD='caddy reload --config /etc/caddy/Caddyfile'
export BLUE_GREEN_PUBLIC_SMOKE_URL=https://ma3.io
bash /tmp/bluegreen_remote.sh cutover
"@ -replace "`r", ""
ssh -o BatchMode=yes $RemoteHost $remoteCmd

if (-not $SkipVerify) {
    Write-Host "==> public smoke"
    $tmpHtml = Join-Path $env:TEMP "ma3-home-smoke.html"
    & curl.exe -fsSL "https://ma3.io/ui/home/?lang=zh-CN" -o $tmpHtml
    $html = [IO.File]::ReadAllText($tmpHtml)
    if ($html -notmatch "ma3-talk\.slack\.com") {
        throw "Slack link not found on https://ma3.io/ui/home/"
    }
    Write-Host "    Slack link present on landing"
    & curl.exe -fsS "https://ma3.io/healthz"
    Write-Host ""
}

Write-Host "==> patch deploy done"
