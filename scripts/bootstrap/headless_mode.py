import pathlib, subprocess, sys, json, os, asyncio, textwrap

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ── 1. Harvest storage_state from running CDP browsers ──
harvest = BE / "scripts" / "harvest_storage.py"
harvest.write_text(textwrap.dedent('''
    """One-time: pull cookies + storage from the running CDP Chromes so we
    can run future chats in a hidden headless browser.
    """
    import asyncio, json, pathlib, sys
    from playwright.async_api import async_playwright

    TARGETS = {
        "deepseek": "http://127.0.0.1:9223",
        "claude":   "http://127.0.0.1:9222",
        "chatgpt":  "http://127.0.0.1:9224",
        "gemini":   "http://127.0.0.1:9225",
    }

    async def harvest(name, cdp_url):
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.connect_over_cdp(cdp_url)
                if not browser.contexts:
                    print(f"[{name}] no context on {cdp_url}"); return False
                ctx = browser.contexts[0]
                state = await ctx.storage_state()
                out = pathlib.Path(".ainterceptor") / name / "storage_state.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(state, indent=2), encoding="utf-8")
                ck = len(state.get("cookies", []))
                print(f"[{name}] saved {ck} cookies -> {out}")
                return True
        except Exception as e:
            print(f"[{name}] FAIL: {e}")
            return False

    async def main():
        ok = 0
        for name, url in TARGETS.items():
            if await harvest(name, url):
                ok += 1
        print(f"harvested {ok}/{len(TARGETS)}")
        return 0

    sys.exit(asyncio.run(main()))
'''), encoding="utf-8", newline="\n")
print(f"  [OK] wrote {harvest.relative_to(ROOT)}")

# ── 2. Patch runtime: prefer headless if storage_state exists ──
nrt = BE / "app/interception/nonclaude_runtime.py"
src = nrt.read_text(encoding="utf-8")

# Insert headless decision right after the env_val branch
old_resolve = '''        env_key = f"AINTERCEPTOR_{self.provider.upper()}_CDP_URL"
        env_val = os.environ.get(env_key)
        if env_val == "":
            self.cdp_url = None
        elif env_val:
            self.cdp_url = env_val
        else:
            self.cdp_url = provider_registry.cdp_url(self.provider)'''

new_resolve = '''        env_key = f"AINTERCEPTOR_{self.provider.upper()}_CDP_URL"
        env_val = os.environ.get(env_key)

        # Headless preference: if a saved storage_state exists and the user
        # has not forced a CDP URL, run our own hidden Chromium.
        headless_pref = os.environ.get("AINTERCEPTOR_HEADLESS", "1") not in {"0","false","no"}
        sp = pathlib.Path(self.session_path) if self.session_path else None
        has_state = bool(sp and sp.exists() and sp.stat().st_size > 50)

        if headless_pref and has_state and env_val is None:
            self.cdp_url = None  # use launch path below
        elif env_val == "":
            self.cdp_url = None
        elif env_val:
            self.cdp_url = env_val
        else:
            self.cdp_url = provider_registry.cdp_url(self.provider)'''

if old_resolve in src:
    src = src.replace(old_resolve, new_resolve, 1)
    print("  [OK] runtime: headless preference honored")
else:
    print("  [!] CDP resolve block not matched")

nrt.write_text(src, encoding="utf-8", newline="\n")

# ── 3. Syntax ──
r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{nrt}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("[FAIL] syntax:", r.stderr); sys.exit(1)
print("  [OK] syntax valid")

# ── 4. Harvest cookies from running Chromes ──
env = os.environ.copy(); env["PYTHONUTF8"]="1"
print("\n==> Harvesting cookies from running CDP Chromes")
r = subprocess.run([PY, "-u", str(harvest)], cwd=BE,
                   capture_output=True, text=True, encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)

# ── 5. Live test — should launch HIDDEN browser, no window pops ──
print("\n==> Live headless test (no browser window should appear)")
env["AINTERCEPTOR_HEADLESS"] = "1"
r = subprocess.run([PY, "-u", "-m", "scripts.chat_deepseek"], cwd=BE,
    input="hi\nwhat can you do\n/exit\n",
    capture_output=True, text=True, encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)

# ── 6. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "feat(runtime): headless mode via harvested storage_state; no visible browser"])
print(r.stdout.strip() or r.stderr.strip())
