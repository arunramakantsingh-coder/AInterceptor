"""aidaemon — resident session manager for AInterceptor.

Owns all four provider browsers, keeps them off-screen, exposes them
via HTTP on 127.0.0.1:7700. CLI clients connect to this daemon.
"""
from __future__ import annotations
import asyncio, ctypes, importlib, json, os, pathlib, socket, subprocess, sys, time, traceback

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
STATE_DIR = ROOT / ".ainterceptor"
STATE_DIR.mkdir(exist_ok=True)

PROVIDERS = {
    "claude":   {"port": 9222, "url": "https://claude.ai/",          "profile": "chrome-profile-claude"},
    "deepseek": {"port": 9223, "url": "https://chat.deepseek.com/",  "profile": "chrome-profile-deepseek"},
    "chatgpt":  {"port": 9224, "url": "https://chatgpt.com/",        "profile": "chrome-profile-chatgpt"},
    "gemini":   {"port": 9225, "url": "https://gemini.google.com/",  "profile": "chrome-profile-gemini"},
}
TITLE_MATCH = {
    "claude":   ["claude"],
    "deepseek": ["deepseek"],
    "chatgpt":  ["chatgpt"],
    "gemini":   ["gemini"],
}

# ── helpers ──
def find_chrome():
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if pathlib.Path(c).exists(): return c
    return None

def port_open(port):
    s = socket.socket(); s.settimeout(0.4)
    try: s.connect(("127.0.0.1", port)); return True
    except OSError: return False
    finally: s.close()

def launch_chrome(provider, off_screen=True):
    cfg = PROVIDERS[provider]
    chrome = find_chrome()
    if not chrome: raise RuntimeError("chrome.exe not found")
    profile = STATE_DIR / cfg["profile"]
    profile.mkdir(parents=True, exist_ok=True)
    pos = "-32000,-32000" if off_screen else "100,100"
    args = [chrome,
            f"--remote-debugging-port={cfg['port']}",
            f"--user-data-dir={profile}",
            "--no-first-run", "--no-default-browser-check",
            f"--window-position={pos}",
            "--window-size=1280,900",
            cfg["url"]]
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, creationflags=flags)
    for _ in range(30):
        time.sleep(0.5)
        if port_open(cfg["port"]): return
    raise RuntimeError(f"{provider} chrome did not bind port {cfg['port']}")

# ── window manipulation ──
_enum_windows = ctypes.windll.user32.EnumWindows
_get_text = ctypes.windll.user32.GetWindowTextW
_get_text_len = ctypes.windll.user32.GetWindowTextLengthW
_is_visible = ctypes.windll.user32.IsWindowVisible
_move = ctypes.windll.user32.MoveWindow
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

def _windows():
    out = []
    def cb(hwnd, lp):
        n = _get_text_len(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n+1)
            _get_text(hwnd, buf, n+1)
            if _is_visible(hwnd):
                out.append((hwnd, buf.value))
        return True
    _enum_windows(WNDENUMPROC(cb), 0)
    return out

def move_provider_window(provider, x, y):
    keys = TITLE_MATCH.get(provider, [provider])
    moved = 0
    for hwnd, title in _windows():
        tl = title.lower()
        if any(k in tl for k in keys):
            _move(hwnd, x, y, 1280, 900, True)
            moved += 1
    return moved

# ── runtime loading ──
sys.path.insert(0, str(BACKEND))
from app.interception.contracts import ProviderExecutionRequest

def load_runtime_class(provider):
    module = importlib.import_module(f"app.interception.{provider}")
    target = provider.replace("-","").lower()
    for name, obj in vars(module).items():
        if isinstance(obj, type) and obj.__module__ == module.__name__:
            if name.lower() == f"{target}runtime": return obj
    for name, obj in vars(module).items():
        if isinstance(obj, type) and obj.__module__ == module.__name__ and name.endswith("Runtime"):
            return obj
    raise RuntimeError(f"no Runtime for {provider}")

# ── state ──
LOCK = asyncio.Lock()
RUNTIMES = {}

async def ensure(provider):
    cfg = PROVIDERS[provider]
    async with LOCK:
        if not port_open(cfg["port"]):
            print(f"[daemon] launching {provider} chrome off-screen", flush=True)
            launch_chrome(provider, off_screen=True)
        if provider not in RUNTIMES:
            cls = load_runtime_class(provider)
            rt = cls()
            await rt.start()
            RUNTIMES[provider] = rt
            print(f"[daemon] {provider} attached", flush=True)
        return RUNTIMES[provider]

# ── API ──
app = FastAPI(title="aidaemon")

class ChatBody(BaseModel):
    prompt: str

@app.get("/")
def status():
    out = {"daemon": "running", "providers": {}}
    for name, cfg in PROVIDERS.items():
        out["providers"][name] = {
            "port": cfg["port"],
            "chrome_alive": port_open(cfg["port"]),
            "attached": name in RUNTIMES,
        }
    return out

@app.post("/ensure/{provider}")
async def api_ensure(provider: str):
    if provider not in PROVIDERS: raise HTTPException(404)
    await ensure(provider)
    return {"ok": True}

@app.post("/chat/{provider}")
async def api_chat(provider: str, body: ChatBody):
    if provider not in PROVIDERS: raise HTTPException(404)
    rt = await ensure(provider)
    req = ProviderExecutionRequest(
        provider=provider,
        request_id=os.urandom(8).hex(),
        messages=[{"role":"user","content":body.prompt}],
    )
    async def gen():
        try:
            async for ev in rt.execute(req):
                if ev.delta:
                    yield f"data: {json.dumps({'delta': ev.delta})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.post("/login/{provider}")
async def api_login(provider: str):
    if provider not in PROVIDERS: raise HTTPException(404)
    if not port_open(PROVIDERS[provider]["port"]):
        launch_chrome(provider, off_screen=False)
    else:
        move_provider_window(provider, 100, 100)
    return {"ok": True, "message": f"Log into {provider} in the window, then run: daemon hide {provider}"}

@app.post("/show/{provider}")
async def api_show(provider: str):
    n = move_provider_window(provider, 100, 100)
    return {"moved": n}

@app.post("/hide/{provider}")
async def api_hide(provider: str):
    n = move_provider_window(provider, -32000, -32000)
    return {"moved": n}

@app.post("/shutdown")
async def api_shutdown():
    async def later():
        await asyncio.sleep(0.3)
        os._exit(0)
    asyncio.create_task(later())
    return {"ok": True}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7700, log_level="warning")
