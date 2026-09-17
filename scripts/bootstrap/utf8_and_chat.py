import pathlib, subprocess, sys, os, glob

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

# ── 1. Patch repro to force UTF-8 stdout/stderr at the top ──
repro = BE / "scripts/repro_deepseek_capture.py"
src = repro.read_text(encoding="utf-8")

if "sys.stdout.reconfigure" not in src:
    header = (
        "import sys, io\n"
        "try:\n"
        "    sys.stdout.reconfigure(encoding='utf-8')\n"
        "    sys.stderr.reconfigure(encoding='utf-8')\n"
        "except Exception:\n"
        "    pass\n"
    )
    # inject after the shebang / docstring / first import line
    lines = src.splitlines()
    insert_at = 0
    for i, ln in enumerate(lines):
        if ln.strip().startswith("import ") or ln.strip().startswith("from "):
            insert_at = i
            break
    lines = lines[:insert_at] + header.splitlines() + [""] + lines[insert_at:]
    repro.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("  [OK] patched repro with UTF-8 stdout")
else:
    print("  [OK] UTF-8 stdout already patched")

# ── 2. Also patch the chat harness writer we'll add now ──
chat = BE / "scripts/chat_deepseek.py"
chat.write_text('''"""Interactive DeepSeek chat through AInterceptor.

Usage:
    python -u -m scripts.chat_deepseek
"""
import asyncio, os, sys, uuid, pathlib

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

RAW = pathlib.Path("..") / ".evidence" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
os.environ["AINTERCEPTOR_RAW_CAPTURE_DIR"] = str(RAW)

from app.interception.contracts import ProviderExecutionRequest
from app.interception.deepseek import DeepSeekRuntime


async def main() -> int:
    rt = DeepSeekRuntime()
    await rt.start()
    print("Connected to DeepSeek Web chat context.")
    print("Type /exit or Ctrl+C to return to AIRouter.\\n")
    try:
        while True:
            try:
                prompt = input("AIRouter(chat)> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not prompt.strip():
                continue
            if prompt.strip() in {"/exit", "/back", "quit", "exit"}:
                break
            req = ProviderExecutionRequest(
                provider="deepseek",
                request_id=str(uuid.uuid4()),
                messages=[{"role": "user", "content": prompt}],
            )
            print("Deepseek:")
            async for ev in rt.execute(req):
                if ev.delta:
                    print(ev.delta, end="", flush=True)
            print()
    finally:
        await rt.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
''', encoding="utf-8", newline="\n")
print("  [OK] wrote backend/scripts/chat_deepseek.py")

# ── 3. Run the repro with UTF-8 forced on the CLI too ──
print("\n==> Re-running repro with UTF-8 forced")
env = os.environ.copy()
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"
r = subprocess.run(
    [PY, "-X", "utf8", "-u", "-m", "scripts.repro_deepseek_capture", "hi how are you"],
    cwd=BE, capture_output=True, text=True, encoding="utf-8", env=env,
)
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)

# ── 4. Show the raw capture ──
print("\n==> Raw capture files")
raw_files = sorted((BE.parent / ".evidence" / "raw").glob("deepseek_*.raw"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
for f in raw_files[:3]:
    print(f"  {f.stat().st_size:>8} bytes  {f}")

if raw_files:
    latest = raw_files[0]
    text = latest.read_text(encoding="utf-8", errors="replace")
    print(f"\n==> Tail of {latest.name} (last 2500 chars)")
    print(text[-2500:])

# ── 5. Commit ──
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
git(["add", "-A"])
r = git(["commit", "-m",
         "fix(scripts): force UTF-8 stdout for DeepSeek streaming on Windows"])
print("\n" + (r.stdout.strip() or r.stderr.strip()))

print("=" * 60)
print("RESULT:", "PASS" if r.returncode == 0 or "nothing to commit" in r.stdout else "REVIEW")
print("NEXT: interactive chat")
print(f"  cd backend")
print(f'  $env:PYTHONUTF8="1"; {PY} -u -m scripts.chat_deepseek')
print("=" * 60)
