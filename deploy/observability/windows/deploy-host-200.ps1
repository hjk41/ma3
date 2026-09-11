# Push ma3 off-host probe to host 200 (hct-nas) and (re)install scheduled tasks.
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File deploy/observability/windows/deploy-host-200.ps1
param(
    [string]$Remote = 'hct@192.168.31.200',
    [string]$RemoteStaging = 'C:/Users/hct/ma3-obs-deploy',
    [string]$RemoteProbeRoot = 'C:/Users/hct/.ma3/probe',
    [string]$FeishuSource = '',
    [switch]$SkipFeishuCopy
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$ObsDir = Join-Path $RepoRoot 'deploy\observability'
$WindowsDir = Join-Path $ObsDir 'windows'

if (-not $FeishuSource) {
    $localFeishu = Join-Path $env:USERPROFILE '.ma3\probe\feishu.env'
    if (Test-Path $localFeishu) { $FeishuSource = $localFeishu }
}

Write-Host "==> staging on $Remote : $RemoteStaging"
ssh -o BatchMode=yes $Remote "mkdir C:\Users\hct\ma3-obs-deploy\windows 2>nul & mkdir C:\Users\hct\.ma3\probe\state 2>nul & mkdir C:\Users\hct\.ma3\probe\logs 2>nul"

scp -o BatchMode=yes `
    (Join-Path $ObsDir 'probe_ma3.py') `
    (Join-Path $ObsDir 'local_webhook_sink.py') `
    "${Remote}:${RemoteStaging}/"

$windowsFiles = @(
    'load_env.ps1', 'start_sink.ps1', 'run_probe.ps1', 'run_probe_hidden.vbs',
    'install_probe.ps1', 'install_sink_task.ps1', 'probe.env.host200'
)
foreach ($f in $windowsFiles) {
    scp -o BatchMode=yes (Join-Path $WindowsDir $f) "${Remote}:${RemoteStaging}/windows/"
}

$remoteProbeEnv = "$RemoteProbeRoot/probe.env"
scp -o BatchMode=yes (Join-Path $WindowsDir 'probe.env.host200') "${Remote}:${remoteProbeEnv}"

if (-not $SkipFeishuCopy) {
    if (-not $FeishuSource -or -not (Test-Path $FeishuSource)) {
        Write-Warning "feishu.env not found locally; skip copy. Place it on host 200 manually."
    } else {
        Write-Host "==> copy feishu.env from $FeishuSource"
        scp -o BatchMode=yes $FeishuSource "${Remote}:${RemoteProbeRoot}/feishu.env"
    }
}

$installProbe = 'C:\Users\hct\ma3-obs-deploy\windows\install_probe.ps1'
$installSink = 'C:\Users\hct\ma3-obs-deploy\windows\install_sink_task.ps1'
$probeRootWin = $RemoteProbeRoot -replace '/', '\'

Write-Host '==> install_probe.ps1'
ssh -o BatchMode=yes $Remote "powershell -NoProfile -ExecutionPolicy Bypass -File $installProbe -WindowsDir C:\Users\hct\ma3-obs-deploy\windows -ProbeRoot $probeRootWin"

Write-Host '==> install_sink_task.ps1'
ssh -o BatchMode=yes $Remote "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\hct\ma3-obs-deploy\windows\install_sink_task.ps1"

Write-Host '==> done. See deploy/observability/windows/DEPLOYMENT.md for debug commands.'
