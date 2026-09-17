
"""Run one DeepSeek round-trip with raw capture enabled.

Usage:
    python -m scripts.repro_deepseek_capture "hi how are you"
"""
import asyncio, os, pathlib, sys, uuid

RAW_DIR = pathlib.Path(".evidence/raw")
os.environ["AINTERCEPTOR_RAW_CAPTURE_DIR"] = str(RAW_DIR)

from app.interception.contracts import ProviderExecutionRequest
from app.interception.deepseek import DeepSeekRuntime

async def main() -> int:
    prompt = " ".join(sys.argv[1:]) or "hi how are you"
    rt = DeepSeekRuntime()
    req = ProviderExecutionRequest(
        provider="deepseek",
        request_id=str(uuid.uuid4()),
        messages=[{"role": "user", "content": prompt}],
    )
    await rt.start()
    print(f"REQUEST: {prompt}")
    print("-" * 60)
    emitted = ""
    try:
        async for ev in rt.execute(req):
            et = ev.event_type.value
            if ev.delta:
                emitted += ev.delta
                print(ev.delta, end="", flush=True)
            elif et in {"STREAM_STARTED","STREAM_COMPLETED","STREAM_FAILED","SESSION_EXPIRED"}:
                print(f"\n[{et}]", flush=True)
        print()
    finally:
        await rt.close()
    print("-" * 60)
    print("AIRouter emitted:")
    print(repr(emitted))
    files = sorted(RAW_DIR.glob("deepseek_*.raw"))
    if files:
        print(f"\nRAW CAPTURE: {files[-1]}  ({files[-1].stat().st_size} bytes)")
        print("Paste that file's content back.")
    else:
        print("\nWARN: no raw capture file written.")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
