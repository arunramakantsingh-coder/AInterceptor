import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ── 1. Revert headless preference: prefer CDP if reachable ──
nrt = BE / "app/interception/nonclaude_runtime.py"
src = nrt.read_text(encoding="utf-8")

old = '''        # Headless preference: if a saved storage_state exists and the user
        # has not forced a CDP URL, run our own hidden Chromium.
        headless_pref = os.environ.get("AINTERCEPTOR_HEADLESS", "1") not in {"0","false","no"}
        sp = pathlib.Path(self.session_path) if self.session_path else None
        has_state = bool(sp and sp.exists() and sp.stat().st_size > 50)

        if headless_pref and has_state and env_val is None:
            self.cdp_url = None  # use launch path below
        elif env_val == "":'''

new = '''        # Prefer CDP: the visible Chrome holds the real login; headless
        # Chromium trips Google/Cloudflare bot detection. Only fall back to
        # headless if the user explicitly sets AINTERCEPTOR_HEADLESS=1 AND
        # no CDP is reachable.
        import socket as _sock
        def _cdp_alive(url: str | None) -> bool:
            if not url: return False
            try:
                host = url.split("://", 1)[-1].split(":")[0]
                port = int(url.rsplit(":", 1)[-1].split("/")[0])
            except Exception:
                return False
            s = _sock.socket(); s.settimeout(0.3)
            try: s.connect((host, port)); return True
            except OSError: return False
            finally: s.close()

        target_cdp = env_val if env_val else provider_registry.cdp_url(self.provider)
        force_headless = os.environ.get("AINTERCEPTOR_HEADLESS", "") in {"1","true","yes"}
        if force_headless and not _cdp_alive(target_cdp):
            self.cdp_url = None
        elif env_val == "":'''

if old in src:
    src = src.replace(old, new, 1)
    print("  [OK] runtime: prefer CDP, headless only as last resort")
else:
    print("  [!] headless block not matched")

# Ensure the surrounding 'elif env_val:' chain is intact
nrt.write_text(src, encoding="utf-8", newline="\n")

# ── 2. Launcher script that starts Chrome off-screen ──
launcher = ROOT / "scripts" / "start_browsers_offscreen.ps1"
launcher.parent.mkdir(parents=True, exist_ok=True)
launcher.write_text(r'''# start_browsers_offscreen.ps1
# Launches Chrome with the debugging port and the window pushed off-screen
# so the user never sees it. Attach via CDP and everything works headless.

param(
  [string]$Provider = "deepseek",   # deepseek | claude | chatgpt | gemini
  [int]$Port = 0
)

$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
if (!(Test-Path $chrome)) { $chrome = 'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe' }
if (!(Test-Path $chrome)) { Write-Error "chrome.exe not found"; exit 1 }

$map = @{
  deepseek = @{ Port = 9223; Url = "https://chat.deepseek.com/"; Profile = "chrome-profile-deepseek" }
  claude   = @{ Port = 9222; Url = "https://claude.ai/";        Profile = "chrome-profile-claude" }
  chatgpt  = @{ Port = 9224; Url = "https://chatgpt.com/";      Profile = "chrome-profile-chatgpt" }
  gemini   = @{ Port = 9225; Url = "https://gemini.google.com/";Profile = "chrome-profile-gemini" }
}
if (-not $map.ContainsKey($Provider)) { Write-Error "unknown provider $Provider"; exit 1 }
if ($Port -eq 0) { $Port = $map[$Provider].Port }

$profileDir = Join-Path $env:USERPROFILE "..\..\Projects\AInterceptor-M1.5\.ainterceptor\$($map[$Provider].Profile)"
$profileDir = [System.IO.Path]::GetFullPath("C:\Projects\AInterceptor-M1.5\.ainterceptor\$($map[$Provider].Profile)")
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

Start-Process $chrome -ArgumentList @(
  "--remote-debugging-port=$Port",
  "--user-data-dir=$profileDir",
  "--no-first-run",
  "--no-default-browser-check",
  "--window-position=-32000,-32000",   # off-screen: invisible to the user
  "--window-size=1280,900",
  $map[$Provider].Url
)

Write-Host "launched $Provider Chrome off-screen on port $Port"
Write-Host "attach via CDP: http://127.0.0.1:$Port"
''', encoding="utf-8", newline="\n")
print(f"  [OK] wrote {launcher.relative_to(ROOT)}")

# ── 3. Syntax check ──
r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{nrt}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("[FAIL] syntax:", r.stderr); sys.exit(1)
print("  [OK] syntax valid")

# ── 4. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(runtime): prefer CDP; add off-screen Chrome launcher for hidden UI"])
print(r.stdout.strip() or r.stderr.strip())

print()
print("=" * 66)
print("NEXT — restart the DeepSeek browser OFF-SCREEN")
print()
print("  1. Close the current DeepSeek Chrome (the visible one on 9223).")
print("  2. Launch it off-screen:")
print("       powershell -ExecutionPolicy Bypass -File scripts\\start_browsers_offscreen.ps1 -Provider deepseek")
print()
print("  3. Log into DeepSeek in that window once (it will be off-screen;")
print("     temporarily move it on-screen to log in, then minimize again).")
print("       — OR —")
print("     Copy the existing profile: rename your visible profile to")
print("     .ainterceptor\\chrome-profile-deepseek so cookies carry over.")
print()
print("  4. Run the chat — no browser window will appear while it works:")
print("       cd backend")
print('       $env:PYTHONUTF8="1"')
print(f"       {PY} -u -m scripts.chat_deepseek")
print("=" * 66)
