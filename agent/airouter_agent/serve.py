"""Local helper: tiny HTTP server so the AInterceptor web UI can run
agent commands on this laptop. Bound to 127.0.0.1 only; CORS-locked
to AInterceptor origins.
"""
from __future__ import annotations
import json
import platform
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from airouter_agent import config

DEFAULT_PORT = 45231
DEFAULT_HOST = "127.0.0.1"

# Only these origins may call us from a browser
ALLOWED_ORIGINS = {
    "https://ainterceptor.taila2310c.ts.net",
    "http://100.82.62.82:8000",
    "http://localhost:8000",
}

# Jobs in memory — cleared on restart
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _allowed_origin(origin: str) -> bool:
    if not origin:
        return False
    return origin.rstrip("/") in ALLOWED_ORIGINS


def _run_login_job(job_id: str, provider: str) -> None:
    """Spawn `airouter-agent login <provider>` and capture output."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "airouter_agent.cli", "login", provider],
            capture_output=True, text=True, timeout=600,
        )
        with _JOBS_LOCK:
            _JOBS[job_id].update({
                "status": "done" if proc.returncode == 0 else "failed",
                "exit_code": proc.returncode,
                "output": (proc.stdout or "") + (proc.stderr or ""),
                "finished_at": time.time(),
            })
    except Exception as e:
        with _JOBS_LOCK:
            _JOBS[job_id].update({
                "status": "failed",
                "exit_code": -1,
                "output": f"exception: {e}",
                "finished_at": time.time(),
            })


class Handler(BaseHTTPRequestHandler):
    server_version = "airouter-agent/0.1"

    def log_message(self, fmt, *args):
        # Keep the console clean — one line per request
        sys.stderr.write(f"[agent-serve] {fmt % args}\n")

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if _allowed_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin.rstrip("/"))
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")

    def _json(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/status":
            cfg = config.load()
            server_ok = False
            if cfg.server:
                try:
                    with urllib.request.urlopen(f"{cfg.server}/health", timeout=3) as r:
                        server_ok = r.status == 200
                except Exception:
                    pass
            return self._json(200, {
                "ok": True,
                "version": "0.1.0",
                "os": platform.system(),
                "hostname": platform.node(),
                "server": cfg.server or "",
                "has_token": bool(cfg.token),
                "server_reachable": server_ok,
            })
        if path.startswith("/job/"):
            job_id = path[len("/job/"):]
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
            if not job:
                return self._json(404, {"error": "unknown job"})
            return self._json(200, job)
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/login/"):
            return self._json(404, {"error": "not found"})
        provider = path[len("/login/"):].strip().lower()
        if not provider or not provider.isalnum():
            return self._json(400, {"error": "invalid provider"})

        job_id = secrets.token_urlsafe(12)
        with _JOBS_LOCK:
            _JOBS[job_id] = {
                "id": job_id,
                "provider": provider,
                "status": "running",
                "started_at": time.time(),
                "output": "",
            }
        threading.Thread(target=_run_login_job, args=(job_id, provider),
                         daemon=True).start()
        return self._json(200, {"job_id": job_id, "provider": provider})


def _try_bind(port: int) -> bool:
    """Can we bind 127.0.0.1:port right now?"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((DEFAULT_HOST, port))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _ensure_port_bindable(port: int) -> bool:
    """Make sure we can bind `port`. On Windows, if Windows has reserved
    it (Hyper-V/WSL/Docker grab dynamic port ranges), ask the user once
    to let us reserve it via netsh — elevated. Idempotent: if the port
    is already reserved from a previous run, the elevation is skipped.
    """
    if _try_bind(port):
        return True

    if platform.system() != "Windows":
        print(f"[agent] port {port} is in use. Close whatever is using it and retry.")
        return False

    print()
    print("=" * 64)
    print(f"[agent] Port {port} is blocked by Windows.")
    print("[agent] This usually means Hyper-V, WSL, or Docker reserved it")
    print("[agent] inside their dynamic port range. We can fix it once,")
    print("[agent] for good, with admin rights.")
    print("=" * 64)
    print()
    print("[agent] A UAC prompt will appear. Click Yes to reserve the port.")
    print()

    # Single elevated PowerShell invocation: stop winnat, add the exclusion,
    # restart winnat. The '&' chains commands so the whole sequence runs in
    # one elevated shell, avoiding multiple UAC prompts.
    inner = (
        f"net stop winnat & "
        f"netsh int ipv4 add excludedportrange protocol=tcp "
        f"startport={port} numberofports=1 & "
        f"net start winnat"
    )
    ps_cmd = (
        "Start-Process powershell -Verb RunAs -Wait "
        "-ArgumentList '-NoProfile','-Command','" + inner + "'"
    )

    try:
        rc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=60,
        )
        if rc.returncode != 0:
            print(f"[agent] elevation returned {rc.returncode}")
            if rc.stderr:
                print(rc.stderr[:400])
    except Exception as e:
        print(f"[agent] elevation failed: {e}")
        return False

    # Retry bind
    if _try_bind(port):
        print(f"[agent] port {port} is now reserved and bindable. Setup complete.")
        return True

    print(f"[agent] port {port} still not bindable after netsh.")
    print(f"[agent] Run this manually in an Admin PowerShell, then retry serve:")
    print(f"    net stop winnat")
    print(f"    netsh int ipv4 add excludedportrange protocol=tcp startport={port} numberofports=1")
    print(f"    net start winnat")
    return False


def main(port: int = DEFAULT_PORT) -> int:
    if not _ensure_port_bindable(port):
        return 1
    addr = (DEFAULT_HOST, port)
    httpd = ThreadingHTTPServer(addr, Handler)
    print(f"[agent-serve] listening on http://{DEFAULT_HOST}:{port}")
    print(f"[agent-serve] allowed origins: {sorted(ALLOWED_ORIGINS)}")
    print("[agent-serve] Ctrl+C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[agent-serve] stopped")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="airouter-agent serve")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()
    sys.exit(main(args.port))
