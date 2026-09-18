import pathlib, subprocess

ROOT = pathlib.Path.cwd()
p = ROOT / "agent" / "airouter_agent" / "login.py"
src = p.read_text(encoding="utf-8")

old = '''    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(LOGIN_URLS[provider])
        try:
            await _wait_until_logged_in(page, provider)
        except TimeoutError as e:
            print(f"error: {e}")
            await browser.close()
            return 1

        state = await ctx.storage_state()
        await browser.close()'''

new = '''    # Use the user's real Chrome (not Playwright's bundled Chromium) so that
    # Google OAuth trusts the browser. Also keep a persistent profile so
    # Google remembers the device after the first successful login.
    profile_dir = pathlib.Path.home() / ".airouter" / "chrome-profile" / provider
    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",                 # real Chrome, not Chromium
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(LOGIN_URLS[provider])
        try:
            await _wait_until_logged_in(page, provider)
        except TimeoutError as e:
            print(f"error: {e}")
            await ctx.close()
            return 1

        state = await ctx.storage_state()
        await ctx.close()'''

if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] login.py: real Chrome + persistent profile")
else:
    print("  [!] pattern not matched — checking")
    if "channel=" in src:
        print("      already uses channel")
    else:
        print("      inspect manually")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(agent): use real Chrome + persistent profile so Google OAuth works"])
print((r.stdout.strip() or r.stderr.strip())[:300])
