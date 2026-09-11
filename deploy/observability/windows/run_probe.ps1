$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. "$Root\load_env.ps1" -EnvFile "$Root\probe.env"

& "$Root\start_sink.ps1" *> $null

$probeScript = Join-Path $Root 'probe_ma3.py'
if (-not (Test-Path $probeScript)) {
    Add-Content -Path (Join-Path $Root 'logs\probe.log') -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR probe_ma3.py not found in $Root"
    exit 2
}

if (-not $env:MA3_PROBE_STATE_DIR) {
    $env:MA3_PROBE_STATE_DIR = Join-Path $Root 'state'
}

$python = 'C:\python3\python.exe'
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $python) {
    Add-Content -Path (Join-Path $Root 'logs\probe.log') -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR python not found"
    exit 2
}

$logFile = Join-Path $Root 'logs\probe.log'
$stdoutFile = Join-Path $Root 'logs\probe-last.out'
$stderrFile = Join-Path $Root 'logs\probe-last.err'
$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

& $python $probeScript 1> $stdoutFile 2> $stderrFile
$exitCode = $LASTEXITCODE

foreach ($path in @($stdoutFile, $stderrFile)) {
    if (Test-Path $path) {
        $body = Get-Content $path -Raw -ErrorAction SilentlyContinue
        if ($body) {
            Add-Content -Path $logFile -Value "[$ts] $body"
        }
    }
}

exit $exitCode
