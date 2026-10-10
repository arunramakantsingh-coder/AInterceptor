import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

nrt = BE / "app/interception/nonclaude_runtime.py"
src = nrt.read_text(encoding="utf-8")

# ── 1. Silence per-turn print; log once per runtime ──
# Find every print of the CDP line and gate it
old_print = '''        if not getattr(self, "_cdp_logged", False):
            print(f"[interception] {self.provider}: CDP -> {self.cdp_url}")
            self._cdp_logged = True'''
new_print = '''        if not getattr(self, "_cdp_logged", False):
            self._cdp_logged = True'''

if old_print in src:
    src = src.replace(old_print, new_print, 1)
    print("  [OK] silenced per-turn CDP print")
else:
    # old un-gated form
    old2 = '''        print(f"[interception] {self.provider}: CDP -> {self.cdp_url}")'''
    if old2 in src:
        src = src.replace(old2, '', 1)
        print("  [OK] removed un-gated CDP print")

# ── 2. Add port-attachment recorder ──
# Append to .ainterceptor/ports.log when a runtime first attaches to a CDP port.
if "_record_port_attachment" not in src:
    import re
    # add method to NonClaudeWebRuntime class
    anchor = "    async def _ensure_page(self, interactive: bool = False) -> None:"
    helper = '''    def _record_port_attachment(self) -> None:
        """Append a line to .ainterceptor/ports.log the first time this
        runtime attaches to a provider CDP endpoint. Format:
            2026-09-18T12:34:56Z  deepseek  http://127.0.0.1:9223
        """
        try:
            import datetime as _dt
            log_dir = pathlib.Path(".ainterceptor")
            log_dir.mkdir(parents=True, exist_ok=True)
            line = (
                _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                + f"  {self.provider:<10} {self.cdp_url}\\n"
            )
            with open(log_dir / "ports.log", "a", encoding="utf-8") as fh:
                fh.write(line)
        except Exception:
            pass

'''
    if anchor in src:
        src = src.replace(anchor, helper + anchor, 1)
        print("  [OK] added _record_port_attachment")

    # call it right after CDP is resolved in _ensure_page
    old_resolve = '''            self.cdp_url = provider_registry.cdp_url(self.provider)
        if not getattr(self, "_cdp_logged", False):
            self._cdp_logged = True'''
    new_resolve = '''            self.cdp_url = provider_registry.cdp_url(self.provider)
        if not getattr(self, "_cdp_logged", False):
            self._cdp_logged = True
            self._record_port_attachment()'''
    if old_resolve in src:
        src = src.replace(old_resolve, new_resolve, 1)
        print("  [OK] port attachment recorded on first attach")
    else:
        # fallback: insert after first CDP assignment
        import re as _re
        m = _re.search(r"(self\.cdp_url = provider_registry\.cdp_url\(self\.provider\)\n)", src)
        if m:
            src = src[:m.end()] + "        self._record_port_attachment()\n" + src[m.end():]
            print("  [OK] port attachment call inserted")

nrt.write_text(src, encoding="utf-8", newline="\n")

# ── 3. Also fix the *other* interceptor file (deepseek.py) if it prints ──
ds = BE / "app/interception/deepseek.py"
dsrc = ds.read_text(encoding="utf-8")
for old in [
    '''        print(f"[interception] {self.provider}: CDP -> {self.cdp_url}")''',
]:
    if old in dsrc:
        dsrc = dsrc.replace(old, '', 1)
        print("  [OK] removed stray print in deepseek.py")
ds.write_text(dsrc, encoding="utf-8", newline="\n")

# ── 4. Ensure ports.log is gitignored ──
gi = ROOT / ".gitignore"
g = gi.read_text(encoding="utf-8") if gi.exists() else ""
if ".ainterceptor/ports.log" not in g:
    gi.write_text(g.rstrip() + "\n.ainterceptor/ports.log\n", encoding="utf-8", newline="\n")
    print("  [OK] .ainterceptor/ports.log gitignored")

# ── 5. Syntax + tests ──
r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{nrt}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("[FAIL] syntax:", r.stderr); sys.exit(1)
print("  [OK] syntax valid")

def run(args, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print(r.stderr)
    return r.returncode

run([PY, "-m", "pytest", "-q",
     "tests/test_nonclaude_parsers.py",
     "tests/test_deepseek_think_response.py",
     "-o", "asyncio_mode=auto"], cwd=ROOT)

# ── 6. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(cli): silence per-turn CDP print; log port attachments to .ainterceptor/ports.log"])
print(r.stdout.strip() or r.stderr.strip())

# ── 7. Live test — expect NO [interception] lines in output ──
print("\n==> Live test — should print replies only")
import os as _os
env = _os.environ.copy(); env["PYTHONUTF8"]="1"
r = subprocess.run([PY, "-u", "-m", "scripts.chat_deepseek"], cwd=BE,
    input="hi\nwhat can you do\n/exit\n",
    capture_output=True, text=True, encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)

# ── 8. Show recorded ports ──
print("\n==> .ainterceptor/ports.log")
log = ROOT / ".ainterceptor" / "ports.log"
if log.exists():
    print(log.read_text(encoding="utf-8"))
else:
    print("(empty)")
