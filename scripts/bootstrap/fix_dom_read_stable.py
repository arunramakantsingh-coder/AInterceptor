import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

nrt = BE / "app/interception/nonclaude_runtime.py"
src = nrt.read_text(encoding="utf-8")

# ── 1. Replace _read_last_assistant_text: LAST bubble, not longest ──
start = src.find("    async def _read_last_assistant_text")
end   = src.find("\n    async def ", start + 10)
if end == -1:
    end = src.find("\n    def ", start + 10)
if end == -1:
    end = src.find("\nclass ", start + 10)
if start == -1 or end == -1:
    print("[FAIL] cannot find _read_last_assistant_text bounds"); sys.exit(1)

new_reader = '''    async def _read_last_assistant_text(self) -> str:
        """Return the text of the LAST assistant bubble.

        Uses the newest matching element, not the longest. In multi-turn
        chat the previous reply may be longer than the current one; picking
        the longest would return stale text.
        """
        selectors = (
            ".ds-markdown",
            ".ds-markdown--block",
            "[data-message-author-role='assistant']",
            ".model-response-text",
            "message-content",
        )
        for s in selectors:
            try:
                loc = self._page.locator(s)
                n = await loc.count()
                if n == 0:
                    continue
                txt = (await loc.nth(n - 1).inner_text()).strip()
                if txt:
                    return txt
            except Exception:
                continue
        return ""
'''

src = src[:start] + new_reader + src[end:]
print("  [OK] _read_last_assistant_text: last bubble, not longest")

# ── 2. Replace the wait loop in execute with a time-based stability check ──
old_wait = '''            # Wait for a NEW assistant bubble
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
                    text = current'''

new_wait = '''            # Wait for a NEW assistant bubble, then for its text to stop
            # changing for STABLE_FOR seconds (not just N reads).
            import time as _time
            DEADLINE = 120.0
            STABLE_FOR = 2.0
            t0 = _time.monotonic()
            last_text = ""
            last_change = t0
            text = ""
            saw_new_bubble = False
            while _time.monotonic() - t0 < DEADLINE:
                await asyncio.sleep(0.35)
                count = await self._assistant_count()
                if count <= before:
                    continue
                saw_new_bubble = True
                current = await self._read_last_assistant_text()
                if not current:
                    continue
                if current != last_text:
                    last_text = current
                    last_change = _time.monotonic()
                elif _time.monotonic() - last_change >= STABLE_FOR:
                    text = current
                    break
            if not text and last_text:
                text = last_text  # best effort if deadline hit mid-change'''

if old_wait in src:
    src = src.replace(old_wait, new_wait, 1)
    print("  [OK] execute wait-loop: time-based stability (2s)")
else:
    print("  [!] wait-loop pattern not matched")

# ── 3. Also — a more reliable bubble counter using combined selectors ──
old_count_start = src.find("    async def _assistant_count")
if old_count_start != -1:
    old_count_end = src.find("\n    async def ", old_count_start + 10)
    if old_count_end == -1:
        old_count_end = src.find("\n    def ", old_count_start + 10)
    new_counter = '''    async def _assistant_count(self) -> int:
        """Count assistant bubbles. Uses the widest single selector that
        matches DeepSeek's current UI; falls back to alternates."""
        for s in (".ds-markdown",
                  "[data-message-author-role='assistant']",
                  ".model-response-text",
                  "message-content"):
            try:
                n = await self._page.locator(s).count()
                if n > 0:
                    return n
            except Exception:
                continue
        return 0
'''
    src = src[:old_count_start] + new_counter + src[old_count_end:]
    print("  [OK] _assistant_count refreshed")

nrt.write_text(src, encoding="utf-8", newline="\n")

# ── 4. Syntax + tests ──
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

# ── 5. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(deepseek): read LAST assistant bubble; time-based stability wait"])
print(r.stdout.strip() or r.stderr.strip())

# ── 6. Live test with mixed short/long replies ──
print("\n==> Live test — short and long replies")
import os as _os
env = _os.environ.copy(); env["PYTHONUTF8"]="1"
r = subprocess.run([PY, "-u", "-m", "scripts.chat_deepseek"], cwd=BE,
    input="where r u\ngreat this time its working very well\nhi\n/exit\n",
    capture_output=True, text=True, encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)
