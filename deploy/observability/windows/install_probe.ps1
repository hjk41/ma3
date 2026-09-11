# Install ma3 off-host probe + Feishu alert sink on this Windows machine.
param(
    [string]$ProbeRoot = "$env:USERPROFILE\.ma3\probe",
    [string]$WindowsDir = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'
$ProbeTask = 'ma3-probe'

function Ensure-Dir([string]$Path) {
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Test-ScheduledTask([string]$Name) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    schtasks /Query /TN $Name 2>&1 | Out-Null
    $ok = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $old
    return $ok
}

Ensure-Dir $ProbeRoot
Ensure-Dir (Join-Path $ProbeRoot 'state')
Ensure-Dir (Join-Path $ProbeRoot 'logs')

$obsDir = (Resolve-Path (Join-Path $WindowsDir '..')).Path

foreach ($file in @('load_env.ps1', 'start_sink.ps1', 'run_probe.ps1', 'run_probe_hidden.vbs', 'install_sink_task.ps1')) {
    Copy-Item (Join-Path $WindowsDir $file) (Join-Path $ProbeRoot $file) -Force
}
foreach ($file in @('probe_ma3.py', 'local_webhook_sink.py')) {
    Copy-Item (Join-Path $obsDir $file) (Join-Path $ProbeRoot $file) -Force
}

$probeEnv = Join-Path $ProbeRoot 'probe.env'
if (-not (Test-Path $probeEnv)) {
    $example = Join-Path $WindowsDir 'probe.env.example'
    if (Test-Path $example) {
        (Get-Content $example -Raw).Replace('YOUR_USER', $env:USERNAME) | Set-Content $probeEnv -Encoding UTF8
    } else {
        throw 'Missing probe.env and probe.env.example'
    }
    Write-Host "Created $probeEnv"
}

$feishuEnv = Join-Path $ProbeRoot 'feishu.env'
if (-not (Test-Path $feishuEnv)) {
    Write-Warning "Missing $feishuEnv"
}

$runProbeHidden = Join-Path $ProbeRoot 'run_probe_hidden.vbs'
$startSink = Join-Path $ProbeRoot 'start_sink.ps1'

if (Test-ScheduledTask $ProbeTask) { schtasks /Delete /TN $ProbeTask /F | Out-Null }

$probeCmd = 'wscript.exe "' + $runProbeHidden + '"'
schtasks /Create /TN $ProbeTask /TR $probeCmd /SC MINUTE /MO 1 /F | Out-Null

$sinkInstaller = Join-Path $ProbeRoot 'install_sink_task.ps1'
if (Test-Path $sinkInstaller) {
    & $sinkInstaller
}

Write-Host 'Scheduled task:'
schtasks /Query /TN $ProbeTask /FO LIST /V | Select-String 'TaskName|Status|Next Run|Task To Run'
schtasks /Query /TN ma3-alert-sink /FO LIST /V | Select-String 'TaskName|Status|Task To Run'

Write-Host 'Starting alert sink...'
& $startSink

Write-Host 'Running one hidden probe tick...'
& wscript.exe $runProbeHidden
Start-Sleep -Seconds 8
$log = Join-Path $ProbeRoot 'logs\probe.log'
if (Test-Path $log) { Get-Content $log -Tail 3 }

$logDir = Join-Path $ProbeRoot 'logs'
Write-Host "Done. Logs: $logDir"
