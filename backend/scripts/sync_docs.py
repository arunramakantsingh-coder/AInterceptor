"""sync_docs — parse commit-message tags, update project docs.

Tags:
  [roadmap:phase-a]   mark phase A done in PROJECT/ROADMAP.md
  [closes:B005]       move bug B005 to Resolved in PROJECT/BUGS.md
  [bug:B006]          add B006 to Open bugs if missing
  [feature:xyz]       append to .ai/FUTURE_WORK.md
  [release:v0.2.0]    create version heading in PROJECT/CHANGELOG.md

Usage:
  sync_docs --last-commit        process the most recent commit
  sync_docs --commit <sha>       process a specific commit
  sync_docs --last-commit --dry  show changes without writing
"""
from __future__ import annotations
import argparse
import pathlib
import re
import subprocess
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

ROADMAP   = ROOT / "PROJECT" / "ROADMAP.md"
BUGS      = ROOT / "PROJECT" / "BUGS.md"
KNOWN     = ROOT / ".ai" / "KNOWN_ISSUES.md"
FUTURE    = ROOT / ".ai" / "FUTURE_WORK.md"
CHANGELOG = ROOT / "PROJECT" / "CHANGELOG.md"

TAG_RE = re.compile(r"\[(roadmap|closes|bug|feature|release):([^\]]+)\]")


def _git(args: list[str]) -> str:
    r = subprocess.run(["git", "-C", str(ROOT)] + args,
                       capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else ""


def _commit_message(ref: str) -> tuple[str, str]:
    """Return (sha, full message)."""
    sha = _git(["rev-parse", ref]).strip()
    if not sha:
        return "", ""
    msg = _git(["log", "-1", "--pretty=%B", ref])
    return sha[:7], msg


def _tags(msg: str) -> list[tuple[str, str]]:
    return TAG_RE.findall(msg)


# ── doc writers ──────────────────────────────────────────────────────

def _update_roadmap(tag: str, value: str, sha: str, dry: bool) -> str:
    if not ROADMAP.exists():
        return f"[skip] {ROADMAP.name} not found"
    txt = ROADMAP.read_text(encoding="utf-8")
    # Match row: | <phase-id> | ... |
    pattern = re.compile(
        r"\|(\s*" + re.escape(value) + r"\s*)\|([^|]*)\|([^|]*)\|([^|]*)\|",
        re.IGNORECASE,
    )
    m = pattern.search(txt)
    if not m:
        return f"[skip] ROADMAP: phase '{value}' row not found"
    old_row = m.group(0)
    new_row = (
        "|" + m.group(1) + "|" +
        m.group(2).rstrip() + " |" +          # keep name
        " DONE |" +                            # status
        f" {sha} |"                            # gate
    )
    if dry:
        return f"[dry]  ROADMAP row:\n  - {old_row.strip()}\n  + {new_row.strip()}"
    txt = txt.replace(old_row, new_row, 1)
    ROADMAP.write_text(txt, encoding="utf-8")
    return f"[ok]   ROADMAP: {value} → DONE @ {sha}"


def _close_bug(bug_id: str, sha: str, dry: bool) -> str:
    if not BUGS.exists():
        return f"[skip] {BUGS.name} not found"
    txt = BUGS.read_text(encoding="utf-8")
    marker = f"| {bug_id} |"
    if marker not in txt:
        return f"[skip] BUGS: {bug_id} not found"
    row = [bug_id, "(auto)", "(auto)",
           f"closed by {sha} on {date.today().isoformat()}", "Resolved"]
    if dry:
        return f"[dry]  BUGS {bug_id} -> Resolved row {row}"
    txt, how = _append_row(txt, "## Resolved", row)
    BUGS.write_text(txt, encoding="utf-8")
    return f"[ok]   BUGS: {bug_id} -> Resolved @ {sha} ({how})"


def _add_bug(bug_id: str, sha: str, msg: str, dry: bool) -> str:
    if not BUGS.exists():
        return f"[skip] {BUGS.name} not found"
    txt = BUGS.read_text(encoding="utf-8")
    if f"| {bug_id} |" in txt:
        return f"[skip] BUGS: {bug_id} already present"
    row = [bug_id, "(auto)", "(auto)", f"opened by {sha}", "Open"]
    if dry:
        return f"[dry]  BUGS += {row}"
    txt, how = _append_row(txt, "## Open", row)
    BUGS.write_text(txt, encoding="utf-8")
    return f"[ok]   BUGS += {bug_id} ({how})"


def _add_feature(name: str, sha: str, dry: bool) -> str:
    if not FUTURE.exists():
        return f"[skip] {FUTURE.name} not found"
    txt = FUTURE.read_text(encoding="utf-8")
    if f"- [x] {name}" in txt or f"- {name} " in txt:
        return f"[skip] FUTURE: feature '{name}' already listed"
    line = f"- [x] {name} (added by {sha} on {date.today().isoformat()})"
    if dry:
        return f"[dry]  FUTURE += {line}"
    # Append to the FIRST bullet list in the file, not the end of the file
    # (the file has later "## ..." sections that are not the feature list).
    lines = txt.splitlines()
    last_bullet = None
    for i, l in enumerate(lines):
        if l.startswith("- "):
            last_bullet = i
        elif l.startswith("## ") and last_bullet is not None:
            break
    if last_bullet is None:
        out = txt.rstrip("\n") + f"\n\n## Features\n\n{line}\n"
    else:
        lines.insert(last_bullet + 1, line)
        out = "\n".join(lines) + "\n"
    FUTURE.write_text(out, encoding="utf-8")
    return f"[ok]   FUTURE += {name}"


def _release(version: str, sha: str, dry: bool) -> str:
    if not CHANGELOG.exists():
        return f"[skip] {CHANGELOG.name} not found"
    txt = CHANGELOG.read_text(encoding="utf-8")
    heading = f"## [{version}] — {date.today().isoformat()}"
    if heading in txt:
        return f"[skip] CHANGELOG: {version} already present"
    block = (
        f"{heading}\n\n"
        f"  Release commit: {sha}\n\n"
    )
    if dry:
        return f"[dry]  CHANGELOG += heading '{heading}'"
    # insert before the first "## [" line
    import re as _re
    m = _re.search(r"^## \[", txt, _re.M)
    if m:
        txt = txt[:m.start()] + block + txt[m.start():]
    else:
        txt = txt.rstrip() + "\n\n" + block
    CHANGELOG.write_text(txt, encoding="utf-8")
    return f"[ok]   CHANGELOG += {version}"


# ── main ─────────────────────────────────────────────────────────────

# Ã¢â€â‚¬Ã¢â€â‚¬ markdown table helpers Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

def _is_sep(line: str) -> bool:
    s = line.strip()
    return bool(s.startswith("|") and set(s) <= set("|-: ") and "-" in s)


def _table_rows(txt: str, heading: str) -> tuple[int, int] | None:
    """Locate the markdown table under `heading`.

    Returns (ncols, insert_line_index) or None.
    """
    lines = txt.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == heading)
    except StopIteration:
        return None
    for i in range(start + 1, len(lines)):
        if lines[i].strip().startswith("|"):
            if i + 1 < len(lines) and _is_sep(lines[i + 1]):
                ncols = len(lines[i].strip().strip("|").split("|"))
                j = i + 2
                while j < len(lines) and lines[j].strip().startswith("|"):
                    j += 1
                return ncols, j
            return None
    return None


