"""AInterceptor admin ops - read commands."""
from __future__ import annotations
import datetime, json, pathlib, subprocess, sys, time

_HERE = pathlib.Path(__file__).resolve()
ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

EXPORT_DIR = pathlib.Path.home() / ".ainterceptor" / "exports"
KEY_FILE   = pathlib.Path.home() / ".ainterceptor" / "admin_api_key.txt"
BASE_URL   = "http://127.0.0.1:8000"
CDP_PORT   = 9222
EVIDENCE_DIR = ROOT / ".evidence"

LOG_FILES = {
    "daemon": ROOT / ".ainterceptor" / "daemon.log",
    "chrome": ROOT / ".ainterceptor" / "chrome_launch.log",
    "x11vnc": pathlib.Path.home() / ".vnc" / "x11vnc.log",
}


def _token():
    return KEY_FILE.read_text().strip() if KEY_FILE.exists() else None


def _api(method, path, body=None):
    import urllib.request, urllib.error
    h = {"Accept": "application/json"}
    t = _token()
    if t:
        h["Authorization"] = f"Bearer {t}"
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "replace")}
    except Exception as e:
        return 0, {"error": str(e)}


def _daemon_pid():
    try:
        r = subprocess.run(["pgrep", "-f", "app.runtime.daemon"],
                           capture_output=True, text=True, timeout=3)
        pids = [int(x) for x in r.stdout.split() if x.strip().isdigit()]
        return pids[0] if pids else None
    except Exception:
        return None


def _read_env():
    d = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def asessions_list():
    code, body = _api("GET", "/api/sessions")
    if code != 200:
        print(f"[FAIL] daemon returned {code}: {body.get('error', body)}")
        print("       is the daemon running?  astatus")
        return 1
    if not body:
        print("  (no sessions)")
        print("  Next:  airouter-agent login <provider>")
        print("         alogin <provider>  (VNC)")
        return 0
    print(f"  {'PROVIDER':12s}  {'ALIAS':10s}  {'STATUS':10s}  CREATED")
    print("  " + "-" * 62)
    for s in body:
        created = (s.get("created_at") or "")[:19]
        print(f"  {s['provider']:12s}  {s['alias']:10s}  {s['status']:10s}  {created}")
    return 0


def asessions_export(provider, out=None):
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    src = EXPORT_DIR / f"{provider}.json"
    if not src.exists():
        print(f"[FAIL] no file: {src}")
        print(f"       create:  airouter-agent login {provider}")
        return 1
    if out:
        import shutil
        shutil.copy2(src, out)
        print(f"[OK] copied -> {out}")
    else:
        print(f"[OK] {src} ({src.stat().st_size} bytes)")
    return 0


def asessions_delete(provider):
    code, body = _api("GET", "/api/sessions")
    if code != 200:
        print(f"[FAIL] {code}")
        return 1
    t = next((s for s in body if s["provider"] == provider), None)
    if not t:
        print(f"[FAIL] no session for {provider}")
        return 1
    code, _ = _api("DELETE", f"/api/sessions/{t['id']}")
    print(f"[OK] deleted {provider}" if code == 200 else f"[FAIL] {code}")
    return 0 if code == 200 else 1


def ahealth():
    code, body = _api("GET", "/health")
    if code != 200:
        print(f"[FAIL] /health {code}")
        print("       astatus")
        return 1
    if isinstance(body, dict):
        for k in sorted(body):
            v = body[k]
            if isinstance(v, dict):
                print(f"  {k}:")
                for kk in sorted(v):
                    print(f"    {kk}: {v[kk]}")
            else:
                print(f"  {k}: {v}")
    else:
        print(json.dumps(body, indent=2))
    return 0


def aversion():
    import platform
    print(f"  AInterceptor  : 0.1.0")
    print(f"  Python        : {platform.python_version()}")
    print(f"  Platform      : {platform.system()} {platform.release()}")
    try:
        import playwright
        print(f"  Playwright    : {getattr(playwright, '__version__', 'unknown')}")
    except Exception:
        print("  Playwright    : (not installed)")
    try:
        r = subprocess.run(["google-chrome", "--version"],
                           capture_output=True, text=True, timeout=5)
        print(f"  Chrome        : {r.stdout.strip()}")
    except Exception:
        print("  Chrome        : (not found)")
    env = _read_env()
    print(f"  prober flag   : {env.get('AINTERCEPTOR_PROBER_ENABLED', '?')}")
    print(f"  active provs  : {env.get('AINTERCEPTOR_ACTIVE_PROVIDERS', '?')}")
    return 0


def alogs(which="daemon", lines=40):
    path = LOG_FILES.get(which)
    if path is None:
        print(f"[FAIL] unknown log: {which}")
        print(f"       known: {', '.join(LOG_FILES)}")
        return 1
    if not path.exists():
        print(f"[FAIL] no log at {path}")
        return 1
    try:
        txt = path.read_text(errors="replace").splitlines()
    except Exception as e:
        print(f"[FAIL] {e}")
        return 1
    tail = txt[-lines:]
    print(f"== {path}  (last {len(tail)} of {len(txt)}) ==")
    for line in tail:
        print(f"  {line}")
    return 0


def aevidence_list():
    if not EVIDENCE_DIR.exists():
        print("  (no .evidence/)")
        return 0
    files = sorted(EVIDENCE_DIR.glob("*"),
                   key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        print("  (empty)")
        return 0
    print(f"  {'NAME':45s}  {'SIZE':>8s}  MODIFIED")
    for f in files[:20]:
        st = f.stat()
        mt = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {f.name:45s}  {st.st_size:>8d}  {mt}")
    return 0


def aevidence_show(name):
    p = EVIDENCE_DIR / name
    if not p.exists():
        print(f"[FAIL] not found: {name}")
        return 1
    print(p.read_text(errors="replace"))
    return 0


def aevidence_clear(days=30):
    if not EVIDENCE_DIR.exists():
        print("  (nothing to clear)")
        return 0
    cutoff = time.time() - days * 86400
    n = 0
    for f in EVIDENCE_DIR.glob("*"):
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                n += 1
        except Exception:
            pass
    print(f"[OK] removed {n} file(s) older than {days}d")
    return 0
