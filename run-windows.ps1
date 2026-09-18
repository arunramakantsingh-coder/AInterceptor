# run-windows.ps1 — Run the AInterceptor API natively on Windows.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSCommandPath
Set-Location $root

Write-Host "==> AInterceptor (Windows native)" -ForegroundColor Cyan

if (-not (Test-Path .env.windows)) {
    Write-Host "  [FAIL] .env.windows not found" -ForegroundColor Red; exit 1
}
Get-Content .env.windows | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}
Write-Host "  [OK] env loaded" -ForegroundColor Green

$pg = Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue
if (-not $pg) {
    Write-Host "  [FAIL] Postgres not running on 5432. Start: docker compose up -d db" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Postgres on 5432" -ForegroundColor Green

foreach ($port in 9222,9223,9224,9225) {
    $ok = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    $color = if ($ok) { "Green" } else { "Yellow" }
    $status = if ($ok) { "OK" } else { "not running" }
    Write-Host "  [$(if ($ok) {'OK'} else {'--'})] Chrome $port : $status" -ForegroundColor $color
}

$venv = Join-Path $root ".venv-windows"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Write-Host "  [..] creating .venv-windows (first run, ~2 min)" -ForegroundColor Yellow
    python -m venv $venv
    & "$venv\Scripts\pip.exe" install -q -r backend\requirements.txt
    Write-Host "  [OK] venv ready" -ForegroundColor Green
} else {
    Write-Host "  [OK] venv ready" -ForegroundColor Green
}

Write-Host ""
Write-Host "==> Starting API on http://localhost:8000" -ForegroundColor Cyan
Write-Host "    Docs:    http://localhost:8000/docs" -ForegroundColor Gray
Write-Host "    Health:  http://localhost:8000/healthz" -ForegroundColor Gray
Write-Host "    Ctrl+C to stop"
Write-Host ""

$env:PYTHONPATH = "backend"
& "$venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
