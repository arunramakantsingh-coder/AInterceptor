"""airouter-agent CLI."""
from __future__ import annotations
import argparse, sys
from airouter_agent import config
from airouter_agent.login import login_sync

PROVIDERS = ["claude", "chatgpt", "gemini", "deepseek"]


def cmd_login(args) -> int:
    cfg = config.load()
    server = args.server or cfg.server
    token = args.token or cfg.token
    if not server or not token:
        print("missing server or token. Run: airouter-agent config --server URL --token TOKEN")
        return 1
    cfg.server, cfg.token = server, token
    config.save(cfg)
    return login_sync(args.provider, server, token)


def cmd_config(args) -> int:
    cfg = config.load()
    if args.server: cfg.server = args.server
    if args.token:  cfg.token = args.token
    config.save(cfg)
    print(f"server: {cfg.server}")
    print(f"token : {cfg.token[:16]}…" if cfg.token else "token : (none)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="airouter-agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("login", help="Log into a provider and upload its session")
    pl.add_argument("provider", choices=PROVIDERS)
    pl.add_argument("--server", default="")
    pl.add_argument("--token", default="")
    pl.set_defaults(fn=cmd_login)

    pc = sub.add_parser("config", help="Store server URL and token")
    pc.add_argument("--server", default="")
    pc.add_argument("--token", default="")
    pc.set_defaults(fn=cmd_config)

    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
