import pathlib, subprocess, sys, re

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

nrt = BE / "app/interception/nonclaude_runtime.py"
src = nrt.read_text(encoding="utf-8")

# Find the whole execute() method and replace its body
start = src.find("    async def execute(self, request: ProviderExecutionRequest)")
end   = src.find("\n    async def ", start + 10)
if start == -1 or end == -1:
    print("[FAIL] cannot find execute bounds"); sys.exit(1)

new_execute = '''    async def execute(self, request: ProviderExecutionRequest):
        """Submit prompt, wait until the DOM shows a NEW assistant reply,
        return it. Relies on text-change detection, NOT on bubble counting
        (providers reuse DOM slots, so counts are unreliable).
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
            import time as _time
            seq = 0
            yield StreamEvent(self.provider, request.request_id,
                              EventType.REQUEST_INTERCEPTED, seq,
                              metadata={"transport": "dom"})
            seq += 1

            # Snapshot BEFORE sending
            before_text = await self._read_last_assistant_text()

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

            # Poll for a NEW reply. A reply is "new" if the last-assistant
            # text differs from before_text AND is stable for STABLE_FOR.
            DEADLINE = 90.0
            STABLE_FOR = 2.5
            t0 = _time.monotonic()
            last_change = t0
            last_seen = ""
            text = ""
            while _time.monotonic() - t0 < DEADLINE:
                await asyncio.sleep(0.4)
                current = await self._read_last_assistant_text()
                if not current:
                    continue
                # Reject the pre-send snapshot
                if current == before_text:
                    continue
                if current != last_seen:
                    last_seen = current
                    last_change = _time.monotonic()
                    continue
                # Stable?
                if _time.monotonic() - last_change >= STABLE_FOR:
                    text = current
                    break

            if not text:
                text = last_seen or ""

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

'''

src = src[:start] + new_execute + src[end:]
nrt.write_text(src, encoding="utf-8", newline="\n")
print("  [OK] execute() rewritten: text-change detection only")

# syntax
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
         "fix(deepseek): drop bubble-count reliance; use text snapshot + stability"])
print(r.stdout.strip() or r.stderr.strip())

print()
print("Test now:  deepseek")
