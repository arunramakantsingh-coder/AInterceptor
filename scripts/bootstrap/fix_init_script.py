import pathlib, subprocess, sys, ast

ROOT = pathlib.Path.cwd()
PB = ROOT / "backend" / "app" / "runtime" / "path_b.py"
BS = ROOT / "backend" / "app" / "runtime" / "browser_supervisor.py"

# ── 1. Replace the JS wrapper with one that also patches XHR + EventSource ──
pb_src = PB.read_text(encoding="utf-8")

new_js_block = '''

# Injected via add_init_script() BEFORE navigation so it lands before any
# site JS captures a reference to the original fetch/XHR/EventSource.
_WRAPPER_JS = r"""
(function() {
  if (window.__ainterceptor_patched) return;
  window.__ainterceptor_patched = true;

  const init_state = () => ({
    chunks: [], done: false, error: null, started: false, endpoint: null
  });
  window.__ainterceptor_stream = init_state();

  const isCompletion = (url) => {
    if (!url) return false;
    const u = String(url);
    if (/backend-api\\/f\\/conversation/.test(u) && !/prepare/.test(u)) return true;
    if (/api\\/v0\\/chat\\/completion/.test(u)) return true;
    if (/\\/completion/.test(u) && !/prepare/.test(u)) return true;
    if (/StreamGenerate/.test(u)) return true;
    return false;
  };

  const reset = (url) => {
    window.__ainterceptor_stream = init_state();
    window.__ainterceptor_stream.started = true;
    window.__ainterceptor_stream.endpoint = url;
  };
  const push = (s) => {
    if (s && s.length) window.__ainterceptor_stream.chunks.push(s);
  };
  const done = (err) => {
    if (err) window.__ainterceptor_stream.error = String(err);
    window.__ainterceptor_stream.done = true;
  };

  // ── fetch wrapper ──
  const origFetch = window.fetch;
  window.fetch = async function(...args) {
    let url = '';
    try {
      url = typeof args[0] === 'string' ? args[0]
           : (args[0] && args[0].url) || '';
    } catch (e) {}
    if (!isCompletion(url)) return origFetch.apply(this, args);

    reset(url);
    let resp;
    try {
      resp = await origFetch.apply(this, args);
    } catch (e) { done(e); throw e; }

    if (!resp.body || !resp.body.tee) { done(); return resp; }
    const [a, b] = resp.body.tee();
    (async () => {
      const reader = b.getReader();
      const dec = new TextDecoder();
      try {
        while (true) {
          const { done: d, value } = await reader.read();
          if (d) break;
          if (value) push(dec.decode(value, {stream: true}));
        }
      } catch (e) { done(e); return; }
      done();
    })();
    return new Response(a, {
      status: resp.status, statusText: resp.statusText, headers: resp.headers
    });
  };

  // ── XHR wrapper ──
  const OrigXHR = window.XMLHttpRequest;
  window.XMLHttpRequest = function() {
    const xhr = new OrigXHR();
    let url = '';
    const origOpen = xhr.open;
    xhr.open = function(method, u, ...rest) {
      url = u;
      if (isCompletion(u)) reset(u);
      return origOpen.call(this, method, u, ...rest);
    };
    let lastIndex = 0;
    xhr.addEventListener('progress', () => {
      if (!window.__ainterceptor_stream.started) return;
      try {
        const txt = xhr.responseText || '';
        if (txt.length > lastIndex) {
          push(txt.slice(lastIndex));
          lastIndex = txt.length;
        }
      } catch (e) {}
    });
    xhr.addEventListener('load', () => {
      if (!window.__ainterceptor_stream.started) return;
      try {
        const txt = xhr.responseText || '';
        if (txt.length > lastIndex) {
          push(txt.slice(lastIndex));
          lastIndex = txt.length;
        }
      } catch (e) {}
      done();
    });
    xhr.addEventListener('error', () => {
      if (window.__ainterceptor_stream.started) done('xhr error');
    });
    return xhr;
  };

  // ── EventSource wrapper ──
  const OrigES = window.EventSource;
  if (OrigES) {
    window.EventSource = function(url, opts) {
      const es = new OrigES(url, opts);
      if (isCompletion(url)) reset(url);
      const origAdd = es.addEventListener;
      es.addEventListener = function(type, listener, ...rest) {
        const wrapped = function(ev) {
          if (window.__ainterceptor_stream.started && ev && ev.data) {
            push('data: ' + ev.data + '\\n\\n');
          }
          return listener.apply(this, arguments);
        };
        return origAdd.call(this, type, wrapped, ...rest);
      };
      return es;
    };
  }
})();
"""

'''

# Remove old wrapper if present
old_start = pb_src.find("\n# Injected into the page.")
if old_start != -1:
    # find next occurrence of "class PathBError" and cut up to it
    nxt = pb_src.find("\nclass PathBError", old_start)
    if nxt != -1:
        pb_src = pb_src[:old_start] + "\n" + pb_src[nxt:]