def _append_row(txt: str, heading: str, row: list[str]) -> tuple[str, str]:
    """Append a table row under `heading`, creating the table if absent."""
    info = _table_rows(txt, heading)
    lines = txt.splitlines()
    if info is None:
        # create heading + table at end of file
        n = len(row)
        header = "| " + " | ".join(["ID"] + ["(auto)"] * (n - 1)) + " |"
        sep = "|" + "---|" * n
        out = txt.rstrip("\n") + f"\n\n{heading}\n{header}\n{sep}\n"
        out += "| " + " | ".join(row) + " |\n"
        return out, "created table"
    ncols, idx = info
    if len(row) > ncols:
        # Merge the overflow into the final column rather than truncating
        # (truncating silently discarded real data, e.g. a Status cell).
        row = row[:ncols - 1] + [" ".join(row[ncols - 1:])]
    elif len(row) < ncols:
        row = row + ["(auto)"] * (ncols - len(row))
    lines.insert(idx, "| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n", "appended row"


def process(ref: str, dry: bool) -> int:
    sha, msg = _commit_message(ref)
    if not sha:
        print(f"[FAIL] could not resolve commit: {ref}")
        return 1

    tags = _tags(msg)
    print(f"[i] commit: {sha}")
    print(f"[i] subject: {msg.splitlines()[0][:80]}")
    if not tags:
        print("[i] no recognized tags — nothing to do")
        return 0
    print(f"[i] tags: {tags}")
    print()

    failures = 0
    for kind, value in tags:
        value = value.strip()
        if kind == "roadmap":
            print(_update_roadmap(kind, value, sha, dry))
        elif kind == "closes":
            print(_close_bug(value, sha, dry))
        elif kind == "bug":
            print(_add_bug(value, sha, msg, dry))
        elif kind == "feature":
            print(_add_feature(value, sha, dry))
        elif kind == "release":
            print(_release(value, sha, dry))
        else:
            print(f"[skip] unknown tag: {kind}:{value}")
            failures += 1
        print()

    return 0 if failures == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="sync_docs")
    ap.add_argument("--last-commit", action="store_true")
    ap.add_argument("--commit", default="")
    ap.add_argument("--dry", "--dry-run", action="store_true",
                    dest="dry", help="print only; do not write")
    args = ap.parse_args()

    if args.commit:
        ref = args.commit
    elif args.last_commit:
        ref = "HEAD"
    else:
        print("usage: sync_docs --last-commit [--dry] | --commit <sha> [--dry]")
        return 1

    return process(ref, args.dry)


if __name__ == "__main__":
    sys.exit(main())
