"""AInterceptor admin ops - system/lifecycle commands."""
from __future__ import annotations
import pathlib, subprocess, sys, time

_HERE = pathlib.Path(__file__).resolve()
ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

CDP_PORT = 9222


def _daemon_pid():
    try:
        r = subprocess.run(["pgrep", "-f", "app.runtime.daemon"],
                           capture_output=True, text=True, timeout=3)
        pids = [int(x) for x in r.stdout.split() if x.strip().isdigit()]
        return pids[0] if pids else None
    except Exception:
        return None


def astop():
    pid = _daemon_pid()
    if not pid:
        print("[i] daemon not running")
        return 0
    subprocess.run(["pkill", "-f", "app.runtime.daemon"], capture_output=True)
    subprocess.run(["pkill", "-f", f"remote-debugging-port={CDP_PORT}"],
                   capture_output=True)
    time.sleep(2)
    if _daemon_pid():
        print("[FAIL] daemon still alive")
        return 1
    print("[OK] daemon + Chrome stopped")
    return 0


def abootstrap():
    print("[..] running bootstrap_admin")
    return subprocess.call(["python", "-m", "scripts.bootstrap_admin"],
                           cwd=str(ROOT / "backend"))


def asave(message):
    if not message:
        print('usage: asave "commit message"')
        return 1
    r = subprocess.run(["git", "-C", str(ROOT), "status", "--short"],
                       capture_output=True, text=True)
    if not r.stdout.strip():
        print("[i] nothing to commit")
        return 0
    subprocess.run(["git", "-C", str(ROOT), "add", "-A"], check=False)
    rc = subprocess.call(["git", "-C", str(ROOT), "commit", "-m", message])
    if rc != 0:
        print("[FAIL] commit failed")
        return rc
    br = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
                        capture_output=True, text=True).stdout.strip()
    rc = subprocess.call(["git", "-C", str(ROOT), "push", "origin", br])
    if rc != 0:
        print("[FAIL] push failed (commit is local)")
        return rc
    print(f"[OK] committed + pushed to {br}")
    return 0


def aconfig_reset(key):
    defaults = {
        "AINTERCEPTOR_PROBER_ENABLED": "0",
        "AINTERCEPTOR_ACTIVE_PROVIDERS": "claude,chatgpt,gemini,deepseek",
    }
    if key not in defaults:
        print(f"[FAIL] no default for: {key}")
        print(f"       known: {', '.join(defaults)}")
        return 1
    env_file = ROOT / ".env"
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    out, found = [], False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={defaults[key]}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={defaults[key]}")
    env_file.write_text("\n".join(out) + "\n")
    print(f"[OK] {key} = {defaults[key]}")
    print("     restart daemon to apply:  arestart")
    return 0

def _port_8000_listening():
    import socket
    s = socket.socket()
    s.settimeout(1.0)
    try:
        s.connect(("127.0.0.1", 8000))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _daemon_up_in_log():
    log = ROOT / ".ainterceptor" / "daemon.log"
    if not log.exists():
        return False
    try:
        return "[daemon] up." in log.read_text(errors="replace")
    except Exception:
        return False


def _wait_daemon_gone(timeout_s=15):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if not _daemon_pid() and not _port_8000_listening():
            return True
        time.sleep(0.5)
    return False


def _wait_chrome_gone(timeout_s=15):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = subprocess.run(["pgrep", "-f", "remote-debugging-port=9222"],
                           capture_output=True, text=True)
        if not r.stdout.strip():
            return True
        time.sleep(0.5)
    return False


def astop():
    pid = _daemon_pid()
    if not pid:
        print("[i] daemon not running")
        return 0
    print(f"[..] stopping daemon (pid {pid})")
    subprocess.run(["pkill", "-f", "app.runtime.daemon"], capture_output=True)
    subprocess.run(["pkill", "-f", f"remote-debugging-port={CDP_PORT}"],
                   capture_output=True)
    if not _wait_daemon_gone(15):
        print("[warn] daemon still present after 15s")
    if not _wait_chrome_gone(15):
        print("[warn] Chrome still running after 15s")
    for f in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        lock = ROOT / ".ainterceptor" / "chrome-profile" / f
        try:
            if lock.exists() or lock.is_symlink():
                lock.unlink()
        except Exception:
            pass
    time.sleep(1)
    print("[OK] daemon + Chrome stopped")
    return 0


def _spawn_daemon():
    log = ROOT / ".ainterceptor" / "daemon.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        log.write_text("", encoding="utf-8")
    except Exception:
        pass
    fh = open(log, "ab")
    subprocess.Popen(
        ["bash", "-lc", "cd ~/ainterceptor && ./run-linux.sh"],
        stdout=fh, stderr=fh, start_new_session=True,
    )


def _poll_up(timeout_s=60):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if _daemon_up_in_log() and _port_8000_listening():
            return True
        time.sleep(1.0)
    return False


def astart(fg=False):
    if not fg and _daemon_pid() and _port_8000_listening():
        print(f"[i] daemon already running (pid {_daemon_pid()}, port 8000)")
        print("     arestart    restart (background)")
        print("     astop       stop")
        return 0
    if fg:
        print("[..] starting in FOREGROUND (Ctrl+C to stop)")
        return subprocess.call(["bash", "-lc", "cd ~/ainterceptor && ./run-linux.sh"])
    if _daemon_pid() and not _port_8000_listening():
        print(f"[warn] stale pid {_daemon_pid()} without port 8000 — stopping")
        astop()
    print("[..] starting (background)")
    _spawn_daemon()
    if _poll_up(60):
        print(f"[OK] daemon up (pid {_daemon_pid()}, port 8000)")
        print("     alogs daemon")
        return 0
    print("[FAIL] daemon did not come up within 60s")
    print("       alogs daemon")
    return 1


def arestart(fg=False):
    astop()
    return astart(fg=fg)
