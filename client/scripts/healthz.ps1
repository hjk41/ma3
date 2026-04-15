$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $ScriptDir 'ma3.ps1') healthz
exit $LASTEXITCODE
