param(
    [string]$Dir = $(if ($env:MA3_PLUGIN_DIR) { $env:MA3_PLUGIN_DIR } else { "$HOME\plugins\ma3" })
)

$ClientScript = "$Dir\skills\ma3\scripts\ma3_client.py"
$CodexSkillLink = "$HOME\.codex\skills\ma3"
$CodexRuleFile = "$HOME\.codex\rules\ma3.rules"
$ClaudeSettings = "$HOME\.claude\settings.json"

Write-Host ""
Write-Host "=== ma3 uninstall ===" -ForegroundColor Cyan
Write-Host "Install  : $Dir"
Write-Host ""

Write-Host "[1/4] Removing Codex skill link ..."
if (Test-Path -LiteralPath $CodexSkillLink) {
    Remove-Item -LiteralPath $CodexSkillLink -Force -Recurse
    Write-Host "      -> removed $CodexSkillLink"
} else {
    Write-Host "      -> no Codex link found"
}

Write-Host "[2/4] Removing Codex allow rules ..."
if (Test-Path -LiteralPath $CodexRuleFile) {
    Remove-Item -LiteralPath $CodexRuleFile -Force
    Write-Host "      -> removed $CodexRuleFile"
} else {
    Write-Host "      -> no Codex rule file found"
}

Write-Host "[3/4] Removing Claude permission rules ..."
if (Test-Path -LiteralPath $ClaudeSettings) {
    $json = Get-Content -Raw -LiteralPath $ClaudeSettings | ConvertFrom-Json
    if (-not $json.permissions) {
        $json | Add-Member -MemberType NoteProperty -Name permissions -Value ([pscustomobject]@{})
    }
    if (-not $json.permissions.allow) {
        $json.permissions | Add-Member -MemberType NoteProperty -Name allow -Value @()
    }

    $before = @($json.permissions.allow)
    $rulesToRemove = @(
        "Bash(python $ClientScript*)",
        "Bash(python3 $ClientScript*)"
    )
    $after = @($before | Where-Object { $_ -notin $rulesToRemove })

    $json.permissions.allow = $after
    $json | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $ClaudeSettings -Encoding UTF8

    if ($before.Count -ne $after.Count) {
        Write-Host "      -> removed $($before.Count - $after.Count) rule(s) from $ClaudeSettings"
    } else {
        Write-Host "      -> no matching Claude rules found"
    }
} else {
    Write-Host "      -> no Claude settings file found"
}

Write-Host "[4/4] Removing installed plugin files ..."
if (Test-Path -LiteralPath $Dir) {
    Remove-Item -LiteralPath $Dir -Force -Recurse
    Write-Host "      -> removed $Dir"
} else {
    Write-Host "      -> plugin directory already absent"
}

Write-Host ""
Write-Host "=== Done! ===" -ForegroundColor Green
