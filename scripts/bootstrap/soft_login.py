import pathlib, subprocess, sys, ast

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
rt   = BE / "app/interception/nonclaude_runtime.py"
src  = rt.read_text(encoding="utf-8")

# ── 1. start() should not fail on login page ──
old = '''    async def start(self) -> None:
        """Attach and go. Does NOT require login — providers like ChatGPT
        work without an account. If the page shows a login wall when we
        submit the prompt, the reply itself will make that clear."""
        if self._started:
            return
        await self._ensure_page()
        self._started = True'''
new = '''    async def start(self) -> None:
        """Attach and go. Login is checked lazily — we do NOT block here
        because several providers (ChatGPT, Perplexity, DuckDuckGo) allow
        anonymous chat. If a login wall is present at prompt time, execute()
        reports it as SESSION_EXPIRED so the CLI can prompt the user."""
        if self._started:
            return
        await self._ensure_page()
        self._started = True

    def is_login_page(self) -> bool:
        return self._is_login_page()'''
if old in src:
    src = src.replace(old, new, 1)
    print("  [OK] start(): soft — no login block, exposes is_login_page()")

# ── 2. In execute(), detect login wall on submit ──
# After prompt submission, if the page navigates to login markers, emit SESSION_EXPIRED
old_wait = '''            yield StreamEvent(self.provider, request.request_id,
                              EventType.STREAM_STARTED, seq,
                              metadata={"transport": "dom"})
            seq += 1

            # Wait for a NEW assistant bubble'''
new_wait = '''            yield StreamEvent(self.provider, request.request_id,
                              EventType.STREAM_STARTED, seq,
                              metadata={"transport": "dom"})
            seq += 1

            # Lazy login detection: after submit, the page may have
            # navigated to a login wall. Give it 2s to settle, then check.
            await asyncio.sleep(2.0)
            if self._is_login_page():
                yield StreamEvent(self.provider, request.request_id,
                                  EventType.SESSION_EXPIRED, seq,
                                  metadata={"reason": "login_required",
                                            "hint": f"run:  login {self.provider}"})
                seq += 1
                yield StreamEvent(self.provider, request.request_id,
                                  EventType.SESSION_RECOVERY_REQUIRED, seq,
                                  metadata={"reason": "login_required"})
                return

            # Wait for a NEW assistant bubble'''
if old_wait in src:
    src = src.replace(old_wait, new_wait, 1)
    print("  [OK] execute(): detects login wall on submit")
else:
    print("  [!] execute() submit block not matched")

rt.write_text(src, encoding="utf-8", newline="\n")
ast.parse(src)
print("  [OK] syntax valid")

# ── 3. CLI: handle SESSION_EXPIRED by telling user to login ──
BE2 = BE / "scripts" / "chat_any.py"
csrc = BE2.read_text(encoding="utf-8")

old_loop = '''                got = False
                try:
                    async for ev in rt.execute(req):
                        if ev.delta:
                            print(ev.delta, end="", flush=True)
                            got = True
                except Exception as e:
                    print(f"\\n[FAIL] {e}")
                print()
                if not got:
                    print("(no reply — if a login wall appeared, run:  login " + provider + ")")'''

new_loop = '''                got = False
                need_login = False
                try:
                    async for ev in rt.execute(req):
                        if ev.delta:
                            print(ev.delta, end="", flush=True)
                            got = True
                        et = getattr(ev.event_type, "value", str(ev.event_type))
                        if et in ("SESSION_EXPIRED", "SESSION_RECOVERY_REQUIRED"):
                            need_login = True
                except Exception as e:
                    print(f"\\n[FAIL] {e}")
                print()
                if need_login:
                    print(f"This provider needs a login.")
                    print(f"Run:  login {provider}")
                    print(f"Then: hide")
                    print(f"Then: {provider}")
                elif not got:
                    print("(no reply received)")'''

if old_loop in csrc:
    csrc = csrc.replace(old_loop, new_loop, 1)
    BE2.write_text(csrc, encoding="utf-8", newline="\n")
    ast.parse(csrc)
    print("  [OK] chat_any.py: prints login hint on SESSION_EXPIRED")
else:
    print("  [!] CLI loop pattern not matched")

# ── 4. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(runtime): soft login detection — chat works anonymously; hint to login only when wall appears"])
print((r.stdout.strip() or r.stderr.strip())[:400])

print()
print("=" * 60)
print("Behavior now:")
print("  deepseek          -> chats anonymously if allowed")
print("                       if a login wall appears, tells you: login deepseek")
print("  login deepseek    -> slides Chrome on-screen")
print("  hide              -> pushes it back off-screen")
print("=" * 60)
