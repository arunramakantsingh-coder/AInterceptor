import pathlib, subprocess, sys, os, textwrap

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ───────────────────────────────────────────────────────────
# 1. Generic launcher: backend/scripts/chat_any.py
# ───────────────────────────────────────────────────────────
chat_any = textwrap.dedent('''\
    """Generic AI chat launcher.

    Usage:
        python -m scripts.chat_any <provider>

    Provider examples: deepseek, claude, chatgpt, gemini.
    Shows a <provider>> prompt, streams replies directly.
    """
    import asyncio, importlib, os, sys, uuid, pathlib

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    RAW = pathlib.Path("..") / ".evidence" / "raw"
    RAW.mkdir(parents=True, exist_ok=True)
    os.environ["AINTERCEPTOR_RAW_CAPTURE_DIR"] = str(RAW)

    from app.interception.contracts import ProviderExecutionRequest

    def _load_runtime(provider: str):
        module = importlib.import_module(f"app.interception.{provider}")
        for name in (provider.capitalize() + "Runtime",
                     provider.title() + "Runtime",
                     "Runtime"):
            cls = getattr(module, name, None)
            if cls is not None:
                return cls
        raise RuntimeError(f"no runtime class found in app.interception.{provider}")

    async def main() -> int:
        if len(sys.argv) < 2:
            print("usage: chat_any <provider>  (deepseek|claude|chatgpt|gemini)")
            return 1
        provider = sys.argv[1].lower()
        try:
            RuntimeClass = _load_runtime(provider)
        except Exception as e:
            print(f"[FAIL] cannot load runtime for {provider}: {e}")
            return 2

        try:
            rt = RuntimeClass()
        except TypeError:
            rt = RuntimeClass(provider=provider)

        await rt.start()
        prompt_prefix = f"{provider}> "
        print(f"Connected to {provider}. /exit or Ctrl+C to leave.\\n")
        try:
            while True:
                try:
                    line = input(prompt_prefix)
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not line.strip():
                    continue
                if line.strip() in {"/exit", "/back", "exit", "quit"}:
                    break
                req = ProviderExecutionRequest(
                    provider=provider,
                    request_id=str(uuid.uuid4()),
                    messages=[{"role": "user", "content": line}],
                )
                print()
                async for ev in rt.execute(req):
                    if ev.delta:
                        print(ev.delta, end="", flush=True)
                print()
        finally:
            await rt.close()
        return 0

    if __name__ == "__main__":
        sys.exit(asyncio.run(main()))
''')

(BE / "scripts" / "chat_any.py").write_text(chat_any, encoding="utf-8", newline="\n")
print("  [OK] backend/scripts/chat_any.py")

# ───────────────────────────────────────────────────────────
# 2. .cmd wrappers in a bin/ directory
# ───────────────────────────────────────────────────────────
BIN = ROOT / "bin"
BIN.mkdir(exist_ok=True)

PROVIDERS = ["deepseek", "claude", "chatgpt", "gemini"]

for p in PROVIDERS:
    cmd = (
        "@echo off\r\n"
        "set PYTHONUTF8=1\r\n"
        f"cd /d \"{BE}\"\r\n"
        f"\"{PY}\" -u -m scripts.chat_any {p}\r\n"
    )
    (BIN / f"{p}.cmd").write_text(cmd, encoding="utf-8", newline="")
    print(f"  [OK] bin/{p}.cmd")

# also a generic `ai` command
(BIN / "ai.cmd").write_text(
    "@echo off\r\n"
    "set PYTHONUTF8=1\r\n"
    f"cd /d \"{BE}\"\r\n"
    f"\"{PY}\" -u -m scripts.chat_any %*\r\n",
    encoding="utf-8", newline="",
)
print("  [OK] bin/ai.cmd")

# ───────────────────────────────────────────────────────────
# 3. Add bin/ to USER PATH (idempotent)
# ───────────────────────────────────────────────────────────
ps_add_path = f'''
$binPath = "{BIN}"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$binPath*") {{
    [Environment]::SetEnvironmentVariable("Path", $userPath + ";" + $binPath, "User")
    Write-Host "added $binPath to USER PATH (open a new terminal to use it)"
}} else {{
    Write-Host "$binPath already on USER PATH"
}}
'''
r = subprocess.run(["powershell", "-NoProfile", "-Command", ps_add_path],
                   capture_output=True, text=True, shell=True)
print(r.stdout.strip())
if r.stderr.strip(): print("  ", r.stderr.strip())

# ───────────────────────────────────────────────────────────
# 4. Commit
# ───────────────────────────────────────────────────────────
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "feat(cli): chat_any launcher + per-provider .cmd shortcuts (deepseek, claude, chatgpt, gemini)"])
print(r.stdout.strip() or r.stderr.strip())

print()
print("=" * 66)
print("DONE")
print()
print("Open a NEW PowerShell window, then simply type:")
print("    deepseek")
print("    claude")
print("    chatgpt")
print("    gemini")
print()
print("Each opens a REPL with that provider. Example:")
print("    PS> deepseek")
print("    Connected to deepseek. /exit or Ctrl+C to leave.")
print("    deepseek> hi how are you")
print("    <reply>")
print("    deepseek> /exit")
print()
print("If the commands are not found, run this once in the current shell:")
print(f'    $env:Path += ";{BIN}"')
print("=" * 66)
