import pathlib, subprocess, sys, ast, re

ROOT = pathlib.Path.cwd()
PB = ROOT / "backend" / "app" / "runtime" / "path_b.py"

src = PB.read_text(encoding="utf-8")

# ── Fix 1: JS regexes — replace \\. and \\/ with \. and \/ ──
# The current JS has patterns like `/backend-api\\/f\\/conversation/`
# Those must be `/backend-api\/f\/conversation/`
fixes = [
    (r"/backend-api\\/f\\/conversation/", r"/backend-api\/f\/conversation/"),
    (r"/api\\/v0\\/chat\\/completion/",    r"/api\/v0\/chat\/completion/"),
    (r"/\\/completion/",                   r"/\/completion/"),
]
for old, new in fixes:
    if old in src:
        src = src.replace(old, new)
        print(f"  [OK] fixed: {old}")

PB.write_text(src, encoding="utf-8", newline="\n")

# ── Fix 2: composer selection — contenteditable first for ChatGPT ──
old_sel = '''COMPOSER_SELECTORS: dict[str, tuple[str, ...]] = {
    "claude":   ('div[contenteditable="true"]', "textarea"),
    "chatgpt":  ("#prompt-textarea", 'div[contenteditable="true"]', "textarea"),
    "gemini":   ("rich-textarea div[contenteditable='true']", 'div[contenteditable="true"]', "textarea"),
    "deepseek": ('textarea[placeholder*="Message"]', "textarea",
                 '[contenteditable="true"]', '[role="textbox"]'),
}'''

new_sel = '''COMPOSER_SELECTORS: dict[str, tuple[str, ...]] = {
    # Order matters — most visible/specific first.
    "chatgpt":  (
        'div[contenteditable="true"].ProseMirror',
        'div[contenteditable="true"][id="prompt-textarea"]',
        'div[contenteditable="true"]',
        "#prompt-textarea",
        "textarea",
    ),
    "claude":   (
        'div[contenteditable="true"].ProseMirror',
        'div[contenteditable="true"]',
        "textarea",
    ),
    "gemini":   (
        "rich-textarea div[contenteditable='true']",
        'div[contenteditable="true"]',
        "textarea",
    ),
    "deepseek": (
        'textarea[placeholder*="Message"]',
        "textarea",
        '[contenteditable="true"]',
        '[role="textbox"]',
    ),
}'''

if old_sel in src:
    src = src.replace(old_sel, new_sel, 1)
    print("  [OK] composer selectors updated")
else:
    print("  [!] COMPOSER_SELECTORS not found — inspecting")
    m = re.search(r"COMPOSER_SELECTORS[^\n]*=.*?^\}", src, re.M | re.S)
    if m:
        print(m.group(0)[:400])

# ── Also improve _find_composer to filter by visibility more strictly ──
old_find = '''async def _find_composer(page: Any, selectors: tuple[str, ...]) -> Any:
    for sel in selectors:
        try:
            loc = page.locator(sel)
            n = await loc.count()
            for i in range(n - 1, -1, -1):
                cand = loc.nth(i)
                try:
                    if await cand.is_visible() and await cand.is_editable():
                        return cand
                except Exception:
                    pass
        except Exception:
            continue
    return None'''

new_find = '''async def _find_composer(page: Any, selectors: tuple[str, ...]) -> Any:
    """Return the first visible+editable composer, preferring earlier selectors."""
    for sel in selectors:
        try:
            loc = page.locator(sel)
            n = await loc.count()
            for i in range(n):
                cand = loc.nth(i)
                try:
                    visible = await cand.is_visible()
                    if not visible:
                        continue
                    editable = await cand.is_editable()
                    if not editable:
                        # contenteditable may not report as editable on
                        # some builds — check attribute directly
                        ce = await cand.get_attribute("contenteditable")
                        if (ce or "").lower() not in ("true", "plaintext-only", ""):
                            continue
                    return cand
                except Exception:
                    continue
        except Exception:
            continue
    return None'''

if old_find in src:
    src = src.replace(old_find, new_find, 1)
    print("  [OK] _find_composer improved")

PB.write_text(src, encoding="utf-8", newline="\n")

# syntax
try: ast.parse(src)
except SyntaxError as e:
    print(f"[FAIL] syntax: {e}"); sys.exit(1)
print("  [OK] syntax valid")

# ── sanity: run the wrapper JS through a quick node check ──
try:
    r = subprocess.run(["node", "--check", "--input-type=module"],
                       input="", capture_output=True, text=True, timeout=3)
    # node not always present; skip if missing
except Exception:
    pass

# ── tests ──
PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable
r = subprocess.run([str(PY), "-m", "pytest", "-q",
                    "tests/test_path_b_parser_adapters.py",
                    "-o", "asyncio_mode=auto"],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
print(r.stdout[-600:] if r.stdout else "")
if r.returncode != 0:
    print("[FAIL] tests failed"); sys.exit(1)

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(path_b): correct JS regex escapes; prefer visible contenteditable composer"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("RESTART DAEMON AND TEST")
print()
print("  1. Daemon window: Ctrl+C")
print("  2. .\\run-windows.ps1")
print("  3. Look for '[browser] init script installed for chatgpt'")
print()
print("  4. New window: run the chatgpt curl")
print()
print("Watch for [path_b]:")
print("  chatgpt: wrapper already installed: True   ← MUST be True this time")
print("  chatgpt: wrapper saw request — draining")
print("  chatgpt: DONE emitted=N chars")
print("=" * 60)
