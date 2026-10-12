"""OSI-layer latency probe. Called by admin_cli as `atest osi <provider>`.

Reads the provider's home_url from its own file (R10-compliant — no
dispatch branching, no provider-specific logic here). Pure measurement:
DNS, ICMP, TCP, TLS, HTTP TTFB. Does NOT send a chat message (that is
the job of the default `atest <provider>` mode) so this command is
idempotent and does not pollute provider chat history.
"""
from __future__ import annotations

import pathlib
import re
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[2]


def _provider_home_url(provider: str) -> str | None:
    f = ROOT / "backend" / "app" / "interception" / provider / "__init__.py"
    if not f.exists():
        return None
    m = re.search(r'home_url\s*=\s*["\']([^"\']+)["\']', f.read_text())
    return m.group(1) if m else None


def _host(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else url


def _dns_ms(host: str) -> tuple[float, str]:
    t0 = time.perf_counter()
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addrs = sorted({i[4][0] for i in infos})
        return (time.perf_counter() - t0) * 1000.0, addrs[0] if addrs else "?"
    except Exception as e:
        return -1.0, f"err: {e}"


def _ping(host: str) -> dict:
    try:
        r = subprocess.run(["ping", "-c", "4", "-W", "2", host],
                           capture_output=True, text=True, timeout=15)
        txt = r.stdout + r.stderr
        m = re.search(r"=\s*([\d.]+)/([\d.]+)/([\d.]+)/", txt)
        loss = re.search(r"(\d+)% packet loss", txt)
        if m:
            return {"min": float(m.group(1)), "avg": float(m.group(2)),
                    "max": float(m.group(3)),
                    "loss": int(loss.group(1)) if loss else -1}
    except Exception:
        pass
    return {"min": -1, "avg": -1, "max": -1, "loss": -1}


def _tcp_ms(host: str) -> float:
    t0 = time.perf_counter()
    try:
        s = socket.create_connection((host, 443), timeout=5)
        s.close()
        return (time.perf_counter() - t0) * 1000.0
    except Exception:
        return -1.0


def _tls_ms(host: str) -> float:
    t0 = time.perf_counter()
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=5) as raw:
            with ctx.wrap_socket(raw, server_hostname=host):
                pass
        return (time.perf_counter() - t0) * 1000.0
    except Exception:
        return -1.0


def _http_ttfb_ms(url: str) -> dict:
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ainterceptor-osi/1"})
        with urllib.request.urlopen(req, timeout=10) as r:
            _ = r.read(1024)
            return {
                "ttfb_ms": (time.perf_counter() - t0) * 1000.0,
                "status": r.status,
                "server": r.headers.get("server", "?"),
                "cf_ray": r.headers.get("cf-ray", ""),
            }
    except urllib.error.HTTPError as e:
        return {
            "ttfb_ms": (time.perf_counter() - t0) * 1000.0,
            "status": e.code,
            "server": e.headers.get("server", "?"),
            "cf_ray": e.headers.get("cf-ray", ""),
        }
    except Exception as e:
        return {"ttfb_ms": -1.0, "status": 0, "server": f"err: {e}", "cf_ray": ""}


def run(provider: str) -> int:
    provider = provider.lower()
    url = _provider_home_url(provider)
    if not url:
        print(f"[FAIL] no home_url in interception/{provider}/__init__.py")
        return 1
    host = _host(url)

    print(f"═══ OSI probe: {provider} ═══")
    print(f"  target: {url}")
    print(f"  host:   {host}")
    print()

    dns, addr = _dns_ms(host)
    print(f"  L3   DNS resolve        {dns:8.1f} ms   ({addr})")

    p = _ping(host)
    if p["avg"] >= 0:
        print(f"  L3   ICMP RTT avg       {p['avg']:8.1f} ms   "
              f"(min {p['min']:.1f} / max {p['max']:.1f}, {p['loss']}% loss)")
    else:
        print(f"  L3   ICMP RTT avg       (no reply — may be blocked)")

    tcp = _tcp_ms(host)
    print(f"  L4   TCP connect        {tcp:8.1f} ms" if tcp >= 0
          else "  L4   TCP connect        (failed)")

    tls = _tls_ms(host)
    print(f"  L6   TLS handshake      {tls:8.1f} ms" if tls >= 0
          else "  L6   TLS handshake      (failed)")

    http = _http_ttfb_ms(url)
    cf = f" cf-ray={http['cf_ray']}" if http.get("cf_ray") else ""
    print(f"  L7   HTTP TTFB          {http['ttfb_ms']:8.1f} ms   "
          f"(status {http['status']}, server {http['server']}{cf})")

    print()
    if tcp >= 0 and tls >= 0 and http["ttfb_ms"] >= 0:
        floor = dns + tcp + tls + http["ttfb_ms"]
        print(f"  network floor:          {floor:8.1f} ms   (DNS + TCP + TLS + TTFB)")
        print(f"  — the rest, up to end-to-end reply, is the AIP thinking.")
    print()
    print("  NOTE: use `atest <provider>` to measure the full chat round-trip.")
    return 0
