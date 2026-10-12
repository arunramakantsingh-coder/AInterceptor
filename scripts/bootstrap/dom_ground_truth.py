import pathlib, subprocess, sys, os, textwrap

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ── 1. Parser: current filters to RESPONSE only ──
ds = BE / "app/interception/deepseek.py"
src = ds.read_text(encoding="utf-8")

old_current = '''    @property
    def current(self) -> str:
        parts: list[str] = []
        for fragment in self._fragments:
            if str(fragment.get("type") or "").upper() == "RESPONSE":
                parts.extend(self._text_values(fragment.get("content")))
        if parts:
            return self._join_response_parts(parts)
        return self._choice_text.strip()'''

new_current = '''    @property
    def current(self) -> str:
        """Return only RESPONSE fragments joined.

        THINK fragments are internal reasoning and MUST NOT appear in output.
        If no RESPONSE fragment has arrived yet, return "" — never fall back
        to THINK text.
        """
        parts: list[str] = []
        for fragment in self._fragments:
            ftype = str(fragment.get("type") or "").upper()
            if ftype == "RESPONSE":
                parts.extend(self._text_values(fragment.get("content")))
        if parts:
            return self._join_response_parts(parts)
        return ""'''

if old_current in src:
    src = src.replace(old_current, new_current, 1)
    print("  [OK] current: RESPONSE-only")
elif 'if str(fragment.get("type") or "").upper() == "RESPONSE"' in src:
    # already RESPONSE-only, but has fallback to _choice_text.strip()
    src = src.replace(
        '''        if parts:
            return self._join_response_parts(parts)
        return self._choice_text.strip()''',
        '''        if parts:
            return self._join_response_parts(parts)
        return ""''',
        1,
    )
    print("  [OK] current: no fallback to choice text")
else:
    print("  [!] current pattern not matched")

# Also remove the fallback in the current property if we can see it
src = src.replace(
    '''        if parts:
            return self._join_response_parts(parts)
        return self._choice_text''',
    '''        if parts:
            return self._join_response_parts(parts)
        return ""''',
    1,
)

ds.write_text(src, encoding="utf-8", newline="\n")

# ── 2. Runtime: after stream finish, read DOM's last assistant message
nrt = BE / "app/interception/nonclaude_runtime.py"
nsrc = nrt.read_text(encoding="utf-8")

# Add assistant-selector to WebProviderSpec usage — insert DOM read before final yield
old_finish = '''                        if kind == "finished":
                            final = self.parser(body.decode("utf-8", errors="replace")).rstrip("\\n")
                            if final and final.startswith(emitted):
                                delta = final[len(emitted):]
                            else:
                                delta = ""
                            if delta:
                                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_DELTA, sequence, delta=delta)
                                sequence += 1
                            yield StreamEvent(self.provider, request.request_id, EventType.STREAM_COMPLETED, sequence, finish_reason="stop")
                            return'''

new_finish = '''                        if kind == "finished":
                            # Prefer the browser's rendered assistant bubble as
                            # ground truth. The CDP reconstruction is best-effort
                            # for live deltas; the DOM is authoritative for the
                            # final text.
                            dom_text = ""
                            try:
                                dom_text = await self._read_last_assistant_text()
                            except Exception:
                                dom_text = ""
                            parsed = self.parser(body.decode("utf-8", errors="replace")).rstrip("\\n")
                            # Choose whichever is longer/more complete; prefer DOM
                            final = dom_text if len(dom_text) >= len(parsed) and dom_text else parsed

                            # Emit only the suffix beyond what we already sent.
                            # If the final diverges from emitted (mid-stream
                            # corrections), find the longest common prefix and
                            # emit the remainder as one delta — never drop chars.
                            if final and final.startswith(emitted):
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
                                delta = ""
                            if delta:
                                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_DELTA, sequence, delta=delta)
                                sequence += 1
                            yield StreamEvent(self.provider, request.request_id, EventType.STREAM_COMPLETED, sequence, finish_reason="stop")
                            return'''

if old_finish in nsrc:
    nsrc = nsrc.replace(old_finish, new_finish, 1)
    print("  [OK] runtime: DOM-preferring finalization")
else:
    print("  [!] finish block not matched")

# Add the _read_last_assistant_text helper
helper = '''
    async def _read_last_assistant_text(self) -> str:
        """Read the last rendered assistant bubble from the page DOM.

        DeepSeek, ChatGPT, Gemini, Claude each render assistant messages
        differently. We try a small set of stable selectors; the first that
        yields visible text wins. This is the ground truth for the final
        reply, independent of streaming reconstruction.
        """
        selectors = (
            # DeepSeek
            '[class*="ds-markdown"]',
            'div[class*="_"]:has(> div > div.ds-markdown)',
            # generic markdown containers
            '.markdown',
            '.prose',
            # ChatGPT
            '[data-message-author-role="assistant"]',
            # Claude
            '[data-testid*="assistant"]',
            # Gemini
            'message-content',
            '.model-response-text',
        )
        for sel in selectors:
            try:
                loc = self._page.locator(sel)
                n = await loc.count()
                if n == 0:
                    continue
                last = loc.nth(n - 1)
                txt = (await last.inner_text()).strip()
                if txt:
                    return txt
            except Exception:
                continue
        return ""
'''

# Insert before _prompt_textbox
anchor = "    async def _prompt_textbox(self)"
if anchor in nsrc and "_read_last_assistant_text" not in nsrc:
    nsrc = nsrc.replace(anchor, helper + "\n" + anchor, 1)
    print("  [OK] added _read_last_assistant_text")

nrt.write_text(nsrc, encoding="utf-8", newline="\n")

# ── 3. Syntax check
r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{nrt}').read_text(encoding='utf-8')); "
    f"ast.parse(pathlib.Path(r'{ds}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("[FAIL] syntax:"); print(r.stderr); sys.exit(1)
print("  [OK] syntax valid")

# ── 4. Tests
def run(args, cwd=ROOT):
    print(f"\n$ {' '.join(str(a) for a in args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print("STDERR:", r.stderr)
    return r.returncode

if run([PY, "-m", "pytest", "-q",
        "tests/test_nonclaude_parsers.py",
        "tests/test_deepseek_think_response.py",
        "-o", "asyncio_mode=auto"], cwd=ROOT) != 0:
    print("FAIL: tests broke"); sys.exit(1)

# ── 5. Commit
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(deepseek): RESPONSE-only current; prefer DOM for final text"])
print(r.stdout.strip() or r.stderr.strip())

# ── 6. Live test
print("\n==> Live DeepSeek test")
env = os.environ.copy(); env["PYTHONUTF8"]="1"
r = subprocess.run([PY, "-u", "-m", "scripts.chat_deepseek"], cwd=BE,
    input="say hello in one short sentence\n/exit\n",
    capture_output=True, text=True, encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)
