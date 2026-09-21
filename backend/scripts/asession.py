"""asession — append a decision to .ai/SESSION_LOG.md.

Usage:
  asession                     interactive prompts
  asession "title"             only title, body from prompts
  asession --quick "title" "chosen" "why"
"""
from __future__ import annotations
import argparse
import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
LOG = ROOT / ".ai" / "SESSION_LOG.md"


def _ask(prompt: str, default: str = "") -> str:
    try:
        v = input(prompt + (f" [{default}]: " if default else ": ")).strip()
    except EOFError:
        return default
    return v or default


def _prepend_entry(title: str, context: str, options: str, chosen: str,
                   why: str, drift: str, impact: str) -> None:
    today = date.today().isoformat()
    entry = (
        f"## {today} — {title}\n\n"
        f"  Context: {context or 'n/a'}\n"
        f"  Options: {options or 'n/a'}\n"
        f"  Chosen:  {chosen}\n"
        f"  Why:     {why or 'n/a'}\n"
        f"  Drift:   {drift or 'none'}\n"
        f"  Impact:  {impact or 'n/a'}\n\n"
        "---\n\n"
    )

    if not LOG.exists():
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text("# AInterceptor — Session Log\n\n", encoding="utf-8")

    txt = LOG.read_text(encoding="utf-8")
    lines = txt.splitlines(keepends=True)

    # find the first "## " line (newest entry)
    idx = None
    for i, line in enumerate(lines):
        if line.startswith("## "):
            idx = i
            break

    if idx is None:
        new = txt.rstrip() + "\n\n" + entry
    else:
        new = "".join(lines[:idx]) + entry + "".join(lines[idx:])

    LOG.write_text(new, encoding="utf-8")
    print(f"[OK] appended to {LOG.relative_to(ROOT)}")
    print(f"     title: {title}")


def main() -> int:
    ap = argparse.ArgumentParser(prog="asession")
    ap.add_argument("title", nargs="?", help="decision title")
    ap.add_argument("--quick", action="store_true",
                    help="non-interactive: title, chosen, why")
    ap.add_argument("args", nargs="*", help="for --quick: chosen why")
    parsed = ap.parse_args()

    if parsed.quick:
        if not parsed.title:
            print("usage: asession --quick \"title\" \"chosen\" \"why\"")
            return 1
        rest = list(parsed.args) if hasattr(parsed, "args") else []
        chosen = rest[0] if len(rest) > 0 else ""
        why = rest[1] if len(rest) > 1 else ""
        _prepend_entry(parsed.title, "", "", chosen, why, "", "")
        return 0

    title = parsed.title
    if not title:
        title = _ask("Title")
        if not title:
            print("[FAIL] title is required")
            return 1

    print("(leave blank to skip any field)")
    context = _ask("Context (why this came up)")
    options = _ask("Options (a/b/c...)")
    chosen  = _ask("Chosen")
    why     = _ask("Why (one sentence)")
    drift   = _ask("Drift (what changed vs earlier plan)")
    impact  = _ask("Impact (files / phases)")

    if not chosen:
        print("[FAIL] 'Chosen' is required")
        return 1

    _prepend_entry(title, context, options, chosen, why, drift, impact)
    return 0


if __name__ == "__main__":
    sys.exit(main())
