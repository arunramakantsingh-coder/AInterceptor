import os, pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
OUT  = ROOT / ".evidence" / "repo_tree.txt"
OUT.parent.mkdir(parents=True, exist_ok=True)

# ── 1. Full directory tree (skip noise dirs) ──
SKIP_DIRS = {
    ".git", "node_modules", ".next", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "venv", ".venv",
    ".ainterceptor",              # chrome profiles, huge
}
SKIP_SUFFIX = {".pyc", ".pyo", ".log", ".raw"}

lines = []

def walk(path: pathlib.Path, prefix: str = ""):
    try:
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except (PermissionError, OSError):
        return
    entries = [e for e in entries if e.name not in SKIP_DIRS]
    for i, e in enumerate(entries):
        last = (i == len(entries) - 1)
        branch = "└── " if last else "├── "
        lines.append(f"{prefix}{branch}{e.name}{'/' if e.is_dir() else ''}")
        if e.is_dir():
            walk(e, prefix + ("    " if last else "│   "))

lines.append(f"{ROOT.name}/")
walk(ROOT)
tree = "\n".join(lines)

OUT.write_text(tree, encoding="utf-8")
print(f"[OK] wrote {len(lines)} entries to {OUT.relative_to(ROOT)}")

# ── 2. Git status (what's tracked) ──
r = subprocess.run(["git","ls-files"], cwd=ROOT, capture_output=True, text=True)
tracked = r.stdout.strip().split("\n") if r.stdout.strip() else []
(OUT.parent / "tracked_files.txt").write_text("\n".join(tracked), encoding="utf-8")
print(f"[OK] {len(tracked)} tracked files -> .evidence/tracked_files.txt")

# ── 3. Branch + recent commits ──
r = subprocess.run(["git","branch","-a"], cwd=ROOT, capture_output=True, text=True)
(OUT.parent / "branches.txt").write_text(r.stdout, encoding="utf-8")
r = subprocess.run(["git","log","--oneline","-30"], cwd=ROOT, capture_output=True, text=True)
(OUT.parent / "recent_commits.txt").write_text(r.stdout, encoding="utf-8")
r = subprocess.run(["git","tag","--list"], cwd=ROOT, capture_output=True, text=True)
(OUT.parent / "tags.txt").write_text(r.stdout, encoding="utf-8")
print("[OK] branches, commits, tags exported")

# ── 4. Top-level breakdown (quick view) ──
print()
print("=" * 66)
print("TOP-LEVEL (depth 2)")
print("=" * 66)
root_entries = sorted([e for e in ROOT.iterdir()
                       if e.name not in SKIP_DIRS and not e.name.endswith((".pyc",))],
                      key=lambda p: (p.is_file(), p.name.lower()))
for e in root_entries:
    if e.is_file():
        print(f"  {e.name}  ({e.stat().st_size} B)")
    else:
        sub = sorted([c for c in e.iterdir()
                      if c.name not in SKIP_DIRS],
                     key=lambda p: (p.is_file(), p.name.lower()))
        print(f"  {e.name}/")
        for c in sub[:12]:
            print(f"      {c.name}{'/' if c.is_dir() else ''}")
        if len(sub) > 12:
            print(f"      ... ({len(sub) - 12} more)")

print()
print("=" * 66)
print("EXPORTED FILES (copy each into chat):")
print(f"  {OUT.relative_to(ROOT)}")
print(f"  .evidence/tracked_files.txt")
print(f"  .evidence/branches.txt")
print(f"  .evidence/recent_commits.txt")
print(f"  .evidence/tags.txt")
print("=" * 66)
print()
print("To paste into chat (opens the file):")
print(f"  cat {OUT}")
