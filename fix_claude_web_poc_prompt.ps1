# AInterceptor Claude Web POC - Prompt Wiring Fix
# Run from C:\Projects\AInterceptor
# This script ONLY patches the standalone POC launcher. It does not touch
# production AInterceptor code, Git history, database, or migrations.

$ErrorActionPreference = "Stop"

$root = (Get-Location).Path
$launcher = Join-Path $root "run_claude_web_poc.ps1"
$pythonFile = Join-Path $root "scripts\poc_claude_web_roundtrip.py"

if (-not (Test-Path $launcher)) {
    throw "Launcher not found: $launcher"
}

$backup = "$launcher.before_prompt_fix"
Copy-Item $launcher $backup -Force
Write-Host "Backup created: $backup" -ForegroundColor DarkGray

$content = Get-Content -Raw $launcher

# Ensure the launcher has a Prompt parameter.
if ($content -notmatch '(?im)\[string\]\s*\$Prompt') {
    if ($content -match '(?is)param\s*\((.*?)\)') {
        $content = [regex]::Replace(
            $content,
            '(?is)param\s*\((.*?)\)',
            {
                param($m)
                $body = $m.Groups[1].Value
                if ($body -notmatch '(?im)\$Prompt') {
                    $body = $body.TrimEnd() + "`r`n    [string]`$Prompt = 'ACI-POC-001. Reply with exactly: ACI-POC-001-RECEIVED'`r`n"
                }
                return "param (`r`n$body)"
            },
            1
        )
    } else {
        throw "Could not locate a PowerShell param block in the launcher."
    }
}

# The launcher regenerates the Python file on every run. Therefore patch
# the generated Python after it is created, and pass the requested prompt
# via an environment variable.
$bridge = @'
$env:ACI_POC_PROMPT = $Prompt

if (-not (Test-Path $pythonFile)) {
    throw "Generated Python POC was not found: $pythonFile"
}

$py = Get-Content -Raw $pythonFile

if ($py -notmatch '_ACI_POC_REQUESTED_PROMPT') {
    $bridgeText = @"
# --- AInterceptor prompt bridge ---
import os as _aci_poc_os
_ACI_POC_DEFAULT_PROMPT = "ACI-POC-001. Reply with exactly: ACI-POC-001-RECEIVED"
_ACI_POC_REQUESTED_PROMPT = _aci_poc_os.environ.get(
    "ACI_POC_PROMPT",
    _ACI_POC_DEFAULT_PROMPT,
)
# --- end prompt bridge ---
"@

    $py = $bridgeText + "`r`n" + $py

    $py = $py -replace `
        'ACI-POC-001\. Reply with exactly: ACI-POC-001-RECEIVED', `
        '_ACI_POC_REQUESTED_PROMPT'

    $py = $py -replace `
        '_ACI_POC_DEFAULT_PROMPT = "_ACI_POC_REQUESTED_PROMPT"', `
        '_ACI_POC_DEFAULT_PROMPT = "ACI-POC-001. Reply with exactly: ACI-POC-001-RECEIVED"'

    Set-Content -Path $pythonFile -Value $py -Encoding UTF8
}

Write-Host ""
Write-Host "Prompt bridge installed." -ForegroundColor Green
Write-Host "Test command:" -ForegroundColor Cyan
Write-Host ""
Write-Host 'powershell -ExecutionPolicy Bypass -File .\run_claude_web_poc.ps1 -Prompt "ACI-POC-005. Reply with exactly: PROMPT-WIRING-PASSED"' -ForegroundColor White
Write-Host ""
