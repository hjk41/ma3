param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsList
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginRoot = Split-Path -Parent $ScriptDir
$ClientPath = Join-Path $PluginRoot 'skills\ma3\scripts\ma3_client.py'

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python $ClientPath @ArgsList
    exit $LASTEXITCODE
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $ClientPath @ArgsList
    exit $LASTEXITCODE
}

throw 'Python was not found in PATH.'
