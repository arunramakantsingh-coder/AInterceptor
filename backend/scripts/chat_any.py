"""Generic AI chat launcher.

Usage:
    python -m scripts.chat_any <provider>
"""
import asyncio, importlib, os, sys, uuid, pathlib, inspect

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
    """Find a Runtime class in app.interception.<provider>, case-insensitive."""
    module = importlib.import_module(f"app.interception.{provider}")
    target = provider.replace("-", "").lower()
    candidates = []
    for name, obj in vars(module).items():
        if not isinstance(obj, type):
            continue
        if obj.__module__ != module.__name__:
            continue
        lname = name.lower()
        if lname == f"{target}runtime":
            return obj
        if lname.endswith("runtime"):
            candidates.append(obj)
    if candidates:
        return candidates[0]
    raise RuntimeError(
        f"no Runtime class in app.interception.{provider}; "
        f"found: {[n for n in vars(module) if isinstance(vars(module)[n], type)]}"
    )


def _instantiate(cls, provider):
    sig = inspect.signature(cls.__init__)
    params = list(sig.parameters.values())
    # Drop self
    params = params[1:]
    kwargs = {}
    for p in params:
        if p.name == "provider":
            kwargs["provider"] = provider
        # everything else: rely on defaults
    try:
        return cls(**kwargs)
    except TypeError:
        return cls()


async def main() -> int:
    if len(sys.argv) < 2:
        print("usage: chat_any <provider>  (deepseek|claude|chatgpt|gemini)")
        return 1
    provider = sys.argv[1].lower()
    try:
        RuntimeClass = _load_runtime(provider)
    except Exception as e:
        print(f"[FAIL] {e}")
        return 2

    try:
        rt = _instantiate(RuntimeClass, provider)
    except Exception as e:
        print(f"[FAIL] cannot instantiate {RuntimeClass.__name__}: {e}")
        return 3

    await rt.start()
    print(f"Connected to {provider}. /exit or Ctrl+C to leave.\n")
    prompt_prefix = f"{provider}> "
    try:
        while True:
            try:
                line = input(prompt_prefix)
            except (EOFError, KeyboardInterrupt):
                print(); break
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
