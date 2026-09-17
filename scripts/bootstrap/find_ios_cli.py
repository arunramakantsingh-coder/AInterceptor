import subprocess, pathlib, re, sys

ROOT = pathlib.Path.cwd()

def run(args):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, shell=True)
    return (r.stdout or "").strip(), (r.stderr or "").strip()

def hr(t):
    print(); print("=" * 68); print(t); print("=" * 68)

# Cisco-IOS vocabulary to look for
KEYS = [
    "AIRouter>", "AIRouter#", "AIRouter(", "enable", "configure terminal",
    "conf t", "show run", "show version", "show interfaces", "no shutdown",
    "write memory", "copy run start", "boot system", "boot config",
    "nvram", "startup-config", "running-config", "cisco", "ios",
    "subsystem", "control plane", "privileged exec", "user exec",
]

hr("1. FILES NAMED LIKE A CISCO-IOS CLI")
out, _ = run(["git", "ls-files"])
files = out.split("\n") if out else []
for f in files:
    if any(k in f.lower() for k in ["nos", "ios", "shell", "main", "chat", "registry", "config_store", "renderer"]):
        print(" ", f)

hr("2. GREP FOR EACH KEY IN TRACKED FILES")
for k in KEYS:
    o, _ = run(["git", "grep", "-n", "-i", "--", k])
    if o:
        print(f"\n--- {k!r} ---")
        print(o[:800])

hr("3. FULL FILE LIST UNDER cli/")
cli = ROOT / "cli"
if cli.exists():
    for f in sorted(cli.rglob("*.py")):
        print(f"  {f.relative_to(ROOT)}  ({f.stat().st_size} bytes)")

hr("4. ENTRYPOINTS (pyproject.toml)")
pp = ROOT / "pyproject.toml"
if pp.exists():
    txt = pp.read_text(encoding="utf-8")
    # print scripts / entry-points sections
    for line in txt.splitlines():
        if "airouter" in line.lower() or "scripts" in line.lower() or "entry" in line.lower() or "=" in line and "console" in txt[:line.find("=")]:
            print("  ", line)

hr("5. GIT HISTORY: COMMITS THAT TOUCHED cli/ OR nos/")
o, _ = run(["git", "log", "--all", "--oneline", "--", "cli/"])
print(o or "(none)")
o, _ = run(["git", "log", "--all", "--oneline", "--", "cli/nos.py"])
print("\nnos.py history:")
print(o or "(none)")

hr("6. GIT HISTORY: ANY COMMIT MESSAGE MENTIONING IOS/NOS/CLI")
for term in ["ios", "nos", "cli", "shell", "airouter", "boot"]:
    o, _ = run(["git", "log", "--all", "--oneline", "--grep="+term, "-i", "-20"])
    if o:
        print(f"\n--- grep={term} ---")
        print(o)

hr("7. RECENT STATE: FULL CLI MAIN")
main = ROOT / "cli" / "main.py"
if main.exists():
    print(main.read_text(encoding="utf-8", errors="replace")[:3000])

hr("8. RECENT STATE: FULL cli/nos.py (if exists)")
nos = ROOT / "cli" / "nos.py"
if nos.exists():
    print(nos.read_text(encoding="utf-8", errors="replace")[:4000])

hr("9. RECENT STATE: FULL cli/shell.py (if exists)")
sh = ROOT / "cli" / "shell.py"
if sh.exists():
    print(sh.read_text(encoding="utf-8", errors="replace")[:4000])

hr("10. WHEN WAS nos.py LAST TOUCHED / DELETED?")
o, _ = run(["git", "log", "--all", "--diff-filter=D", "--oneline", "--summary", "--", "cli/nos.py"])
print("deleted history:")
print(o or "(not deleted)")

o, _ = run(["git", "log", "--all", "--oneline", "--", "cli/nos.py"])
print("\nfull history of nos.py (in case it lived somewhere else):")
print(o or "(none)")

hr("RESULT")
print("RESULT: PASS")
print("Paste the entire output above.")
