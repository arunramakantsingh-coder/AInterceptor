import pathlib, sys, ast

pb = pathlib.Path("backend") / "app" / "runtime" / "path_b.py"
src = pb.read_text(encoding="utf-8")

# Show the broken region
lines = src.splitlines()
print("==> Lines 20-45 (broken region):")
for i in range(19, min(45, len(lines))):
    print(f"  {i+1:3d}  {lines[i]}")
print()

# Fix: ensure class PathBError has a body
old = "class PathBError(Exception):\n\n\n_PROVIDER_LOCKS"
new = "class PathBError(Exception):\n    pass\n\n\n_PROVIDER_LOCKS"

if old in src:
    src = src.replace(old, new, 1)
    print("  [OK] restored 'pass' in PathBError")
else:
    # try alternate spacing
    alt_old = "class PathBError(Exception):\n\n_PROVIDER_LOCKS"
    alt_new = "class PathBError(Exception):\n    pass\n\n_PROVIDER_LOCKS"
    if alt_old in src:
        src = src.replace(alt_old, alt_new, 1)
        print("  [OK] restored 'pass' (alt pattern)")
    else:
        print("  [!] pattern not found — inspect manually")
        # dump exact bytes around class def
        idx = src.find("class PathBError")
        if idx != -1:
            print(f"  raw bytes: {src[idx:idx+120]!r}")

pb.write_text(src, encoding="utf-8", newline="\n")

# verify
try:
    ast.parse(pb.read_text(encoding="utf-8"))
    print("  [OK] syntax valid")
except SyntaxError as e:
    print(f"[FAIL] still broken: {e}")
    # show a wider range
    lines = pb.read_text(encoding="utf-8").splitlines()
    for i in range(max(0, e.lineno - 8), min(len(lines), e.lineno + 4)):
        marker = ">>>" if i + 1 == e.lineno else "   "
        print(f"  {marker} {i+1:3d}  {lines[i]}")
    sys.exit(1)

def git(a):
    return subprocess.run(["git"]+a, cwd=pathlib.Path("."), capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(path_b): restore PathBError class body (broken by lock patch)"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("Now try starting the daemon:")
print("  .\\run-windows.ps1")
