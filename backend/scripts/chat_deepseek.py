"""Interactive DeepSeek chat through AInterceptor.

Refuses to start if CDP is not 9223, to prevent cross-chat leaks.
"""
import asyncio, os, sys, uuid, pathlib, socket

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Force CDP to DeepSeek's own browser
os.environ.pop("AINTERCEPTOR_DEEPSEEK_CDP_URL", None)  # let registry resolve

RAW = pathlib.Path("..") / ".evidence" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
os.environ["AINTERCEPTOR_RAW_CAPTURE_DIR"] = str(RAW)

from app.interception import registry as provider_registry
from app.interception.contracts import ProviderExecutionRequest
from app.interception.deepseek import DeepSeekRuntime


def _port_open(port: int) -> bool:
    s = socket.socket(); s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", port)); return True
    except OSError:
        return False
    finally:
        s.close()


async def main() -> int:
    expected = provider_registry.cdp_url("deepseek") or ""
    print(f"[AInterceptor] deepseek CDP target: {expected}")

    # Sanity: DeepSeek browser must be alive on 9223
    port = 9223
    if not _port_open(port):
        print(f"[FAIL] No Chrome listening on {port}.")
        print("       Launch DeepSeek's Chrome first:")
        print()
        print("  $c='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'")
        print("  if (!(Test-Path $c)) { $c='C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe' }")
        print("  Start-Process $c -ArgumentList '--remote-debugging-port=9223',")
        print("    '--user-data-dir=C:\\Projects\\AInterceptor-M1.5\\.ainterceptor\\chrome-profile-deepseek',")
        print("    'https://chat.deepseek.com/'")
        print()
        print("  Then log in and rerun this script.")
        return 2

    # Sanity: we must NOT attach to 9222 (Claude's browser)
    if ":9222" in expected:
        print("[FAIL] Refusing to start: CDP resolves to 9222 (Claude).")
        return 3

    rt = DeepSeekRuntime()
    await rt.start()
    print("Connected to DeepSeek Web chat context.")
    print("Type /exit or Ctrl+C to return to AIRouter.\n")

    try:
        while True:
            try:
                prompt = input("AIRouter(chat)> ")
            except (EOFError, KeyboardInterrupt):
                print(); break
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
