import pathlib, subprocess, sys, os, asyncio, textwrap

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# Script that: connects to DeepSeek browser on 9223, finds and clicks the
# DeepThink toggle (if currently on), then verifies it's off.
toggle = textwrap.dedent('''
    import asyncio, sys, pathlib
    sys.path.insert(0, r"''' + str(BE) + '''")
    from playwright.async_api import async_playwright

    TOGGLE_SELECTORS = [
        # DeepSeek's DeepThink toggle variants observed across UI versions
        "button:has-text('DeepThink')",
        "button:has-text('Deep Think')",
        "[role='button']:has-text('DeepThink')",
        "[role='button']:has-text('Deep Think')",
        "div[class*='think'] button",
        "button[aria-label*='think' i]",
        "button[aria-label*='DeepThink' i]",
        "button[aria-pressed]",
    ]

    async def main():
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
            ctx = browser.contexts[0]
            page = None
            for p in ctx.pages:
                if "deepseek.com" in (p.url or ""):
                    page = p
                    break
            if page is None:
                print("[FAIL] no deepseek page found"); return 1

            await page.bring_to_front()
            await asyncio.sleep(0.5)

            found = None
            for sel in TOGGLE_SELECTORS:
                try:
                    loc = page.locator(sel)
                    n = await loc.count()
                    if n > 0 and await loc.first.is_visible():
                        found = loc.first
                        print(f"[OK] toggle candidate: {sel}")
                        break
                except Exception:
                    continue

            if found is None:
                print("[WARN] no toggle found — toggle manually and rerun")
                return 0

            pressed = await found.get_attribute("aria-pressed")
            cls = await found.get_attribute("class") or ""
            text = (await found.inner_text()).strip()
            print(f"     aria-pressed={pressed} class={cls[:60]} text={text[:40]!r}")

            # If it looks ON, click it OFF
            looks_on = (pressed == "true") or ("active" in cls.lower()) or ("on" in cls.lower())
            if looks_on:
                await found.click()
                await asyncio.sleep(0.5)
                print("[OK] clicked toggle OFF")
            else:
                print("[OK] toggle already OFF (or unknown state — verify in browser)")
            return 0

    sys.exit(asyncio.run(main()))
''')

toggle_path = BE / "scripts" / "toggle_deepthink.py"
toggle_path.write_text(toggle, encoding="utf-8", newline="\n")
print(f"  [OK] wrote {toggle_path.relative_to(ROOT)}")

# run it
env = os.environ.copy(); env["PYTHONUTF8"] = "1"
print("\n==> Toggling DeepThink off")
r = subprocess.run([PY, "-u", str(toggle_path)], cwd=BE,
                   capture_output=True, text=True, encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)

# run the chat test
print("\n==> Live test (2 turns)")
r = subprocess.run([PY, "-u", "-m", "scripts.chat_deepseek"], cwd=BE,
    input="hi who are you\nwhat can you do\n/exit\n",
    capture_output=True, text=True, encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)

# commit
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","chore: add toggle_deepthink helper"])
print(r.stdout.strip() or r.stderr.strip())
