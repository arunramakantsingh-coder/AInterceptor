import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"

# ── Patch ParserAdapter to dump raw bytes on request ──
pb = BE / "runtime" / "path_b.py"
src = pb.read_text(encoding="utf-8")

old = '''class ParserAdapter:
    """Base: parse(raw_bytes) returns the reconstructed text so far.

    Subclasses implement _parse(text) -> str.
    Calling parse() repeatedly with growing input must be monotone.
    """
    def __init__(self) -> None:
        self._buf = bytearray()
        self._last = ""

    def feed(self, chunk: bytes) -> str:
        if chunk:
            self._buf.extend(chunk)
        try:
            text = self._parse(bytes(self._buf))
        except Exception:
            text = self._last
        if len(text) >= len(self._last):
            self._last = text
        return self._last

    def current(self) -> str:
        return self._last

    def _parse(self, raw: bytes) -> str:            # override
        return raw.decode("utf-8", errors="replace")'''

new = '''class ParserAdapter:
    """Base: parse(raw_bytes) returns the reconstructed text so far.

    Subclasses implement _parse(text) -> str.
    Calling parse() repeatedly with growing input must be monotone.
    """
    def __init__(self) -> None:
        self._buf = bytearray()
        self._last = ""
        self._dump_requested = False

    def feed(self, chunk: bytes) -> str:
        if chunk:
            self._buf.extend(chunk)
        try:
            text = self._parse(bytes(self._buf))
        except Exception as e:
            import sys as _s
            if os.environ.get("AINTERCEPTOR_PATH_B_DEBUG") == "1":
                print(f"[parser] _parse error: {e}", file=_s.stderr, flush=True)
            text = self._last
        if len(text) >= len(self._last):
            self._last = text
        return self._last

    def dump_raw(self, provider: str) -> str:
        """Write raw bytes to .evidence/raw for inspection."""
        try:
            import datetime as _dt
            d = pathlib.Path(".evidence/raw")
            d.mkdir(parents=True, exist_ok=True)
            stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            f = d / f"{provider}_{stamp}.sse"
            f.write_bytes(bytes(self._buf))
            return str(f)
        except Exception:
            return ""

    def current(self) -> str:
        return self._last

    def _parse(self, raw: bytes) -> str:            # override
        return raw.decode("utf-8", errors="replace")'''

if old in src:
    src = src.replace(old, new, 1)
    print("  [OK] ParserAdapter now has dump_raw()")
else:
    print("  [!] ParserAdapter pattern not matched")

# Make sure `os` and `pathlib` are imported at top
if "\nimport os" not in src.split("\n\n")[0]:
    if "import pathlib" in src and "import os" not in src[:500]:
        src = src.replace("import pathlib", "import os\nimport pathlib", 1)
        print("  [OK] added import os")

# ── Patch stream_b to dump on failure ──
old_fail = '''        if emitted == 0:
            _dbg(f"{provider}: NO TEXT. parser.current()={parser.current()!r}")
            raise PathBError(f"{provider}: stream produced no text")'''

new_fail = '''        if emitted == 0:
            _dbg(f"{provider}: NO TEXT. parser.current()={parser.current()!r}")
            dump_path = parser.dump_raw(provider)
            if dump_path:
                _dbg(f"{provider}: raw bytes dumped to {dump_path}")
                # also show a preview
                try:
                    preview = bytes(parser._buf[:400]).decode("utf-8", errors="replace")
                    _dbg(f"{provider}: raw preview:\\n{preview!r}")
                except Exception:
                    pass
            raise PathBError(f"{provider}: stream produced no text")'''

if old_fail in src:
    src = src.replace(old_fail, new_fail, 1)
    print("  [OK] stream_b now dumps raw bytes on failure")
else:
    print("  [!] fail pattern not matched")

pb.write_text(src, encoding="utf-8", newline="\n")

import ast
try: ast.parse(src)
except SyntaxError as e:
    print(f"[FAIL] syntax: {e}"); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","debug(path_b): dump raw SSE bytes when parser produces no text"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("NEXT")
print()
print("  1. Daemon window: Ctrl+C then .\\run-windows.ps1")
print("  2. New window: one curl to chatgpt (as before)")
print("  3. Paste BOTH:")
print("     - the [path_b] lines from the daemon log (especially the raw preview)")
print("     - the newest file under .evidence\\raw\\")
print("=" * 60)
