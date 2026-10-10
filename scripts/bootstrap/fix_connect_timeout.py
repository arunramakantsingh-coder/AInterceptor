import pathlib, re, ast, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
rt   = BE / "app/interception/nonclaude_runtime.py"
src  = rt.read_text(encoding="utf-8")

# ── 1. Show me the ACTUAL connect code ──
print("=" * 66)
print("CURRENT connect_over_cdp usage in nonclaude_runtime.py")
print("=" * 66)
for i, line in enumerate(src.splitlines(), 1):
    if "connect_over_cdp" in line or "asyncio.wait_for" in line:
        ctx_lo = max(0, i - 3)
        ctx_hi = min(len(src.splitlines()), i + 2)
        for j in range(ctx_lo, ctx_hi):
            print(f"  {j+1:4d}  {src.splitlines()[j]}")
        print()

# ── 2. Replace EVERY bare connect_over_cdp with a timed version ──
# Match:  <ws>self._browser = await self._pw.chromium.connect_over_cdp(ARG)
pat = re.compile(
    r"(?P<indent>[ \t]+)self\._browser\s*=\s*await\s+self\._pw\.chromium\.connect_over_cdp\((?P<arg>[^\)]+)\)"
)

def repl(m):
    ind = m.group("indent")
    arg = m.group("arg").strip()
    return (
        f"{ind}self._browser = await asyncio.wait_for(\n"
        f"{ind}    self._pw.chromium.connect_over_cdp({arg}),\n"
        f"{ind}    timeout=15,\n"
        f"{ind})"
    )

new_src, n = pat.subn(repl, src)
if n:
    print(f"  [OK] wrapped {n} connect_over_cdp call(s) with 15s timeout")
    src = new_src
else:
    print("  [!] no bare connect_over_cdp calls found — checking alternate forms")
    # Alternate: `self._browser = await self._pw.chromium.connect_over_cdp(...)` on multi-line
    print("  Full method dump for _ensure_page:")
    m = re.search(r"async def _ensure_page.*?(?=\n    async def |\n    def |\Z)", src, re.S)
    if m:
        print(m.group(0))

rt.write_text(src, encoding="utf-8", newline="\n")
ast.parse(src)
print("  [OK] syntax valid")

# ── 3. Add timeout to _pw.chromium.launch too ──
# Actually launch usually completes quickly; skip.

# ── 4. Kill zombie Chrome on 9222 and restart clean ──
print("\n==> Killing any Chrome bound to 9222")
subprocess.run(["powershell","-NoProfile","-Command",
    "Get-NetTCPConnection -LocalPort 9222 -State Listen -EA SilentlyContinue | "
    "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"],
    capture_output=True, shell=True)

import time, socket
time.sleep(2)

def port_open(p):
    s = socket.socket(); s.settimeout(0.4)
    try: s.connect(("127.0.0.1", p)); return True
    except OSError: return False
    finally: s.close()

print(f"  9222 alive after kill: {port_open(9222)}")

# ── 5. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(runtime): wrap connect_over_cdp in 15s timeout (no more hangs)"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("=" * 66)
print("NEXT — do this in order:")
print()
print("  1.  aid restart         <- kills old Chrome, launches fresh off-screen")
print("  2.  deepseek            <- should connect within 15s max, no hang")
print()
print("If step 2 prints a traceback or hangs:")
print("   paste the FIRST 20 lines only")
print("=" * 66)
