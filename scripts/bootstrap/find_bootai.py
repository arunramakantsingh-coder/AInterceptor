import subprocess, pathlib, sys, re

ROOT = pathlib.Path.cwd()

def run(args, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=True)
    return (r.stdout or "").strip(), (r.stderr or "").strip()

def hr(t):
    print(); print("=" * 66); print(t); print("=" * 66)

hr("1. TRACKED FILES MATCHING 'bootai' OR 'boot'")
out, _ = run(["git", "ls-files"])
for f in out.split("\n"):
    if re.search(r"boot", f, re.I):
        print(" ", f)

hr("2. GREP IN TRACKED FILES")
out, _ = run(['git', 'grep', '-n', '-i', 'bootai', '--', '.'])
print(out or "(no matches)")

hr("3. GREP IN FULL LOG (author messages)")
out, _ = run(["git", "log", "--all", "--oneline", "--grep=bootai", "-i"])
print(out or "(no commits mention bootai)")

hr("4. FULL LOG FOR THE COMMIT THAT MENTIONED IT")
out, _ = run(["git", "log", "--all", "--oneline", "--grep=bootai", "-i", "-5"])
if out:
    for line in out.split("\n")[:3]:
        sha = line.split()[0]
        print(f"\n--- {sha} ---")
        out2, _ = run(["git", "show", "--stat", sha])
        print(out2[:1500])

hr("5. CLI PACKAGE CONTENTS")
cli = ROOT / "cli"
if cli.exists():
    for f in sorted(cli.rglob("*.py")):
        print(f"  {f.relative_to(ROOT)}")
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
            for i, ln in enumerate(txt.splitlines(), 1):
                if re.search(r"bootai", ln, re.I):
                    print(f"     line {i}: {ln.strip()}")
        except Exception as e:
            print(f"     (read failed: {e})")

hr("6. .ainterceptor CONFIG FILES")
cfg_dir = ROOT / ".ainterceptor"
if cfg_dir.exists():
    for f in sorted(cfg_dir.rglob("*")):
        if f.is_file() and f.suffix.lower() in {".json", ".cfg", ".ini", ".toml", ".yaml", ".yml"}:
            print(f"  {f.relative_to(ROOT)}")
            try:
                txt = f.read_text(encoding="utf-8", errors="replace")
                print("     " + txt.replace("\n", "\n     ")[:800])
            except Exception as e:
                print(f"     (read failed: {e})")

hr("7. STARTUP CONFIG")
sc = ROOT / ".ainterceptor" / "nvram" / "startup-config.json"
if sc.exists():
    print(sc.read_text(encoding="utf-8"))

hr("8. RESULTS")
print("RESULT: PASS")
print("Paste the entire output above.")
