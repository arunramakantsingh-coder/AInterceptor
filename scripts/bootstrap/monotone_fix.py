import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ── 1. Parser: monotone (never return shorter than previous best) ──
ds = BE / "app/interception/deepseek.py"
src = ds.read_text(encoding="utf-8")

# init: add _last_result
if "_last_result" not in src:
    import re
    m = re.search(r"(def __init__\(self\)[^\n]*:\n)", src)
    if m:
        src = src[:m.end()] + "        self._last_result: str = \"\"\n" + src[m.end():]
        print("  [OK] added _last_result")

old_call = '''    def __call__(self, cumulative_body: str) -> str:
        """Feed a growing cumulative body; never lose already-parsed state.

        If the new body starts with what we've seen: parse only the new suffix.
        If the body diverges (rare, provider rewrite): replay the ENTIRE body
        against a fresh parser, then adopt that as authoritative — the caller
        can diff old vs new at the string level.
        """
        if not isinstance(cumulative_body, str):
            return self.current
        if cumulative_body.startswith(self._cumulative_body_seen):
            suffix = cumulative_body[len(self._cumulative_body_seen):]
            self._cumulative_body_seen = cumulative_body
            return self.feed(suffix)

        # Diverged: full replay, keep old fragments as a fallback if replay yields less
        prior = self.current
        self.__init__()
        result = self.feed(cumulative_body)
        # Never return less content than we already had
        if len(result) < len(prior):
            return prior
        self._cumulative_body_seen = cumulative_body
        return result'''

new_call = '''    def __call__(self, cumulative_body: str) -> str:
        """Feed a growing cumulative body. Output is MONOTONE:
        the returned string never shrinks across calls.
        """
        if not isinstance(cumulative_body, str):
            return self._last_result or self.current

        if cumulative_body.startswith(self._cumulative_body_seen):
            suffix = cumulative_body[len(self._cumulative_body_seen):]
            self._cumulative_body_seen = cumulative_body
            candidate = self.feed(suffix)
        else:
            # Diverged: full replay, but never lose previously-seen content.
            prior = self.current
            self.__init__()
            self._last_result = prior
            candidate = self.feed(cumulative_body)
            self._cumulative_body_seen = cumulative_body

        # Monotone: keep the longest text ever produced.
        if candidate and len(candidate) >= len(self._last_result):
            self._last_result = candidate
        return self._last_result'''

if old_call in src:
    src = src.replace(old_call, new_call, 1)
    print("  [OK] parser __call__ monotone")
else:
    print("  [!] __call__ pattern not matched")

ds.write_text(src, encoding="utf-8", newline="\n")

# ── 2. Runtime: prefer LONGER of {parsed, dom}; monotone final ──
nrt = BE / "app/interception/nonclaude_runtime.py"
nsrc = nrt.read_text(encoding="utf-8")

# 2a. Simplify DOM reader: just .ds-markdown, no strip
old_helper_start = nsrc.find("    async def _read_last_assistant_text")
if old_helper_start != -1:
    nxt = nsrc.find("\n    async def ", old_helper_start + 10)
    if nxt == -1: nxt = nsrc.find("\n    def ", old_helper_start + 10)
    if nxt == -1: nxt = len(nsrc)
    new_helper = '''    async def _read_last_assistant_text(self) -> str:
        """Read the last rendered assistant bubble. Prefers DeepSeek's own
        markdown container class. Falls back to generic selectors. Does NOT
        strip children — the response container already excludes thinking.
        """
        try:
            text = await self._page.evaluate(r"""
                () => {
                    const sels = [
                        '.ds-markdown',
                        '.ds-markdown--block',
                        '[class*="ds-markdown"]',
                        '[data-message-author-role="assistant"]',
                        '.model-response-text',
                        'message-content',
                    ];
                    let candidates = [];
                    for (const s of sels) {
                        document.querySelectorAll(s).forEach(el => {
                            if (el.offsetParent !== null) candidates.push(el);
                        });
                    }
                    if (candidates.length === 0) return "";
                    // pick the longest text
                    let best = candidates[0];
                    for (const c of candidates) {
                        if ((c.innerText || "").length > (best.innerText || "").length) {
                            best = c;
                        }
                    }
                    return (best.innerText || "").trim();
                }
            """)
            return (text or "").strip()
        except Exception:
            return ""
'''
    nsrc = nsrc[:old_helper_start] + new_helper + nsrc[nxt:]
    print("  [OK] DOM reader simplified")

# 2b. Final: prefer the LONGER of parsed and DOM
old_fin = '''                            parsed = self.parser(body.decode("utf-8", errors="replace")).rstrip("\\n")
                            # Choose whichever is longer/more complete; prefer DOM
                            final = dom_text if len(dom_text) >= len(parsed) and dom_text else parsed'''
new_fin = '''                            parsed = self.parser(body.decode("utf-8", errors="replace")).rstrip("\\n")
                            # Prefer whichever text is longer — the parser can
                            # legitimately miss fragments; the DOM can miss
                            # streaming context. Longer wins.
                            final = dom_text if len(dom_text) > len(parsed) else parsed'''
if old_fin in nsrc:
    nsrc = nsrc.replace(old_fin, new_fin, 1)
    print("  [OK] runtime final: longer wins")

# 2c. Final emit: monotone — never emit shorter, only suffix beyond emitted
old_emit = '''                            if final and final.startswith(emitted):
                                delta = final[len(emitted):]
                            elif final and emitted and final != emitted:
                                # longest common prefix
                                cp = 0
                                for a, b in zip(final, emitted):
                                    if a != b: break
                                    cp += 1
                                if cp >= len(emitted) - 2:
                                    delta = final[cp:]
                                else:
                                    delta = "\\n" + final
                            else:
                                delta = ""'''
new_emit = '''                            if final and final.startswith(emitted):
                                delta = final[len(emitted):]
                            else:
                                delta = ""'''
if old_emit in nsrc:
    nsrc = nsrc.replace(old_emit, new_emit, 1)
    print("  [OK] runtime final emit: strict prefix only")

nrt.write_text(nsrc, encoding="utf-8", newline="\n")

# ── 3. Syntax check ──
r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{nrt}').read_text(encoding='utf-8')); "
    f"ast.parse(pathlib.Path(r'{ds}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("[FAIL] syntax:"); print(r.stderr); sys.exit(1)
print("  [OK] syntax valid")

# ── 4. Tests ──
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

# ── 5. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(deepseek): monotone parser + strict-prefix final emit; DOM = .ds-markdown only"])
print(r.stdout.strip() or r.stderr.strip())

# ── 6. Live test ──
print("\n==> Live 2-turn test")
import os
env = os.environ.copy(); env["PYTHONUTF8"]="1"
r = subprocess.run([PY, "-u", "-m", "scripts.chat_deepseek"], cwd=BE,
    input="hi who are you\nwhat can you do\n/exit\n",
    capture_output=True, text=True, encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)
