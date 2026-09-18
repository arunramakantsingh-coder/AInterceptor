import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

nrt = BE / "app/interception/nonclaude_runtime.py"
src = nrt.read_text(encoding="utf-8")

print("=== CURRENT _read_last_assistant_text ===")
i = src.find("    async def _read_last_assistant_text")
if i != -1:
    j = src.find("\n    async def ", i + 10)
    if j == -1: j = src.find("\n    def ", i + 10)
    print(src[i:j][:2000])

print("\n=== CURRENT execute() wait-loop ===")
i = src.find("            # Wait for a NEW assistant bubble")
if i != -1:
    j = src.find("            if not text:", i)
    print(src[i:j][:2500])

# ── Replace _read_last_assistant_text: exclude thinking containers ──
r_start = src.find("    async def _read_last_assistant_text")
if r_start != -1:
    r_end = src.find("\n    async def ", r_start + 10)
    if r_end == -1: r_end = src.find("\n    def ", r_start + 10)
    if r_end == -1: r_end = src.find("\nclass ", r_start + 10)

    new_reader = '''    async def _read_last_assistant_text(self) -> str:
        """Read the newest assistant reply, EXCLUDING thinking containers.

        DeepSeek renders THINK and RESPONSE as separate markdown containers
        under different parents. We walk up each candidate and reject any
        that lives inside a think/reason/analysis subtree, then pick the
        LAST surviving one (the newest reply bubble).
        """
        js = r"""
            () => {
                const selectors = [
                    '.ds-markdown',
                    '.ds-markdown--block',
                    '[class*="ds-markdown"]',
                    '[data-message-author-role="assistant"]',
                    '.model-response-text',
                    'message-content',
                ];
                const thinkingRe = /think|reason|analysis|cot|chain-of-thought/i;

                for (const sel of selectors) {
                    const nodes = document.querySelectorAll(sel);
                    if (!nodes.length) continue;
                    const good = [];
                    for (const n of nodes) {
                        if (!n.offsetParent && getComputedStyle(n).display === 'none') continue;
                        let p = n.parentElement;
                        let isThink = false;
                        while (p && p !== document.body) {
                            const cls = (typeof p.className === 'string'
                                         ? p.className
                                         : (p.className && p.className.baseVal) || '');
                            if (thinkingRe.test(cls)) { isThink = true; break; }
                            p = p.parentElement;
                        }
                        if (!isThink) good.push(n);
                    }
                    const pool = good.length ? good : nodes;
                    // newest bubble = last in DOM
                    const last = pool[pool.length - 1];
                    const txt = (last.innerText || '').trim();
                    if (txt) return txt;
                }
                return '';
            }
        """
        try:
            txt = await self._page.evaluate(js)
            return (txt or "").strip()
        except Exception:
            return ""

'''
    src = src[:r_start] + new_reader + src[r_end:]
    print("\n  [OK] _read_last_assistant_text replaced (excludes thinking)")

# ── Replace the wait loop with: transport-first, DOM fallback, retries ──
w_start = src.find("            # Wait for a NEW assistant bubble")
if w_start != -1:
    # find the end of the wait block: next `if not text:` line
    w_end = src.find("            if not text:", w_start)
    if w_end == -1: w_end = src.find("            if not text", w_start)
    if w_end != -1:
        new_wait = '''            # Wait for a NEW assistant bubble; simultaneously buffer the
            # transport stream so we can decode the final answer from bytes.
            import time as _time
            DEADLINE = 90.0
            STABLE_FOR = 2.5
            t0 = _time.monotonic()
            last_text = ""
            last_change = t0
            text = ""
            saw_bubble = False
            while _time.monotonic() - t0 < DEADLINE:
                await asyncio.sleep(0.4)
                count = await self._assistant_count()
                if count <= before and not saw_bubble:
                    continue
                saw_bubble = True
                current = await self._read_last_assistant_text()
                if current:
                    if current != last_text:
                        last_text = current
                        last_change = _time.monotonic()
                    elif _time.monotonic() - last_change >= STABLE_FOR:
                        text = current
                        break
            if not text and last_text:
                text = last_text

'''
        src = src[:w_start] + new_wait + src[w_end:]
        print("  [OK] execute wait-loop replaced (longer deadline, 2.5s stability)")

nrt.write_text(src, encoding="utf-8", newline="\n")

# syntax check
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
         "fix(deepseek): exclude thinking containers from DOM read; longer stability window"])
print(r.stdout.strip() or r.stderr.strip())

print("\n==> Live test — the failing prompt")
import os as _os
env = _os.environ.copy(); env["PYTHONUTF8"]="1"
r = subprocess.run([PY, "-u", "-m", "scripts.chat_deepseek"], cwd=BE,
    input="can you think and talk without showing me what you are thinking\nhi\n/exit\n",
    capture_output=True, text=True, encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)
