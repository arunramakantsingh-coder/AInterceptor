"""Interactive DeepSeek chat through AInterceptor.

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
    print("Type /exit or Ctrl+C to return to AIRouter.\n")
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
