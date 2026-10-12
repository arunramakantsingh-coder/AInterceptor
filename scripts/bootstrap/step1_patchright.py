import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
VENV = ROOT / ".venv-windows"
PY = VENV / "Scripts" / "python.exe"

if not PY.exists():
    print(f"[FAIL] {PY} not found. Run .\\run-windows.ps1 once first.")
    raise SystemExit(1)

def run(args, check=True, timeout=600):
    print(f"  $ {' '.join(str(a) for a in args)}")
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", timeout=timeout)
    if r.stdout.strip(): print("   ", r.stdout.strip()[-1500:])
    if r.stderr.strip(): print("   ", r.stderr.strip()[-1500:])
    if check and r.returncode != 0:
        print(f"[FAIL] exit {r.returncode}")
        sys.exit(1)
    return r

# ── 1. Install patchright ──
print("==> installing patchright into .venv-windows")
run([str(PY), "-m", "pip", "install", "-q", "patchright"], timeout=300)

# ── 2. Install patchright's chromium ──
print("\n==> installing patchright chromium")
run([str(PY), "-m", "patchright", "install", "chromium"], timeout=600)

# ── 3. Verify both imports work ──
print("\n==> verifying both patchright and playwright import")
probe = (
    "import patchright; print('patchright:', patchright.__version__ if hasattr(patchright,'__version__') else 'ok')\n"
    "import playwright; print('playwright: ok')\n"
    "from patchright.async_api import async_playwright as pw_patchright\n"
    "from playwright.async_api import async_playwright as pw_playwright\n"
    "print('both async_playwright imports work')\n"
)
run([str(PY), "-c", probe])

# ── 4. Sanity check: launch patchright chromium headless ──
print("\n==> launch test (patchright headless)")
test = '''
import asyncio
from patchright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage"
        ])
        page = await browser.new_page()
        await page.set_content("<h1>patchright works</h1>")
        text = await page.inner_text("h1")
        print(f"page content: {text}")
        await browser.close()

asyncio.run(main())
'''
test_path = ROOT / "scripts" / "bootstrap" / "_patchright_test.py"
test_path.write_text(test, encoding="utf-8", newline="\n")
run([str(PY), str(test_path)])
test_path.unlink()

# ── 5. Report versions ──
print("\n==> versions")
run([str(PY), "-m", "pip", "show", "patchright", "playwright"],
    check=False)

print()
print("=" * 60)
print("STEP 1 COMPLETE")
print("  patchright installed in .venv-windows")
print("  playwright still present (unchanged)")
print("  both importable side by side")
print("  headless chromium launches successfully")
print("=" * 60)
