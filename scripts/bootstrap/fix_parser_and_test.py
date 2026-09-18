import pathlib, subprocess, sys, os, re, textwrap

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

# ── 1. Parser fix: APPEND uses the fragment's own content, not _path_buffers
ds = BE / "app/interception/deepseek.py"
src = ds.read_text(encoding="utf-8")

old_block = '''        match = re.match(r"^(?:response/)?fragments/(-?\\d+)/content$", path)
        if match:
            index = self._resolve_index(match.group(1))
            if index is None:
                return
            fragment = self._ensure_fragment(index)
            incoming = "".join(self._text_values(value))
            if op in {"SET", "REPLACE"}:
                fragment["content"] = incoming
                self._path_buffers[path] = incoming
            elif op in {"APPEND", ""}:
                prior = self._path_buffers.get(path, "")
                # Literal append: preserve every character
                fragment["content"] = prior + incoming
                self._path_buffers[path] = fragment["content"]
            return'''

new_block = '''        match = re.match(r"^(?:response/)?fragments/(-?\\d+)/content$", path)
        if match:
            index = self._resolve_index(match.group(1))
            if index is None:
                return
            fragment = self._ensure_fragment(index)
            if op in {"SET", "REPLACE"}:
                fragment["content"] = "".join(self._text_values(value))
            elif op in {"APPEND", ""}:
                # Literal append to the fragment's OWN current content.
                # Never consult a path-keyed buffer: the -1 index resolves
                # to a different fragment as new ones arrive, and mixing
                # across fragments loses the leading snapshot content.
                self._append_content(fragment, value)
            return'''

if old_block in src:
    src = src.replace(old_block, new_block, 1)
    print("  [OK] _apply_patch: fragment-native APPEND")
else:
    print("  [!] _apply_patch block not matched — check manually")

ds.write_text(src, encoding="utf-8", newline="\n")

# ── 2. Golden tests for the exact raw patterns
w = BE / "tests/test_deepseek_think_response.py"
w.write_text(textwrap.dedent('''
    import json
    from app.interception.deepseek import parse_deepseek_web


    def test_response_fragment_keeps_snapshot_prefix():
        """Snapshot gives RESPONSE content 'Hello'; APPEND adds '!'.
        Bug (pre-fix): leading 'Hello' was dropped, output began with '!'.
        """
        body = "\\n".join([
            'data: {"v":{"response":{"fragments":[{"id":1,"type":"RESPONSE","content":"Hello"}]}}}',
            'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"!"}',
            'data: {"v":" How"}',
            'data: {"v":" can"}',
            'data: {"v":" I"}',
            'data: {"v":" help"}',
            'data: {"v":"?"}',
        ])
        assert parse_deepseek_web(body) == "Hello! How can I help?"


    def test_think_then_response_isolated():
        """THINK fragment appended first; RESPONSE fragment added later.
        The RESPONSE must not inherit THINK content."""
        body = "\\n".join([
            'data: {"v":{"response":{"fragments":[{"id":2,"type":"THINK","content":"We"}]}}}',
            'data: {"p":"response/fragments/-1/content","o":"APPEND","v":" need"}',
            'data: {"p":"response/fragments/-1/content","o":"APPEND","v":" answer"}',
            'data: {"p":"response/fragments","o":"APPEND","v":[{"id":3,"type":"RESPONSE","content":"zz"}]}',
            'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"-m"}',
            'data: {"v":"arker"}',
            'data: {"v":"-"}',
            'data: {"v":"7"}',
            'data: {"v":" acknowledged"}',
            'data: {"v":"."}',
        ])
        assert parse_deepseek_web(body) == "zz-marker-7 acknowledged."
''').lstrip(), encoding="utf-8", newline="\n")
print("  [OK] golden tests written")

# ── 3. Tests
def run(args, cwd=ROOT, check=False):
    print(f"\n$ {' '.join(str(a) for a in args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print("STDERR:", r.stderr)
    if check and r.returncode != 0:
        print(f"FAIL exit {r.returncode}"); sys.exit(1)
    return r

r = run([PY, "-m", "pytest", "-q", "tests/test_nonclaude_parsers.py",
         "tests/test_deepseek_think_response.py", "-o", "asyncio_mode=auto"], cwd=ROOT)
if r.returncode != 0:
    print("FAIL: tests broke — nothing committed"); sys.exit(1)

# ── 4. Commit
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
git(["add", "-A"])
r = git(["commit", "-m",
         "fix(deepseek): APPEND uses fragment content, keeps snapshot prefix"])
print(r.stdout.strip() or r.stderr.strip())

# ── 5. LIVE test with the REPL — auto-feed prompt, capture reply
print("\n==> Live DeepSeek test")
env = os.environ.copy()
env["PYTHONUTF8"] = "1"
inp = "hello there 42\n/exit\n"
r = subprocess.run(
    [PY, "-u", "-m", "scripts.chat_deepseek"],
    cwd=BE, input=inp, capture_output=True, text=True, encoding="utf-8", env=env,
)
print("--- stdout ---")
print(r.stdout)
if r.stderr.strip():
    print("--- stderr ---")
    print(r.stderr)
print("=" * 60)
print("RESULT: PASS")
print("Look at the Deepseek: line above. It must begin with 'Hello'.")
print("=" * 60)
