"""adispatch — force a dispatcher path and trace it step by step."""
from __future__ import annotations
import argparse, asyncio, json as jsonlib, sys, time

sys.path.insert(0, "backend")

from app.db.session import SessionLocal
from app.db.models import User
from app.api.sessions_routes import load_session_state
from app.runtime import dispatcher


DEFAULT_EMAIL = "arunramakantsingh@gmail.com"


def _load_state(email, provider):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return None, "user not found"
        try:
            state = load_session_state(db, user.id, provider)
        except Exception as e:
            return None, f"load_session_state: {e}"
        return (state or {}), None
    finally:
        db.close()


async def _run(provider, prompt, force_path, email, as_json):
    state, load_err = _load_state(email, provider)
    result = {
        "provider": provider, "force_path": force_path or "auto",
        "email": email, "session_loaded": state is not None,
        "ok": False, "text": "", "error": None,
    }

    if not as_json:
        print(f"[d 0.00s] provider={provider} force_path={force_path or 'auto'}")
        if load_err:
            print(f"[d 0.00s] session_state: NOT loaded ({load_err})")
        else:
            print(f"[d 0.00s] session_state: {'loaded' if state else 'empty'} (user={email})")
        print(f"[d 0.00s] dispatch start")
        sys.stdout.flush()

    t0 = time.monotonic()
    try:
        chunks, first_at = [], None
        async for d in dispatcher.stream_reply(
            provider, state or {}, prompt, force_path=force_path
        ):
            if d:
                if first_at is None:
                    first_at = time.monotonic() - t0
                    if not as_json:
                        print(f"[d {first_at:6.2f}s] first delta")
                chunks.append(d)
                if not as_json:
                    print(d, end="", flush=True)
        elapsed = time.monotonic() - t0
        text = "".join(chunks)
        result.update(ok=True, text=text, latency_ms=int(elapsed * 1000))
        if as_json:
            print(jsonlib.dumps(result, ensure_ascii=False))
        else:
            print()
            print(f"[d {elapsed:6.2f}s] RESULT OK {len(text)} chars in {elapsed:.2f}s")
        return 0
    except Exception as e:
        elapsed = time.monotonic() - t0
        result.update(error=str(e), latency_ms=int(elapsed * 1000))
        if as_json:
            print(jsonlib.dumps(result, ensure_ascii=False))
        else:
            print()
            print(f"[d {elapsed:6.2f}s] RESULT FAIL {e}")
        return 1


def main():
    p = argparse.ArgumentParser(prog="adispatch")
    p.add_argument("provider")
    p.add_argument("prompt")
    p.add_argument("--path", choices=["auto", "a", "b", "claude"], default="auto")
    p.add_argument("--email", default=DEFAULT_EMAIL)
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    force_path = None if a.path == "auto" else a.path.upper()
    return asyncio.run(_run(a.provider.lower(), a.prompt, force_path, a.email, a.json))


if __name__ == "__main__":
    sys.exit(main())
