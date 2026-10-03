import pathlib, subprocess

ROOT = pathlib.Path.cwd()
AL = ROOT / "alembic"
(AL / "versions").mkdir(parents=True, exist_ok=True)
AGENT = ROOT / "agent" / "airouter_agent"
AGENT.mkdir(parents=True, exist_ok=True)

F = {}

F["alembic.ini"] = """[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""

F["alembic/env.py"] = '''from __future__ import annotations
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = os.environ.get("DATABASE_URL")
if url:
    config.set_main_option("sqlalchemy.url", url)

import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from backend.app.db.session import Base  # noqa: E402
from backend.app.db import models  # noqa: F401,E402

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''

F["alembic/script.py.mako"] = '''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
'''

F["alembic/versions/0001_initial.py"] = '''"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("alias", sa.String(32), nullable=False, server_default="default"),
        sa.Column("encrypted_blob", sa.LargeBinary, nullable=False),
        sa.Column("nonce", sa.LargeBinary, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "provider", "alias", name="uq_user_provider_alias"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_provider", "user_sessions", ["provider"])

    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("api_key_id", sa.String(36), sa.ForeignKey("api_keys.id")),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("path", sa.String(1), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_usage_events_user_id", "usage_events", ["user_id"])
    op.create_index("ix_usage_events_provider", "usage_events", ["provider"])


def downgrade() -> None:
    op.drop_table("usage_events")
    op.drop_table("user_sessions")
    op.drop_table("api_keys")
    op.drop_table("users")
'''

F["agent/airouter_agent/__init__.py"] = '"""AInterceptor user-side agent."""\n__version__ = "0.1.0"\n'

F["agent/airouter_agent/config.py"] = '''"""Local config file at ~/.airouter/config.json."""
from __future__ import annotations
import json, pathlib
from dataclasses import dataclass, asdict

CONFIG_PATH = pathlib.Path.home() / ".airouter" / "config.json"


@dataclass
class AgentConfig:
    server: str = ""
    token: str = ""


def load() -> AgentConfig:
    if not CONFIG_PATH.exists():
        return AgentConfig()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return AgentConfig(server=data.get("server", ""), token=data.get("token", ""))
    except Exception:
        return AgentConfig()


def save(cfg: AgentConfig) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
'''

F["agent/airouter_agent/login.py"] = '''"""Provider login flow: opens a real Chrome, waits for login, uploads state."""
from __future__ import annotations
import asyncio, json, pathlib, sys, tempfile
import httpx

LOGIN_URLS = {
    "claude":   "https://claude.ai/",
    "chatgpt":  "https://chatgpt.com/",
    "gemini":   "https://gemini.google.com/",
    "deepseek": "https://chat.deepseek.com/",
}
LOGIN_MARKERS = {
    "claude":   ("/login", "/auth", "/signin"),
    "chatgpt":  ("/auth/login", "/auth/0"),
    "gemini":   ("/accounts/", "signin"),
    "deepseek": ("/login", "/auth", "/sign_in", "/signin"),
}


async def _wait_until_logged_in(page, provider: str, timeout: int = 600) -> None:
    markers = LOGIN_MARKERS[provider]
    import time
    t0 = time.monotonic()
    print("Waiting for you to log in (up to 10 minutes)…")
    while time.monotonic() - t0 < timeout:
        await asyncio.sleep(2)
        url = (page.url or "").lower()
        if not any(m.lower() in url for m in markers):
            await asyncio.sleep(2)
            if not any(m.lower() in (page.url or "").lower() for m in markers):
                print("Login detected.")
                return
    raise TimeoutError("login did not complete in time")


async def run_login(provider: str, server: str, token: str) -> int:
    if provider not in LOGIN_URLS:
        print(f"unknown provider: {provider}")
        return 1
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("playwright not installed. Run:")
        print("  pip install playwright")
        print("  python -m playwright install chromium")
        return 1

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(LOGIN_URLS[provider])
        try:
            await _wait_until_logged_in(page, provider)
        except TimeoutError as e:
            print(f"error: {e}")
            await browser.close()
            return 1

        state = await ctx.storage_state()
        await browser.close()

    tmp = pathlib.Path(tempfile.mkstemp(suffix=".json")[1])
    tmp.write_text(json.dumps(state), encoding="utf-8")

    print(f"Uploading {provider} session to {server}…")
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            with open(tmp, "rb") as fh:
                files = {"file": ("storage_state.json", fh, "application/json")}
                data = {"provider": provider, "alias": "default"}
                r = await c.post(f"{server.rstrip('/')}/api/sessions/upload",
                                 headers={"Authorization": f"Bearer {token}"},
                                 files=files, data=data)
        if r.status_code != 200:
            print(f"upload failed: {r.status_code} {r.text}")
            return 1
        print(f"Session for {provider} uploaded successfully.")
        return 0
    finally:
        try: tmp.unlink()
        except Exception: pass


def login_sync(provider: str, server: str, token: str) -> int:
    return asyncio.run(run_login(provider, server, token))
'''

F["agent/airouter_agent/cli.py"] = '''"""airouter-agent CLI."""
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
'''

F["agent/pyproject.toml"] = """[project]
name = "airouter-agent"
version = "0.1.0"
description = "AInterceptor user-side login agent"
requires-python = ">=3.10"
dependencies = [
    "playwright>=1.48.0",
    "httpx>=0.27.2",
]

[project.scripts]
airouter-agent = "airouter_agent.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["airouter_agent*"]
"""

for rel, txt in F.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}  ({len(txt)} B)")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(phase-1): alembic migrations + user-side login agent"])
print((r.stdout.strip() or r.stderr.strip())[:400])
print("DONE — script 5/6. Run script 6 next.")
