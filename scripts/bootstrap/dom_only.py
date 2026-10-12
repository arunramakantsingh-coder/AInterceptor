import pathlib, subprocess, sys
ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ── Replace execute() with DOM-only: submit, wait for stable assistant bubble ──
nrt = BE / "app/interception/nonclaude_runtime.py"
src = nrt.read_text(encoding="utf-8")

start = src.find("    async def execute(self, request: ProviderExecutionRequest)")
end   = src.find("\n    async def close(self)")
if start == -1 or end == -1:
    print("[FAIL] cannot find execute/close bounds"); sys.exit(1)

new_execute = '''    async def execute(self, request: ProviderExecutionRequest):
        """Submit prompt, wait for assistant bubble to stabilise, return it.

        Transport-layer decoding is intentionally NOT used here. The DOM is
        the authoritative source for the reply text. Provider-specific
        transport decoders remain available for future streaming work but
        are not on the critical path.
        """
        if request.provider != self.provider:
            raise ValueError(f"runtime provider mismatch: {request.provider}")
        await self.start()

        prompt = next(
            (m.get("content", "") for m in reversed(request.messages)
             if m.get("role") == "user"), ""
        )
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("execution requires a non-empty user message")

        async with self._lock:
            seq = 0
            yield StreamEvent(self.provider, request.request_id,
                              EventType.REQUEST_INTERCEPTED, seq,
                              metadata={"transport": "dom"})
            seq += 1

            # Snapshot current number of assistant bubbles
            before = await self._assistant_count()

            # Submit
            try:
                await self._page.bring_to_front()
                box = await self._prompt_textbox()
                await box.fill(prompt)
                await box.press("Enter")
            except Exception as exc:
                yield StreamEvent(self.provider, request.request_id,
                                  EventType.STREAM_FAILED, seq,
                                  metadata={"reason": f"submit_failed: {exc}"})
                return

            yield StreamEvent(self.provider, request.request_id,
                              EventType.STREAM_STARTED, seq,
                              metadata={"transport": "dom"})
            seq += 1

            # Wait for a NEW assistant bubble
            text = ""
            stable_reads = 0
            for _ in range(120):  # up to 60s
                await asyncio.sleep(0.5)
                count = await self._assistant_count()
                if count <= before:
                    continue
                current = await self._read_last_assistant_text()
                if current and current == text and len(current) > 0:
                    stable_reads += 1
                    if stable_reads >= 2:
                        break
                else:
                    stable_reads = 0
                    text = current

            if not text:
                yield StreamEvent(self.provider, request.request_id,
                                  EventType.STREAM_FAILED, seq,
                                  metadata={"reason": "no assistant reply observed"})
                return

            yield StreamEvent(self.provider, request.request_id,
                              EventType.STREAM_DELTA, seq, delta=text)
            seq += 1
            yield StreamEvent(self.provider, request.request_id,
                              EventType.STREAM_COMPLETED, seq,
                              finish_reason="stop")
            return

    async def _assistant_count(self) -> int:
        sels = ['.ds-markdown', '[data-message-author-role="assistant"]',
                '.model-response-text', 'message-content']
        for s in sels:
            try:
                n = await self._page.locator(s).count()
                if n > 0:
                    return n
            except Exception:
                continue
        return 0

    async def _read_last_assistant_text(self) -> str:
        sels = ['.ds-markdown', '.ds-markdown--block',
                '[data-message-author-role="assistant"]',
                '.model-response-text', 'message-content']
        best = ""
        for s in sels:
            try:
                loc = self._page.locator(s)
                n = await loc.count()
                if n == 0:
                    continue
                txt = (await loc.nth(n - 1).inner_text()).strip()
                if len(txt) > len(best):
                    best = txt
            except Exception:
                continue
        return best

'''

src = src[:start] + new_execute + src[end:]
nrt.write_text(src, encoding="utf-8", newline="\n")
print("  [OK] execute() replaced with DOM-only")

# syntax check
r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{nrt}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("[FAIL] syntax:", r.stderr); sys.exit(1)
print("  [OK] syntax valid")

# tests
def run(args, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print(r.stderr)
    return r.returncode

run([PY, "-m", "pytest", "-q",
     "tests/test_nonclaude_parsers.py",
     "tests/test_deepseek_think_response.py",
     "-o", "asyncio_mode=auto"], cwd=ROOT)

# commit
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(deepseek): DOM-only reply; abandon transport decoder on critical path"])
print(r.stdout.strip() or r.stderr.strip())

# live test
print("\n==> Live test")
import os as _os
env = _os.environ.copy(); env["PYTHONUTF8"]="1"
r = subprocess.run([PY, "-u", "-m", "scripts.chat_deepseek"], cwd=BE,
    input="hi who are you\nwhat can you do for me\n/exit\n",
    capture_output=True, text=True, encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)
