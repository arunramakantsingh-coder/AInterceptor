import pathlib, subprocess, sys, os

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

# ── 1. Fix DeepSeekStreamParser.__call__ ──
ds_path = BE / "app/interception/deepseek.py"
src = ds_path.read_text(encoding="utf-8")

old_call = '''    def __call__(self, cumulative_body: str) -> str:
        if not isinstance(cumulative_body, str):
            return self.current
        if cumulative_body.startswith(self._cumulative_body_seen):
            suffix = cumulative_body[len(self._cumulative_body_seen):]
        else:
            self.__init__()
            suffix = cumulative_body
        self._cumulative_body_seen = cumulative_body
        return self.feed(suffix)'''

new_call = '''    def __call__(self, cumulative_body: str) -> str:
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

if old_call in src:
    src = src.replace(old_call, new_call, 1)
    print("  [OK] __call__ rewritten to preserve state on divergence")
else:
    print("  [!] __call__ pattern not matched")

ds_path.write_text(src, encoding="utf-8", newline="\n")

# ── 2. Fix NonClaudeWebRuntime delta computation ──
nrt = BE / "app/interception/nonclaude_runtime.py"
nsrc = nrt.read_text(encoding="utf-8")

old_delta = '''                            current = self.parser(body.decode("utf-8", errors="replace"))
                            if current and current.startswith(emitted):
                                delta = current[len(emitted):]
                            elif current and len(current) > len(emitted):
                                delta = current
                            else:
                                delta = ""
                            if delta:
                                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_DELTA, sequence, delta=delta)
                                sequence += 1
                                emitted = current if current.startswith(emitted) else emitted + delta
                            continue'''

new_delta = '''                            current = self.parser(body.decode("utf-8", errors="replace"))
                            # Emit ONLY when the parser output strictly extends the emitted prefix.
                            # Never re-emit an earlier body: that's the class of bug that
                            # collapses "hi how are you" into "hi are you".
                            if current and current.startswith(emitted):
                                delta = current[len(emitted):]
                            else:
                                delta = ""
                            if delta:
                                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_DELTA, sequence, delta=delta)
                                sequence += 1
                                emitted = current
                            continue'''

if old_delta in nsrc:
    nsrc = nsrc.replace(old_delta, new_delta, 1)
    print("  [OK] runtime delta: prefix-only emission")
else:
    print("  [!] runtime delta pattern not matched")

old_final_delta = '''                            final = self.parser(body.decode("utf-8", errors="replace")).rstrip("\\n")
                            if final and final.startswith(emitted):
                                delta = final[len(emitted):]
                            elif final and final != emitted:
                                delta = final
                            else:
                                delta = ""'''

new_final_delta = '''                            final = self.parser(body.decode("utf-8", errors="replace")).rstrip("\\n")
                            if final and final.startswith(emitted):
                                delta = final[len(emitted):]
                            else:
                                delta = ""'''

if old_final_delta in nsrc:
    nsrc = nsrc.replace(old_final_delta, new_final_delta, 1)
    print("  [OK] runtime final delta: prefix-only emission")
else:
    print("  [!] runtime final delta pattern not matched")

nrt.write_text(nsrc, encoding="utf-8", newline="\n")

# ── 3. Tests ──
def run(args, cwd=ROOT):
    print(f"\n$ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print("STDERR:", r.stderr)
    return r.returncode

rc = run([PY, "-m", "pytest", "-q", "tests/test_nonclaude_parsers.py",
          "-o", "asyncio_mode=auto"], cwd=ROOT)
if rc != 0:
    print("RESULT: FAIL — tests broken, not committing"); sys.exit(1)

# ── 4. Live repro with UTF-8 ──
env = os.environ.copy()
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"
print("\n==> Live repro")
r = subprocess.run(
    [PY, "-X", "utf8", "-u", "-m", "scripts.repro_deepseek_capture", "hi how are you"],
    cwd=BE, capture_output=True, text=True, encoding="utf-8", env=env,
)
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)

# ── 5. Commit ──
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
git(["add", "-A"])
r = git(["commit", "-m", "fix(deepseek): prefix-only delta emission; parser preserves state on divergence"])
print("\n" + (r.stdout.strip() or r.stderr.strip()))

print("=" * 60)
print("RESULT: REVIEW output above")
print("=" * 60)
