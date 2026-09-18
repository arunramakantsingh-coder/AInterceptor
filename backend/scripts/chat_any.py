"""Chat CLI — prefers aidaemon, falls back to local runtime."""
import asyncio, json, os, sys, uuid, pathlib, urllib.request, urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

DAEMON = "http://127.0.0.1:7700"

def daemon_alive():
    try:
        with urllib.request.urlopen(f"{DAEMON}/", timeout=0.8) as r:
            return r.status == 200
    except Exception:
        return False

def daemon_call(method, path):
    req = urllib.request.Request(f"{DAEMON}{path}", method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

async def chat_via_daemon(provider):
    print(f"Connected to {provider} (daemon). /exit or Ctrl+C to leave.\n")
    prefix = f"{provider}> "
    while True:
        try:
            line = input(prefix)
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not line.strip(): continue
        if line.strip() in {"/exit","/back","exit","quit"}: break
        body = json.dumps({"prompt": line}).encode()
        req = urllib.request.Request(
            f"{DAEMON}/chat/{provider}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        print()
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                buf = b""
                for chunk in resp:
                    buf += chunk
                    while b"\n\n" in buf:
                        ev, buf = buf.split(b"\n\n", 1)
                        for ln in ev.split(b"\n"):
                            if not ln.startswith(b"data: "): continue
                            payload = ln[6:].decode("utf-8","replace")
                            if payload == "[DONE]": break
                            try:
                                j = json.loads(payload)
                                if "delta" in j:
                                    print(j["delta"], end="", flush=True)
                                elif "error" in j:
                                    print(f"\n[ERROR] {j['error']}")
                            except Exception:
                                pass
        except Exception as e:
            print(f"[FAIL] {e}")
        print()
    return 0

# ── local fallback (identical to previous behavior) ──
async def chat_local(provider):
    import importlib, inspect
    RAW = pathlib.Path("..") / ".evidence" / "raw"
    RAW.mkdir(parents=True, exist_ok=True)
    os.environ["AINTERCEPTOR_RAW_CAPTURE_DIR"] = str(RAW)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from app.interception.contracts import ProviderExecutionRequest
    module = importlib.import_module(f"app.interception.{provider}")
    target = provider.replace("-","").lower()
    cls = None
    for name, obj in vars(module).items():
        if isinstance(obj, type) and obj.__module__ == module.__name__:
            if name.lower() == f"{target}runtime": cls = obj; break
    if cls is None:
        for name, obj in vars(module).items():
            if isinstance(obj, type) and obj.__module__ == module.__name__ and name.endswith("Runtime"):
                cls = obj; break
    if cls is None: print("[FAIL] no runtime"); return 3
    rt = cls()
    await rt.start()
    print(f"Connected to {provider} (local). /exit or Ctrl+C to leave.\n")
    while True:
        try:
            line = input(f"{provider}> ")
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not line.strip(): continue
        if line.strip() in {"/exit","/back","exit","quit"}: break
        req = ProviderExecutionRequest(provider=provider,
            request_id=str(uuid.uuid4()),
            messages=[{"role":"user","content":line}])
        print()
        async for ev in rt.execute(req):
            if ev.delta: print(ev.delta, end="", flush=True)
        print()
    await rt.close()
    return 0

async def main():
    args = sys.argv[1:]
    if not args:
        print("usage: chat_any <provider> [login|show|hide|status]")
        return 1
    provider = args[0].lower()
    sub = args[1].lower() if len(args) > 1 else ""
    if sub in {"login","show","hide"}:
        if not daemon_alive():
            print("[FAIL] daemon not running. Start it with: aidaemon start")
            return 2
        try:
            print(daemon_call("POST", f"/{sub}/{provider}"))
        except Exception as e:
            print(f"[FAIL] {e}")
        return 0
    if sub == "status":
        if not daemon_alive():
            print("daemon: not running"); return 0
        print(daemon_call("GET", "/")); return 0
    if daemon_alive():
        return await chat_via_daemon(provider)
    print("[WARN] daemon not running — falling back to local (browser will appear)")
    print("       To use the daemon: aidaemon start")
    return await chat_local(provider)

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
