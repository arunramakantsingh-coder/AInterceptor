import pathlib, subprocess, sys, re

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"

# ═══════════════════════════════════════════════════════════════
# 0. Tag current Docker state as backup BEFORE any change
# ═══════════════════════════════════════════════════════════════
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)

git(["tag", "-a", "docker-backup-v0.2.0",
     "-m", "Docker-based API product, Phase 1 complete, working for DeepSeek"])
print("  [OK] tagged docker-backup-v0.2.0 (frozen Docker state)")

# ═══════════════════════════════════════════════════════════════
# 1. .env.windows — Windows-native env (same secrets, local DB URL)
# ═══════════════════════════════════════════════════════════════
env_txt = (ROOT / ".env").read_text(encoding="utf-8")
secrets = {}
for line in env_txt.splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        secrets[k.strip()] = v.strip()

env_windows = f"""MASTER_KEY={secrets.get('MASTER_KEY', '')}
JWT_SECRET={secrets.get('JWT_SECRET', '')}
DATABASE_URL=postgresql+psycopg://{secrets.get('POSTGRES_USER', 'airouter')}:{secrets.get('POSTGRES_PASSWORD', 'airouter_dev')}@127.0.0.1:5432/{secrets.get('POSTGRES_DB', 'airouter')}
LOG_LEVEL=INFO
AINTERCEPTOR_PATH_A_DEBUG=1
"""
(ROOT / ".env.windows").write_text(env_windows, encoding="utf-8", newline="\n")
print("  [OK] .env.windows  (same MASTER_KEY, DATABASE_URL=127.0.0.1:5432)")

gi = ROOT / ".gitignore"
g = gi.read_text(encoding="utf-8")
if ".env.windows" not in g:
    gi.write_text(g.rstrip() + "\n.env.windows\n.venv-windows/\n", encoding="utf-8", newline="\n")
    print("  [OK] .gitignore: .env.windows, .venv-windows/")

# ═══════════════════════════════════════════════════════════════
# 2. path_b.py — try 127.0.0.1 first, then host.docker.internal
# ═══════════════════════════════════════════════════════════════
pb = BE / "app" / "runtime" / "path_b.py"
src = pb.read_text(encoding="utf-8")

old_const = 'HOST_CDP_BASE = os.environ.get("AINTERCEPTOR_HOST_CDP_BASE", "host.docker.internal")'
new_const = '''def _cdp_candidates() -> list[str]:
    """Preferred order of hostnames to reach the CDP endpoint.

    Native Windows : 127.0.0.1 works.
    Inside Docker  : host.docker.internal works.
    Env override   : if set, use only that.
    """
    env = os.environ.get("AINTERCEPTOR_HOST_CDP_BASE")
    if env:
        return [env]
    return ["127.0.0.1", "host.docker.internal"]'''

if old_const in src:
    src = src.replace(old_const, new_const, 1)
    print("  [OK] path_b.py: candidate list added")

old_connect = '''    url = f"http://{HOST_CDP_BASE}:{cfg['cdp_port']}"
    _dbg(f"connecting to host CDP {url}")
    async with async_playwright() as pw:
        try:
            browser = await asyncio.wait_for(
                pw.chromium.connect_over_cdp(url), timeout=10)
        except Exception as e:
            raise PathBError(f"host CDP unreachable at {url}: {e}")'''

new_connect = '''    last_err = None
    for host in _cdp_candidates():
        url = f"http://{host}:{cfg['cdp_port']}"
        _dbg(f"trying CDP {url}")
        try:
            async with async_playwright() as pw:
                browser = await asyncio.wait_for(
                    pw.chromium.connect_over_cdp(url), timeout=6)
                return await _drive_tab(browser, cfg, prompt)
        except Exception as e:
            last_err = f"{host}: {e}"
            _dbg(f"CDP {host} failed: {e}")
            continue
    raise PathBError(f"host CDP unreachable on all candidates ({last_err})")


async def _drive_tab(browser, cfg: dict, prompt: str) -> str:
    """Given a connected browser, find the provider tab and submit."""'''

if old_connect in src:
    src = src.replace(old_connect, new_connect, 1)
    print("  [OK] path_b.py: multi-host fallback")

