import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()

# 1. .env.windows — derived from .env
env_path = ROOT / ".env"
if not env_path.exists():
    print("[FAIL] .env missing"); sys.exit(1)

secrets = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        secrets[k.strip()] = v.strip()

env_windows = f"""MASTER_KEY={secrets.get('MASTER_KEY','')}
JWT_SECRET={secrets.get('JWT_SECRET','')}
DATABASE_URL=postgresql+psycopg://{secrets.get('POSTGRES_USER','airouter')}:{secrets.get('POSTGRES_PASSWORD','airouter_dev')}@127.0.0.1:5432/{secrets.get('POSTGRES_DB','airouter')}
LOG_LEVEL=INFO
AINTERCEPTOR_PATH_A_DEBUG=1
"""
(ROOT / ".env.windows").write_text(env_windows, encoding="utf-8", newline="\n")
print("  [OK] .env.windows")

# 2. run-windows.ps1
pwsh = '''# run-windows.ps1 — Run the AInterceptor API natively on Windows.
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
if (-not (Test-Path "$venv\\Scripts\\python.exe")) {
    Write-Host "  [..] creating .venv-windows (first run, ~2 min)" -ForegroundColor Yellow
    python -m venv $venv
    & "$venv\\Scripts\\pip.exe" install -q --upgrade pip
    & "$venv\\Scripts\\pip.exe" install -q -r backend\\requirements.txt
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
& "$venv\\Scripts\\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
'''
(ROOT / "run-windows.ps1").write_text(pwsh, encoding="utf-8", newline="\r\n")
print("  [OK] run-windows.ps1")

# 3. gitignore
gi = ROOT / ".gitignore"
g = gi.read_text(encoding="utf-8")
additions = [".env.windows", ".venv-windows/"]
changed = False
for a in additions:
    if a not in g:
        g = g.rstrip() + "\n" + a + "\n"
        changed = True
if changed:
    gi.write_text(g, encoding="utf-8", newline="\n")
    print("  [OK] .gitignore updated")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)

# Check if path_b.py already has the fallback
pb = ROOT / "backend" / "app" / "runtime" / "path_b.py"
if pb.exists():
    pbs = pb.read_text(encoding="utf-8")
    if "AINTERCEPTOR_HOST_CDP_BASE" in pbs and "host.docker.internal" in pbs:
        # Add 127.0.0.1 fallback
        if "127.0.0.1" not in pbs.split("HOST_CDP_BASE")[0]:
            old = 'HOST_CDP_BASE = os.environ.get("AINTERCEPTOR_HOST_CDP_BASE", "host.docker.internal")'
            new = '''def _cdp_hosts():
    env = os.environ.get("AINTERCEPTOR_HOST_CDP_BASE")
    if env:
        return [env]
    return ["127.0.0.1", "host.docker.internal"]

HOST_CDP_BASE = _cdp_hosts()[0]  # legacy compat'''
            if old in pbs:
                pbs = pbs.replace(old, new, 1)
                pb.write_text(pbs, encoding="utf-8", newline="\n")
                print("  [OK] path_b.py: added 127.0.0.1 candidate (first)")

git(["add", "-A"])
r = git(["commit", "-m", "chore: run-windows.ps1 + .env.windows (native launcher)"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("Now run:  .\\run-windows.ps1")
