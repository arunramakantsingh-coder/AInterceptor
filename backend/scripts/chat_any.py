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
    print(f"Connected to {provider}. /exit or Ctrl+C to leave.\n")
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
