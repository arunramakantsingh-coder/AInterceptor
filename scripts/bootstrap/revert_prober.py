import pathlib, subprocess, sys, ast, re

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"

# ── 1. Enable prober in .env.windows ──
env = ROOT / ".env.windows"
txt = env.read_text(encoding="utf-8")
if "AINTERCEPTOR_PROBER_ENABLED" in txt:
    txt = re.sub(r"^AINTERCEPTOR_PROBER_ENABLED=.*$",
                 "AINTERCEPTOR_PROBER_ENABLED=1", txt, flags=re.M)
else:
    txt = txt.rstrip() + "\nAINTERCEPTOR_PROBER_ENABLED=1\n"
env.write_text(txt, encoding="utf-8", newline="\n")
print("  [OK] .env.windows: prober=1")

# ── 2. Remove the hard-coded disable from daemon.py ──
daemon = BE / "runtime" / "daemon.py"
dt = daemon.read_text(encoding="utf-8")

# Look for our inserted comment block and remove it
old = '''    # PROBER DISABLED — it writes ping/pong into real provider chats.
    # Re-enable only after implementing a non-invasive probe.
    prober = None
    print('[daemon] prober disabled (invasive — sends real chat messages)', flush=True)
'''
if old in dt:
    dt = dt.replace(old, "", 1)
    daemon.write_text(dt, encoding="utf-8", newline="\n")
    print("  [OK] daemon.py: hard-coded disable removed")
else:
    print("  [i] daemon.py: no hard-coded disable found")

# Verify daemon has a prober.start path
if "prober.start()" not in dt and "prober = HealthProber" not in dt:
    print("  [!] daemon.py: prober construction missing — inspect manually")

try:
    ast.parse(dt)
    print("  [OK] daemon.py syntax valid")
except SyntaxError as e:
    print(f"[FAIL] daemon.py: {e}"); sys.exit(1)

# ── 3. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","revert: re-enable prober (env-driven, default on)"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("Restart daemon:  .\\run-windows.ps1")
print("Watch for:       [daemon] prober started")
print()
