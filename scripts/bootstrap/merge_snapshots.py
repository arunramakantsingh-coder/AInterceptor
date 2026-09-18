import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

ds = BE / "app/interception/deepseek.py"
src = ds.read_text(encoding="utf-8")

old = '''            fragments = response.get("fragments")
            if isinstance(fragments, list):
                self._fragments = [self._clone_fragment(item) for item in fragments]
                found = True'''

new = '''            fragments = response.get("fragments")
            if isinstance(fragments, list):
                # Merge snapshot into existing fragments. A snapshot may be
                # shorter than what we already have (partial state); never
                # truncate a fragment we already extended.
                for idx, item in enumerate(fragments):
                    clone = self._clone_fragment(item)
                    while len(self._fragments) <= idx:
                        self._fragments.append({"type": "RESPONSE", "content": ""})
                    existing = "".join(self._text_values(self._fragments[idx].get("content")))
                    incoming = "".join(self._text_values(clone.get("content")))
                    if len(incoming) >= len(existing):
                        self._fragments[idx] = clone
                    else:
                        # keep longer prior content
                        merged = dict(clone)
                        merged["content"] = existing
                        self._fragments[idx] = merged
                found = True'''

if old in src:
    src = src.replace(old, new, 1)
    ds.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] _extract_snapshot: merge instead of replace")
else:
    print("  [!] pattern not matched")

def run(args, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print(r.stderr)
    return r.returncode

if run([PY, "-m", "pytest", "-q", "tests/test_nonclaude_parsers.py",
        "tests/test_deepseek_think_response.py", "-o", "asyncio_mode=auto"], cwd=ROOT) != 0:
    print("tests broke"); sys.exit(1)

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(deepseek): merge snapshots, never truncate extended fragments"])
print(r.stdout.strip() or r.stderr.strip())

print("\n==> live test")
import os
env = os.environ.copy(); env["PYTHONUTF8"]="1"
r = subprocess.run([PY, "-u", "-m", "scripts.chat_deepseek"], cwd=BE,
    input="hello there 42\n/exit\n", capture_output=True, text=True,
    encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)
