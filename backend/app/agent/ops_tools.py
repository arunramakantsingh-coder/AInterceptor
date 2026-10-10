"""Operational tools AIN exposes to AIPs.

These run on the VM (where AIN lives). The AIP plans; AIN executes;
result feeds back. No model decision needed for the mechanics of the
scan -- only for interpreting the output.

Rule refs:
  R10  provider-neutral. Every AIP sees the same tools.
  R11  no polling. Each tool is a one-shot subprocess.run.
"""
from __future__ import annotations
import ipaddress
import json
import shutil
import socket
import subprocess
import time


def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """Run a subprocess. Returns (rc, stdout, stderr). Never raises."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: not found"
    except Exception as e:
        return 1, "", f"{type(e).__name__}: {e}"


# ── tool: list_capabilities ─────────────────────────────────────────
def list_capabilities(args: dict) -> str:
    """Report which external tools AIN can drive on this host."""
    wanted = ["nmap", "arp-scan", "masscan", "ping", "curl", "wget",
              "ssh", "git", "docker", "ansible", "tailscale",
              "tcpdump", "ss", "netstat", "jq", "python3"]
    found = {}
    for w in wanted:
        p = shutil.which(w)
        found[w] = p or None
    have = sorted(k for k, v in found.items() if v)
    miss = sorted(k for k, v in found.items() if not v)
    out = [f"Available on this host: {', '.join(have)}"]
    if miss:
        out.append(f"Missing (installable via apt): {', '.join(miss)}")
    return "\n".join(out)


# ── tool: tailscale_status ──────────────────────────────────────────
def tailscale_status(args: dict) -> str:
    """Return this node's tailnet peers as a compact table."""
    rc, out, err = _run(["tailscale", "status", "--json"], timeout=10)
    if rc != 0:
        return f"error: {err or 'tailscale not available'}"
    try:
        d = json.loads(out)
    except Exception as e:
        return f"error parsing tailscale json: {e}"
    peers = d.get("Peer") or {}
    self_ = d.get("Self") or {}
    rows = []
    rows.append(f"SELF  {self_.get('HostName','?')}  {self_.get('TailscaleIPs',['?'])[0]}  online={self_.get('Online')}")
    for _, p in peers.items():
        rows.append(f"PEER  {p.get('HostName','?'):20s}  "
                    f"{(p.get('TailscaleIPs') or ['?'])[0]:15s}  "
                    f"online={p.get('Online')}  os={p.get('OS','?')}")
    return "\n".join(rows)


# ── tool: probe_port ────────────────────────────────────────────────
def probe_port(args: dict) -> str:
    """TCP-connect probe. args: host, port, timeout_s (optional)."""
    host = args.get("host") or ""
    port = int(args.get("port") or 0)
    timeout = float(args.get("timeout_s") or 3.0)
    if not host or not (1 <= port <= 65535):
        return "error: need host and 1<=port<=65535"
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            dt = (time.perf_counter() - t0) * 1000.0
            return f"OPEN   {host}:{port}  ({dt:.0f} ms)"
    except socket.timeout:
        return f"TIMEOUT {host}:{port}  (>{timeout}s)"
    except ConnectionRefusedError:
        return f"CLOSED {host}:{port}  (refused)"
    except Exception as e:
        return f"ERROR  {host}:{port}  {type(e).__name__}: {e}"


# ── tool: scan_lan ──────────────────────────────────────────────────
def scan_lan(args: dict) -> str:
    """Run nmap against a CIDR or IP. Uses -sn (ping scan) unless
    ports given, then -p with TCP-connect (-sT, no root needed)."""
    target = args.get("range") or ""
    ports = (args.get("ports") or "").strip()
    if not target:
        return "error: need 'range' (CIDR or single IP)"
    # validate the target so we never scan arbitrary things
    try:
        net = ipaddress.ip_network(target, strict=False)
    except Exception:
        try:
            net = ipaddress.ip_network(target + "/32", strict=False)
        except Exception as e:
            return f"error: bad target {target!r}: {e}"
    # basic safety: refuse /0 and /1
    if net.prefixlen < 16:
        return "error: refusing to scan a range larger than /16"
    if not shutil.which("nmap"):
        return ("error: nmap not installed. Ask the operator to run:\n"
                "  sudo apt install -y nmap")
    if ports:
        cmd = ["nmap", "-sT", "-Pn", "-p", ports, "-T4", str(net)]
    else:
        cmd = ["nmap", "-sn", "-T4", str(net)]
    rc, out, err = _run(cmd, timeout=300)
    if rc != 0:
        return f"error (rc={rc}): {err.strip()[:400]}"
    # trim to first 60 lines to keep replies small
    lines = out.splitlines()
    if len(lines) > 60:
        lines = lines[:60] + [f"... ({len(out.splitlines())-60} more lines)"]
    return "\n".join(lines)
