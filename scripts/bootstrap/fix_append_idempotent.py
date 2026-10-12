import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

ds = BE / "app/interception/deepseek.py"
src = ds.read_text(encoding="utf-8")

# Revert my merge-per-fragment _extract_snapshot back to replace-all
old_snap = '''            fragments = response.get("fragments")
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

new_snap = '''            fragments = response.get("fragments")
            if isinstance(fragments, list):
                self._fragments = [self._clone_fragment(item) for item in fragments]
                found = True'''

if old_snap in src:
    src = src.replace(old_snap, new_snap, 1)
    print("  [OK] _extract_snapshot reverted to replace-all")
else:
    print("  [!] snapshot pattern not matched")

# Add suffix-guard to _append_content (idempotent APPEND)
old_append = '''    def _append_content(self, fragment: dict[str, Any], value: Any) -> None:
        incoming = "".join(self._text_values(value))
        if incoming:
            existing = "".join(self._text_values(fragment.get("content")))
            fragment["content"] = self._merge_append(existing, incoming)'''

new_append = '''    def _append_content(self, fragment: dict[str, Any], value: Any) -> None:
        incoming = "".join(self._text_values(value))
        if not incoming:
            return
        existing = "".join(self._text_values(fragment.get("content")))
        # Idempotency: if the incoming text already appears at the end of the
        # fragment (replayed cumulative frame), do not duplicate it.
        if existing.endswith(incoming) and len(existing) >= len(incoming):
            return
        fragment["content"] = self._merge_append(existing, incoming)'''

if old_append in src:
    src = src.replace(old_append, new_append, 1)
    print("  [OK] _append_content: idempotent suffix-guard")
else:
    print("  [!] append_content pattern not matched")

ds.write_text(src, encoding="utf-8", newline="\n")

def run(args, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print(r.stderr)
    return r.returncode

rc = run([PY, "-m", "pytest", "-q", "tests/test_nonclaude_parsers.py",
          "tests/test_deepseek_think_response.py", "-o", "asyncio_mode=auto"], cwd=ROOT)
if rc != 0:
    print("tests broke"); sys.exit(1)

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(deepseek): idempotent append via suffix guard; revert snapshot merge"])
print(r.stdout.strip() or r.stderr.strip())

print("\n==> live test")
import os
env = os.environ.copy(); env["PYTHONUTF8"]="1"
r = subprocess.run([PY, "-u", "-m", "scripts.chat_deepseek"], cwd=BE,
    input="hello there 42\n/exit\n", capture_output=True, text=True,
    encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)
