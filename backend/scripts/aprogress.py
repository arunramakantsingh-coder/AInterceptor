"""aprogress — regenerate a summary block in .ai/PROGRESS.md from git log.

Usage:
  aprogress               regenerate + prepend today's snapshot
  aprogress --show        just print the summary, don't write
  aprogress --commits 50  look at last 50 commits (default 30)
"""
from __future__ import annotations
import argparse
import pathlib
import subprocess
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PROGRESS = ROOT / ".ai" / "PROGRESS.md"
ENV = ROOT / ".env"


def _git_log(n: int):
    try:
        r = subprocess.run(
            ["git", "-C", str(ROOT), "log",
             f"-n{n}", "--pretty=format:%h|%s|%ci"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return []
        rows = []
        for line in r.stdout.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                rows.append({"sha": parts[0], "msg": parts[1], "date": parts[2][:10]})
        return rows
    except Exception:
        return []


def _classify(msg: str) -> str:
    m = msg.lower()
    for tag in ("feat", "fix", "docs", "chore", "test", "refactor", "perf", "release"):
        if m.startswith(tag):
            return tag
    return "other"


def _read_env() -> dict:
    d = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def _recent_providers(env: dict) -> list[str]:
    raw = env.get("AINTERCEPTOR_ACTIVE_PROVIDERS", "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def build_summary(n: int) -> str:
    rows = _git_log(n)
    env = _read_env()
    active = _recent_providers(env)

    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(_classify(r["msg"]), []).append(r)

    out = []
    out.append(f"## {date.today().isoformat()} — auto-generated snapshot")
    out.append("")
    out.append(f"  Commits in view: {len(rows)}")
    if active:
        out.append(f"  Active providers: {', '.join(active)}")
    out.append("")

    order = ["feat", "fix", "docs", "test", "refactor", "perf", "chore", "other"]
    for tag in order:
        items = by_type.get(tag)
        if not items:
            continue
        out.append(f"  {tag} ({len(items)}):")
        for r in items[:5]:
            short = r["msg"][:80]
            out.append(f"    {r['sha']}  {short}")
        if len(items) > 5:
            out.append(f"    … and {len(items) - 5} more")
        out.append("")

    out.append("  Run 'git log --oneline -30' for the full list.")
    out.append("")
    out.append("---")
    out.append("")
    return "\n".join(out)


def _prepend_to_progress(block: str) -> None:
    if not PROGRESS.exists():
        PROGRESS.parent.mkdir(parents=True, exist_ok=True)
        PROGRESS.write_text(
            "# AInterceptor — Progress Report\n\n"
            "Newest entry at top. Auto-prepended by `aprogress`.\n\n",
            encoding="utf-8",
        )

    txt = PROGRESS.read_text(encoding="utf-8")
    lines = txt.splitlines(keepends=True)

    # strip any previous "auto-generated" block to avoid duplication
    import re
    txt = re.sub(
        r"## \d{4}-\d{2}-\d{2} — auto-generated snapshot\n.*?\n---\n\n",
        "", txt, count=1, flags=re.S,
    )

    # insert new block right after the header (first "## " entry)
    lines = txt.splitlines(keepends=True)
    idx = None
    for i, line in enumerate(lines):
        if line.startswith("## "):
            idx = i
            break

    if idx is None:
        new = txt.rstrip() + "\n\n" + block
    else:
        new = "".join(lines[:idx]) + block + "".join(lines[idx:])

    PROGRESS.write_text(new, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(prog="aprogress")
    ap.add_argument("--show", action="store_true",
                    help="print only; do not write")
    ap.add_argument("--commits", type=int, default=30)
    args = ap.parse_args()

    block = build_summary(args.commits)

    if args.show:
        print(block)
        return 0

    _prepend_to_progress(block)
    print(f"[OK] prepended snapshot to {PROGRESS.relative_to(ROOT)}")
    print("     preview:")
    for line in block.splitlines()[:14]:
        print("       " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
