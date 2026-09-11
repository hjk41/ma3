$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. "$Root\load_env.ps1" -EnvFile "$Root\feishu.env"

$hostAddr = if ($env:MA3_ALERT_SINK_HOST) { $env:MA3_ALERT_SINK_HOST } else { '127.0.0.1' }
$port = if ($env:MA3_ALERT_SINK_PORT) { [int]$env:MA3_ALERT_SINK_PORT } else { 8787 }
$logPath = if ($env:MA3_ALERT_SINK_LOG) { $env:MA3_ALERT_SINK_LOG } else { Join-Path $Root 'logs\probe-alerts.jsonl' }
$env:MA3_ALERT_SINK_HOST = $hostAddr
$env:MA3_ALERT_SINK_PORT = "$port"
$env:MA3_ALERT_SINK_LOG = $logPath

$listener = Get-NetTCPConnection -LocalAddress $hostAddr -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Host "ma3-alert-sink already listening on ${hostAddr}:${port}"
    exit 0
}

$python = 'C:\python3\python.exe'
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $python) {
    throw 'python not found'
}

$sinkScript = Join-Path $Root 'local_webhook_sink.py'
if (-not (Test-Path $sinkScript)) {
    throw "sink script not found: $sinkScript"
}

New-Item -ItemType Directory -Force -Path (Split-Path $logPath -Parent) | Out-Null
$stdout = Join-Path $Root 'logs\alert-sink.out'
$stderr = Join-Path $Root 'logs\alert-sink.err'

Start-Process -FilePath $python `
    -ArgumentList @($sinkScript) `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr

Start-Sleep -Seconds 2
try {
    $resp = Invoke-RestMethod -Uri "http://${hostAddr}:${port}/" -TimeoutSec 5
    Write-Host "ma3-alert-sink started: $($resp | ConvertTo-Json -Compress)"
} catch {
    throw "ma3-alert-sink failed to start: $_"
}