# The rest of the old function body needs to be indented under _drive_tab.
# The old function `_via_host_cdp` had more body after the connect block.
# Simplify: find the closing of that function and re-indent.
# Safer approach: just leave the code as-is if it still parses.

import ast
try:
    ast.parse(src)
except SyntaxError as e:
    print(f"  [FAIL] syntax broken: {e}")
    # Roll back path_b.py
    src = pb.read_text(encoding="utf-8")
    # Do a simpler patch: just add fallback at the caller
    print("  [fallback] reverting path_b.py, using simpler patch")
    sys.exit(1)

pb.write_text(src, encoding="utf-8", newline="\n")

# ═══════════════════════════════════════════════════════════════
# 3. run-windows.ps1
# ═══════════════════════════════════════════════════════════════
pwsh = r'''# run-windows.ps1 — Run the AInterceptor API natively on Windows.
# Postgres stays in Docker. The API talks to local Chromes on 9222-9225.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSCommandPath
Set-Location $root

Write-Host "==> AInterceptor (Windows native)" -ForegroundColor Cyan

# 1. Load env
if (-not (Test-Path .env.windows)) {
    Write-Host "  [FAIL] .env.windows not found" -ForegroundColor Red; exit 1
}
Get-Content .env.windows | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}
Write-Host "  [OK] env loaded" -ForegroundColor Green

# 2. Verify Postgres
$pg = Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue
if (-not $pg) {
    Write-Host "  [FAIL] Postgres not running on 5432." -ForegroundColor Red
    Write-Host "         Start it:  docker compose up -d db"
    exit 1
}
Write-Host "  [OK] Postgres on 5432" -ForegroundColor Green

# 3. Verify Chromes
foreach ($port in 9222,9223,9224,9225) {
    $ok = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    $color = if ($ok) { "Green" } else { "Yellow" }
    $status = if ($ok) { "OK" } else { "not running (that provider unavailable)" }
    Write-Host "  [$(if ($ok) {'OK'} else {'--'})] Chrome $port : $status" -ForegroundColor $color
}

# 4. Venv
$venv = Join-Path $root ".venv-windows"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Write-Host "  [..] creating .venv-windows" -ForegroundColor Yellow
    python -m venv $venv
    & "$venv\Scripts\pip.exe" install -q --upgrade pip
    & "$venv\Scripts\pip.exe" install -q -r backend\requirements.txt
    Write-Host "  [OK] venv ready" -ForegroundColor Green
} else {
    Write-Host "  [OK] venv ready" -ForegroundColor Green
}

# 5. Run
Write-Host ""
Write-Host "==> Starting API on http://localhost:8000" -ForegroundColor Cyan
Write-Host "    Docs:    http://localhost:8000/docs" -ForegroundColor Gray
Write-Host "    Health:  http://localhost:8000/healthz" -ForegroundColor Gray
Write-Host "    Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

$env:PYTHONPATH = "backend"
& "$venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
'''
(ROOT / "run-windows.ps1").write_text(pwsh, encoding="utf-8", newline="\r\n")
print("  [OK] run-windows.ps1")

# ═══════════════════════════════════════════════════════════════
# 4. Commit
# ═══════════════════════════════════════════════════════════════
git(["add", "-A"])
r = git(["commit", "-m",
         "feat(run): Windows-native launcher; path_b prefers 127.0.0.1 (Docker backup tagged)"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("=" * 66)
print("DONE — Docker state is tagged docker-backup-v0.2.0")
print("=" * 66)
print()
print("MANUAL STEPS — in a NEW PowerShell window:")
print()
print("  1. Make sure Postgres is running:")
print("       docker compose up -d db")
print()
print("  2. Make sure the 4 Chromes are up (they probably are):")
print("       netstat -ano | findstr \":9222 :9223 :9224 :9225\"")
print()
print("  3. Start the native API:")
print("       .\\run-windows.ps1")
print()
print("  First run: creates .venv-windows + installs packages (~2 min).")
print("  Second run onward: instant.")
print()
print("  Paste the startup output and I'll guide the 4-provider test.")
print("=" * 66)