# Also remove the very old _FETCH_WRAPPER_JS block
for marker in ["_FETCH_WRAPPER_JS"]:
    idx = pb_src.find(marker)
    if idx != -1:
        # find the end of that block (next class PathBError or next def)
        end = pb_src.find("\nclass PathBError", idx)
        if end == -1:
            end = pb_src.find("\ndef ", idx + 5)
        if end == -1:
            end = pb_src.find("\nclass ", idx + 5)
        if end != -1:
            pb_src = pb_src[:idx] + pb_src[end+1:]

# insert new wrapper before class PathBError
insert_at = pb_src.find("class PathBError")
if insert_at == -1:
    print("[FAIL] PathBError not found"); sys.exit(1)
pb_src = pb_src[:insert_at] + new_js_block.strip() + "\n\n" + pb_src[insert_at:]

PB.write_text(pb_src, encoding="utf-8", newline="\n")
print("  [OK] path_b.py: new wrapper (fetch + XHR + EventSource)")

# ── 2. Patch browser_supervisor to install wrapper as init script ──
bs_src = BS.read_text(encoding="utf-8")

old_open_tab = '''    async def _open_tab(self, provider: str) -> Tab:
        url = PROVIDER_URLS[provider]
        self.log(f"open tab: {provider} -> {url}")
        page = await self.state.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:
            self.log(f"goto failed for {provider}: {e}")
        return Tab(provider=provider, url=url, page=page, last_used=time.time())'''

new_open_tab = '''    async def _open_tab(self, provider: str) -> Tab:
        url = PROVIDER_URLS[provider]
        self.log(f"open tab: {provider} -> {url}")
        page = await self.state.context.new_page()
        # install the network-tap wrapper BEFORE navigation so it runs
        # before any site JS captures a reference to fetch/XHR/EventSource
        try:
            from app.runtime.path_b import _WRAPPER_JS
            await page.add_init_script(_WRAPPER_JS)
            self.log(f"init script installed for {provider}")
        except Exception as e:
            self.log(f"init script failed for {provider}: {e}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:
            self.log(f"goto failed for {provider}: {e}")
        return Tab(provider=provider, url=url, page=page, last_used=time.time())'''

if old_open_tab in bs_src:
    bs_src = bs_src.replace(old_open_tab, new_open_tab, 1)
    BS.write_text(bs_src, encoding="utf-8", newline="\n")
    print("  [OK] browser_supervisor: installs wrapper as init script")
else:
    print("  [!] _open_tab pattern not found")

# ── 3. Update stream_b to check window.__ainterceptor_patched ──
pb_src2 = PB.read_text(encoding="utf-8")
old_install = '''    # 1. Install the fetch wrapper (idempotent — checks a flag)
    try:
        await page.evaluate(_FETCH_WRAPPER_JS)
        _dbg(f"{provider}: fetch wrapper installed")
    except Exception as e:
        raise PathBError(f"{provider}: could not install fetch wrapper: {e}")

    # 2. Reset any previous stream buffer'''

new_install = '''    # 1. Ensure the wrapper is present (it should already be, via add_init_script)
    try:
        patched = await page.evaluate("() => !!window.__ainterceptor_patched")
        _dbg(f"{provider}: wrapper already installed: {patched}")
        if not patched:
            _dbg(f"{provider}: forcing wrapper install + reload")
            await page.add_init_script(_WRAPPER_JS)
            await page.reload(wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2)
    except Exception as e:
        _dbg(f"{provider}: wrapper check failed: {e}")

    # 2. Reset any previous stream buffer'''

if old_install in pb_src2:
    pb_src2 = pb_src2.replace(old_install, new_install, 1)
    PB.write_text(pb_src2, encoding="utf-8", newline="\n")
    print("  [OK] stream_b now checks/forces wrapper install")
else:
    print("  [!] install block pattern not found")

# ── syntax ──
for f in [PB, BS]:
    try: ast.parse(f.read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f.name}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

# ── tests ──
PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable
r = subprocess.run([str(PY), "-m", "pytest", "-q",
                    "tests/test_path_b_parser_adapters.py",
                    "-o", "asyncio_mode=auto"],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
print(r.stdout[-800:] if r.stdout else "")
if r.returncode != 0:
    print("[FAIL] tests failed"); sys.exit(1)

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(path_b): install wrapper via add_init_script; wrap fetch+XHR+EventSource"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("RESTART DAEMON")
print("  1. Daemon window: Ctrl+C")
print("  2. .\\run-windows.ps1")
print("  3. Look for '[browser] init script installed for chatgpt' (10 lines)")
print()
print("THEN in a new window, run the chatgpt curl.")
print()
print("Watch the daemon for:")
print("  [path_b] chatgpt: wrapper already installed: True")
print("  [path_b] chatgpt: wrapper saw request — draining")
print("  [path_b] chatgpt: DONE emitted=N chars")
print("=" * 60)
