"""run.py — start backend + dashboard as background services, open browser."""
import subprocess, sys, time, pathlib, os, webbrowser, signal, socket

ROOT = pathlib.Path(__file__).resolve().parent
BE   = ROOT / "backend"
DASH = ROOT / "dashboard"
VENV_PY = BE / ".venv" / "Scripts" / "python.exe"

def port_open(port: int) -> bool:
    s = socket.socket(); s.settimeout(0.3)
    try: s.connect(("127.0.0.1", port)); return True
    except OSError: return False
    finally: s.close()

def wait_port(port: int, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if port_open(port): return True
        time.sleep(0.5)
    return False

print("==> AInterceptor launcher")
procs = []

def start(name, args, cwd, env=None):
    print(f"    starting {name} …")
    kwargs = dict(cwd=str(cwd), shell=False,
                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                  text=True, bufsize=1)
    if env: kwargs["env"] = env
    p = subprocess.Popen(args, **kwargs)
    procs.append((name, p))
    return p

# 1. Backend
if not VENV_PY.exists():
    print(f"[FAIL] missing venv python: {VENV_PY}"); sys.exit(1)

be_env = os.environ.copy()
be_env["PYTHONPATH"] = str(BE)

start("backend",
      [str(VENV_PY), "-m", "uvicorn", "app.api.main:app",
       "--host", "127.0.0.1", "--port", "8000"],
      cwd=BE, env=be_env)

# 2. Dashboard
npm = "npm.cmd" if os.name == "nt" else "npm"
start("dashboard",
      [npm, "run", "dev"],
      cwd=DASH)

# 3. Wait for both
print("    waiting for backend :8000 …")
if not wait_port(8000, 45):
    print("[FAIL] backend did not start on :8000"); sys.exit(1)
print("    backend ready")

print("    waiting for dashboard :4000 …")
if not wait_port(4000, 60):
    print("[FAIL] dashboard did not start on :4000"); sys.exit(1)
print("    dashboard ready")

# 4. Open browser
url = "http://localhost:4000/intercept"
print(f"==> opening {url}")
webbrowser.open(url)

print()
print("="*44)
print("RUNNING")
print(f"  Backend:   http://127.0.0.1:8000/health")
print(f"  Dashboard: http://localhost:4000")
print(f"  Intercept: {url}")
print("  Ctrl+C here stops both services.")
print("="*44)

# Stream child output and wait
try:
    import threading, queue
    q = queue.Queue()
    def reader(name, p):
        for line in p.stdout:
            q.put((name, line.rstrip()))
    for name, p in procs:
        threading.Thread(target=reader, args=(name, p), daemon=True).start()
    while True:
        try:
            name, line = q.get(timeout=0.3)
            if line: print(f"[{name}] {line}")
        except queue.Empty:
            if all(p.poll() is not None for _, p in procs):
                break
except KeyboardInterrupt:
    print("\n==> stopping…")
    for name, p in procs:
        try: p.terminate()
        except: pass
    sys.exit(0)
