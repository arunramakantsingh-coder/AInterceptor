"""Local helper: tiny HTTP server so the AInterceptor web UI can run
agent commands on this laptop. Bound to 127.0.0.1 only; CORS-locked
to AInterceptor origins.
"""
from __future__ import annotations
import json
import platform
import secrets
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


def main(port: int = DEFAULT_PORT) -> int:
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
