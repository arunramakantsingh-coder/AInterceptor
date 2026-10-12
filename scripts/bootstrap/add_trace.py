import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

nrt = BE / "app/interception/nonclaude_runtime.py"
src = nrt.read_text(encoding="utf-8")

# Add debug tracer to execute wait-loop if not present
if "[trace]" not in src:
    # find the wait loop
    marker = "            # Wait for a NEW assistant bubble"
    if marker not in src:
        # maybe the newer loop — search for "DEADLINE = 90"
        marker = "            DEADLINE = 90.0"
        if marker in src:
            inject = '''            import sys as _sys
            def _tr(msg):
                print(f"[trace] {msg}", file=_sys.stderr, flush=True)

'''
            src = src.replace(marker, inject + marker, 1)
        else:
            print("  [!] cannot find wait loop")
    else:
        inject = '''            import sys as _sys
            def _tr(msg):
                print(f"[trace] {msg}", file=_sys.stderr, flush=True)
            _tr(f"before bubble count={before}")

'''
        src = src.replace(marker, inject + marker, 1)

    # also inject traces inside the loop
    loop_marker = "                count = await self._assistant_count()"
    if loop_marker in src:
        src = src.replace(loop_marker,
            loop_marker + '\n                _tr(f"poll: count={count} before={before}")',
            1)

    read_marker = "                current = await self._read_last_assistant_text()"
    if read_marker in src:
        src = src.replace(read_marker,
            read_marker + '\n                _tr(f"read: {len(current)} chars")',
            1)

    nrt.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] trace logging added")

# syntax
r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{nrt}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("[FAIL] syntax:", r.stderr); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","chore(deepseek): add trace logging in execute() wait loop"])
print(r.stdout.strip() or r.stderr.strip())
