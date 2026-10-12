import pathlib, sys, ast

pb = pathlib.Path("backend") / "app" / "runtime" / "path_b.py"
src = pb.read_text(encoding="utf-8")

# In the wrapper JS, add a "seen" list that records every URL
# (not just matching ones). Python can dump it for diagnosis.

# 1. init_state: add "seen"
src = src.replace(
    'const init_state = () => ({\n    chunks: [], done: false, error: null, started: false, endpoint: null\n  });',
    'const init_state = () => ({\n    chunks: [], done: false, error: null, started: false, endpoint: null, seen: []\n  });',
)
src = src.replace(
    "window.__ainterceptor_stream = init_state();",
    "window.__ainterceptor_stream = init_state();\n  window.__ainterceptor_seen = [];",
    1,
)

# 2. Record every fetch URL
src = src.replace(
    "if (!isCompletion(url)) return origFetch.apply(this, args);",
    "try { window.__ainterceptor_seen.push({t: 'fetch', url: String(url)}); } catch(e){}\n    if (!isCompletion(url)) return origFetch.apply(this, args);",
    1,
)

# 3. Record every XHR URL
src = src.replace(
    "      url = u;\n      if (isCompletion(u)) reset(u);",
    "      url = u;\n      try { window.__ainterceptor_seen.push({t: 'xhr', url: String(u)}); } catch(e){}\n      if (isCompletion(u)) reset(u);",
    1,
)

pb.write_text(src, encoding="utf-8", newline="\n")
print("  [OK] wrapper now records every fetch/xhr URL")

# 4. In _stream_b_locked: when no request observed, dump seen URLs
src = pb.read_text(encoding="utf-8")

old = '''    if not started:
        raise PathBError(f"{provider}: no request observed by fetch wrapper")'''

new = '''    if not started:
        # Dump every URL the wrapper saw so we know what ChatGPT actually calls
        try:
            seen = await page.evaluate("() => (window.__ainterceptor_seen || []).slice(-40)")
        except Exception as e:
            seen = [{"error": f"evaluate failed: {e}"}]
        _dbg(f"{provider}: NO REQUEST OBSERVED. Last URLs seen by wrapper:")
        for entry in seen:
            if isinstance(entry, dict):
                _dbg(f"  [{entry.get('t')}] {entry.get('url')}")
        raise PathBError(f"{provider}: no request observed by fetch wrapper")'''

if old in src:
    src = src.replace(old, new, 1)
    print("  [OK] stream_b dumps seen URLs on failure")
else:
    print("  [!] failure branch not matched")

pb.write_text(src, encoding="utf-8", newline="\n")

try: ast.parse(pb.read_text(encoding="utf-8"))
except SyntaxError as e:
    print(f"[FAIL] {e}"); sys.exit(1)
print("  [OK] syntax valid")

import subprocess
def git(a):
    return subprocess.run(["git"]+a, cwd=pathlib.Path("."), capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","debug(path_b): record every fetch/xhr URL wrapper sees"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("NEXT: restart daemon, run chatgpt curl, paste the [path_b] seen-URL lines")
