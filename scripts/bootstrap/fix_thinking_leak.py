import pathlib, subprocess, sys, os

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ── 1. Silence repeated CDP print (only print first time) ──
nrt = BE / "app/interception/nonclaude_runtime.py"
nsrc = nrt.read_text(encoding="utf-8")

old_print = '''        print(f"[interception] {self.provider}: CDP -> {self.cdp_url}")'''
new_print = '''        if not getattr(self, "_cdp_logged", False):
            print(f"[interception] {self.provider}: CDP -> {self.cdp_url}")
            self._cdp_logged = True'''
if old_print in nsrc:
    nsrc = nsrc.replace(old_print, new_print, 1)
    print("  [OK] CDP print: once per runtime")

# Ensure _cdp_logged init
if "_cdp_logged" not in nsrc.split("def __init__")[1][:600]:
    import re
    m = re.search(r"(def __init__\(self[^\n]*\)[^\n]*:\n)", nsrc)
    if m:
        nsrc = nsrc[:m.end()] + "        self._cdp_logged = False\n" + nsrc[m.end():]
        print("  [OK] added _cdp_logged init")

# ── 2. Replace _read_last_assistant_text with thinking-excluding version ──
old_helper_start = nsrc.find("    async def _read_last_assistant_text")
if old_helper_start != -1:
    # find next method
    nxt = nsrc.find("\n    async def ", old_helper_start + 10)
    if nxt == -1:
        nxt = nsrc.find("\n    def ", old_helper_start + 10)
    if nxt == -1:
        nxt = len(nsrc)
    new_helper = '''    async def _read_last_assistant_text(self) -> str:
        """Return the last assistant reply's text, EXCLUDING any visible
        thinking/reasoning block. Uses page.evaluate so we can filter out
        thinking subtrees via class/attribute heuristics.
        """
        try:
            text = await self._page.evaluate(r"""
                () => {
                    // Candidate assistant containers, newest last.
                    const candidates = [];
                    const sels = [
                        '[class*="ds-markdown"]',
                        '[data-message-author-role="assistant"]',
                        '[data-testid*="assistant"]',
                        '.model-response-text',
                        'message-content',
                        '.prose',
                        '.markdown'
                    ];
                    for (const s of sels) {
                        document.querySelectorAll(s).forEach(el => candidates.push(el));
                    }
                    if (candidates.length === 0) return "";

                    // Pick the deepest last candidate (most specific).
                    let best = candidates[candidates.length - 1];
                    // Prefer the one with the deepest DOM (longest text).
                    for (const c of candidates) {
                        const t = (c.innerText || "").length;
                        const bt = (best.innerText || "").length;
                        if (t > bt) best = c;
                    }

                    // Clone and strip thinking blocks before reading text.
                    const clone = best.cloneNode(true);
                    const kill = [
                        '[class*="think"]',
                        '[class*="reason"]',
                        '[class*="analysis"]',
                        '[class*="chain-of-thought"]',
                        'details',
                        'summary'
                    ];
                    for (const k of kill) {
                        clone.querySelectorAll(k).forEach(n => n.remove());
                    }
                    return (clone.innerText || "").trim();
                }
            """)
            return text or ""
        except Exception:
            return ""
'''
    nsrc = nsrc[:old_helper_start] + new_helper + nsrc[nxt:]
    print("  [OK] _read_last_assistant_text: strips thinking blocks")

nrt.write_text(nsrc, encoding="utf-8", newline="\n")

# ── 3. Parser: refuse to emit anything until a RESPONSE fragment exists ──
ds = BE / "app/interception/deepseek.py"
dsrc = ds.read_text(encoding="utf-8")
# already RESPONSE-only; double-ensure no fallback
dsrc = dsrc.replace(
    '''        if parts:
            return self._join_response_parts(parts)
        return self._choice_text.strip()''',
    '''        if parts:
            return self._join_response_parts(parts)
        return ""''',
    1,
)
ds.write_text(dsrc, encoding="utf-8", newline="\n")

# ── 4. Syntax check ──
r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{nrt}').read_text(encoding='utf-8')); "
    f"ast.parse(pathlib.Path(r'{ds}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("[FAIL] syntax:"); print(r.stderr); sys.exit(1)
print("  [OK] syntax valid")

# ── 5. Tests ──
def run(args, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print(r.stderr)
    return r.returncode

if run([PY, "-m", "pytest", "-q",
        "tests/test_nonclaude_parsers.py",
        "tests/test_deepseek_think_response.py",
        "-o", "asyncio_mode=auto"], cwd=ROOT) != 0:
    print("FAIL: tests broke"); sys.exit(1)

# ── 6. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(deepseek): silence repeated CDP print; strip thinking from DOM read"])
print(r.stdout.strip() or r.stderr.strip())

# ── 7. Live test with two prompts ──
print("\n==> Live DeepSeek test (2 turns)")
env = os.environ.copy(); env["PYTHONUTF8"]="1"
r = subprocess.run([PY, "-u", "-m", "scripts.chat_deepseek"], cwd=BE,
    input="hi who are you\nwhat can you do\n/exit\n",
    capture_output=True, text=True, encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)
