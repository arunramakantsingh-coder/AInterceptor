"""airouter-agent CLI."""
from __future__ import annotations
import argparse
import json
import pathlib
import platform
import socket
import sys
import urllib.error
import urllib.request

from airouter_agent import config
from airouter_agent.login import login_sync

PROVIDERS = ["claude", "chatgpt", "gemini", "deepseek"]


def _default_device_name() -> str:
    host = socket.gethostname() or "device"
    try:
        os_name = platform.system() or "unknown"
    except Exception:
        os_name = "unknown"
    return f"{host} ({os_name})"


def cmd_connect(args) -> int:
    """Exchange a code for a device token; save to config."""
    server = (args.server or "").rstrip("/")
    if not server:
        print("missing --server (e.g. http://100.82.62.82:8000)")
        return 1
    code = (args.code or "").strip()
    if not code:
        print("missing --code (get it from /dashboard/connect on the server)")
        return 1
    device_name = args.name or _default_device_name()
    os_name = platform.system() or None

    payload = json.dumps({
        "code": code,
        "device_name": device_name,
        "os": os_name,
    }).encode()
    req = urllib.request.Request(
        f"{server}/api/devices/exchange",
        data=payload, method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json"},
    )
    print(f"Exchanging code {code} with {server}...")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        print(f"[FAIL] server returned {e.code}: {detail}")
        print("       get a fresh code at:  {}/dashboard/connect".format(server))
        return 1
    except Exception as e:
        print(f"[FAIL] connection error: {e}")
        print("       is the server reachable? try:  curl {}/health".format(server))
        return 1

    token = body.get("token")
    if not token:
        print("[FAIL] server did not return a token")
        return 1

    cfg = config.load()
    cfg.server = server
    cfg.token = token
    config.save(cfg)

    print()
    print("=" * 60)
    print(" DEVICE CONNECTED")
    print("=" * 60)
    print(f"  device:  {device_name}")
    print(f"  server:  {server}")
    print(f"  token:   {token[:16]}... (saved to {config.CONFIG_PATH})")
    print()
    print(" Next:")
    print(f"   airouter-agent login claude      # log into a provider")
    print("=" * 60)
    return 0


def cmd_login(args) -> int:
    cfg = config.load()
    server = (args.server or cfg.server).rstrip("/")
    token = args.token or cfg.token
    if not server or not token:
        print("missing server or token.")
        print("  First connect this device:")
        print("    airouter-agent connect --server http://<vm-ip>:8000 --code XXXX-XXXX")
        print("  Or set manually:")
        print("    airouter-agent config --server URL --token TOKEN")
        return 1
    cfg.server, cfg.token = server, token
    config.save(cfg)
    return login_sync(args.provider, server, token)


def cmd_config(args) -> int:
    cfg = config.load()
    if args.server:
        cfg.server = args.server.rstrip("/")
    if args.token:
        cfg.token = args.token
    config.save(cfg)
    print(f"  server: {cfg.server or '(none)'}")
    if cfg.token:
        print(f"  token:  {cfg.token[:16]}... (prefix only)")
    else:
        print("  token:  (none)")
    print(f"  file:   {config.CONFIG_PATH}")
    return 0


def cmd_status(args) -> int:
    cfg = config.load()
    print("agent status")
    print(f"  server:  {cfg.server or '(not configured)'}")
    if cfg.token:
        print(f"  token:   {cfg.token[:16]}... ({'device' if cfg.token.startswith('sk-dev-') else 'other'})")
    else:
        print("  token:   (none)")
    print(f"  name:    {_default_device_name()}")
    print(f"  config:  {config.CONFIG_PATH}")

    if cfg.server and cfg.token:
        import urllib.request as _u
        try:
            req = _u.Request(f"{cfg.server}/health",
                             headers={"Accept": "application/json"})
            with _u.urlopen(req, timeout=5) as r:
                print(f"  server:  reachable (HTTP {r.status})")
        except Exception as e:
            print(f"  server:  [unreachable] {e}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="airouter-agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("connect", help="Exchange a device code for a token")
    pc.add_argument("--server", required=True)
    pc.add_argument("--code", required=True)
    pc.add_argument("--name", default=None,
                    help="Device name (default: hostname + OS)")
    pc.set_defaults(fn=cmd_connect)

    pl = sub.add_parser("login", help="Log into a provider and upload its session")
    pl.add_argument("provider", choices=PROVIDERS)
    pl.add_argument("--server", default="")
    pl.add_argument("--token", default="")
    pl.set_defaults(fn=cmd_login)

    pconf = sub.add_parser("config", help="Store server URL and token")
    pconf.add_argument("--server", default="")
    pconf.add_argument("--token", default="")
    pconf.set_defaults(fn=cmd_config)

    ps = sub.add_parser("status", help="Show agent configuration")
    ps.set_defaults(fn=cmd_status)

    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
