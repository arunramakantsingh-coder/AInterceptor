import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

nrt = BE / "app/interception/nonclaude_runtime.py"
src = nrt.read_text(encoding="utf-8")

start = src.find("    async def execute(self, request: ProviderExecutionRequest)")
end   = src.find("\n    async def ", start + 10)
if start == -1 or end == -1:
    print("[FAIL] cannot find execute bounds"); sys.exit(1)

new_execute = '''    async def execute(self, request: ProviderExecutionRequest):
        """Submit prompt; stream DOM text growth as STREAM_DELTA events.

        Polls the last assistant bubble every ~250ms. Whenever the text
        strictly extends what we already emitted, we emit the new suffix.
        Finalizes when the text stops changing for STABLE_FOR seconds.
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
                              metadata={"transport": "dom-stream"})
            seq += 1

            before_text = await self._read_last_assistant_text()

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
                              metadata={"transport": "dom-stream"})
            seq += 1

            DEADLINE = 120.0
            STABLE_FOR = 2.0
            POLL = 0.25
            t0 = _time.monotonic()
            last_change = t0
            emitted = ""              # what we've already sent
            seen_full = ""            # latest full text from DOM
            started = False           # have we seen the new bubble yet?

            while _time.monotonic() - t0 < DEADLINE:
                await asyncio.sleep(POLL)
                current = await self._read_last_assistant_text()
                if not current:
                    continue
                if not started:
                    # skip until we see a change from the pre-send snapshot
                    if current == before_text:
                        continue
                    started = True

                # If DOM produced a longer text extending what we emitted,
                # stream the delta.
                if current.startswith(emitted) and len(current) > len(emitted):
                    delta = current[len(emitted):]
                    emitted = current
                    seen_full = current
                    last_change = _time.monotonic()
                    yield StreamEvent(self.provider, request.request_id,
                                      EventType.STREAM_DELTA, seq, delta=delta)
                    seq += 1
                    continue

                # Occasionally the provider rewrites the tail (markdown
                # re-render). Handle by treating the common prefix as stable
                # and only emitting a corrected suffix if it grew.
                if current != seen_full:
                    seen_full = current
                    last_change = _time.monotonic()
                    # If current is longer but not a strict prefix-extension,
                    # emit the tail beyond the longest common prefix.
                    if len(current) > len(emitted):
                        cp = 0
                        for a, b in zip(current, emitted):
                            if a != b: break
                            cp += 1
                        if cp >= max(0, len(emitted) - 4):
                            delta = current[cp:]
                            emitted = current
                            yield StreamEvent(self.provider, request.request_id,
                                              EventType.STREAM_DELTA, seq, delta=delta)
                            seq += 1
                            continue

                # Finalize when stable
                if started and (_time.monotonic() - last_change) >= STABLE_FOR:
                    break

            # Final emit: any tail that hasn't been sent yet
            if seen_full and seen_full.startswith(emitted) and len(seen_full) > len(emitted):
                delta = seen_full[len(emitted):]
                yield StreamEvent(self.provider, request.request_id,
                                  EventType.STREAM_DELTA, seq, delta=delta)
                seq += 1

            if not emitted and not seen_full:
                yield StreamEvent(self.provider, request.request_id,
                                  EventType.STREAM_FAILED, seq,
                                  metadata={"reason": "no assistant reply observed"})
                return

            yield StreamEvent(self.provider, request.request_id,
                              EventType.STREAM_COMPLETED, seq,
                              finish_reason="stop")
            return

'''

src = src[:start] + new_execute + src[end:]
nrt.write_text(src, encoding="utf-8", newline="\n")
print("  [OK] execute() rewritten for live streaming")

# syntax
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

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "feat(deepseek): live DOM streaming — deltas emitted as text grows"])
print(r.stdout.strip() or r.stderr.strip())

print()
print("Test streaming:   deepseek")
