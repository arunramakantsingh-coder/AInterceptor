import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"

# ═══════════════════════════════════════════════════════════════
# 1. Debug logging in _stream_deepseek
# ═══════════════════════════════════════════════════════════════
p = BE / "runtime" / "path_a.py"
src = p.read_text(encoding="utf-8")

# Add debug helper at top of file
if "DEBUG" not in src:
    src = src.replace(
        "import json, re, time",
        "import json, re, time, os, sys\n\nDEBUG = os.environ.get('AINTERCEPTOR_PATH_A_DEBUG') == '1'\n\ndef _dbg(*a):\n    if DEBUG:\n        print('[path_a]', *a, file=sys.stderr, flush=True)",
        1,
    )

# Instrument the deepseek streamer
old = '''    async with httpx.AsyncClient(cookies=cookies, timeout=180.0, follow_redirects=True) as c:
        async with c.stream("POST",
                            "https://chat.deepseek.com/api/v0/chat/completion",
                            headers=headers, json=body) as r:
            if r.status_code in (401, 403):
                raise PathAError(f"deepseek session expired: HTTP {r.status_code}")
            if r.status_code >= 400:
                raise PathAError(f"deepseek HTTP {r.status_code}: {await r.aread()[:200]}")
            async for line in r.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue'''

new = '''    _dbg("deepseek POST -> chat.deepseek.com/api/v0/chat/completion")
    _dbg("deepseek cookies:", list(cookies.keys()))
    _dbg("deepseek body:", body)
    raw_lines = 0
    parsed_objs = 0
    emitted = 0
    async with httpx.AsyncClient(cookies=cookies, timeout=180.0, follow_redirects=True) as c:
        async with c.stream("POST",
                            "https://chat.deepseek.com/api/v0/chat/completion",
                            headers=headers, json=body) as r:
            _dbg("deepseek HTTP status:", r.status_code)
            if r.status_code in (401, 403):
                body_txt = await r.aread()
                _dbg("deepseek 4xx body:", body_txt[:500])
                raise PathAError(f"deepseek session expired: HTTP {r.status_code}")
            if r.status_code >= 400:
                body_txt = await r.aread()
                _dbg("deepseek error body:", body_txt[:500])
                raise PathAError(f"deepseek HTTP {r.status_code}: {body_txt[:200]}")
            async for line in r.aiter_lines():
                raw_lines += 1
                if DEBUG and raw_lines <= 5:
                    _dbg(f"line {raw_lines}:", repr(line[:200]))
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                parsed_objs += 1'''

if old in src:
    src = src.replace(old, new, 1)
    print("  [OK] deepseek streamer instrumented")
else:
    print("  [!] pattern not matched")

# Add end-of-stream debug
old_end = '''                # Shape 3: bare string token
                if isinstance(obj.get("v"), str) and "p" not in obj and "o" not in obj:
                    yield obj["v"]'''

new_end = '''                # Shape 3: bare string token
                if isinstance(obj.get("v"), str) and "p" not in obj and "o" not in obj:
                    emitted += 1
                    yield obj["v"]
    _dbg(f"deepseek done: raw_lines={raw_lines} parsed_objs={parsed_objs} emitted={emitted}")'''

if old_end in src:
    src = src.replace(old_end, new_end, 1)
    print("  [OK] end-of-stream debug added")

p.write_text(src, encoding="utf-8", newline="\n")

# ═══════════════════════════════════════════════════════════════
# 2. Chat route: include error message when no deltas were emitted
# ═══════════════════════════════════════════════════════════════
c = BE / "api" / "chat_routes.py"
src = c.read_text(encoding="utf-8")

old_handler = '''    async def gen():
        try:
            async for delta in stream_reply(provider, state, prompt):
                captured["text"] += delta
                yield _openai_chunk(body.model, delta)
            yield _openai_chunk(body.model, "", "stop")
            yield "data: [DONE]\\n\\n"
        except ProviderUnavailable as e:
            captured["status"] = "provider_unavailable"
            err = {"error": {"message": str(e), "type": "provider_unavailable"}}
            yield f"data: {json.dumps(err)}\\n\\n"
            yield "data: [DONE]\\n\\n"
        except Exception as e:
            captured["status"] = "error"
            err = {"error": {"message": str(e), "type": "internal_error"}}
            yield f"data: {json.dumps(err)}\\n\\n"
            yield "data: [DONE]\\n\\n"
        finally:
            db.add(UsageEvent(
                user_id=user.id, api_key_id=key.id,
                provider=provider, model=body.model,
                tokens_in=len(prompt), tokens_out=len(captured["text"]),
                latency_ms=int((time.monotonic() - t0) * 1000),
                status=captured["status"], path="A"))
            key.last_used_at = datetime.now(timezone.utc)
            db.commit()'''

new_handler = '''    async def gen():
        delta_count = 0
        error_msg = None
        try:
            async for delta in stream_reply(provider, state, prompt):
                captured["text"] += delta
                delta_count += 1
                yield _openai_chunk(body.model, delta)
            if delta_count == 0:
                # Provider stream ended with no text — surface a diagnostic
                err = {"error": {
                    "message": f"{provider} returned no text (path A got HTTP 200 but no parsable deltas). "
                               f"Set AINTERCEPTOR_PATH_A_DEBUG=1 in .env and retry to see raw lines.",
                    "type": "empty_stream",
                }}
                yield f"data: {json.dumps(err)}\\n\\n"
                captured["status"] = "empty_stream"
            else:
                captured["status"] = "ok"
            yield _openai_chunk(body.model, "", "stop")
            yield "data: [DONE]\\n\\n"
        except ProviderUnavailable as e:
            captured["status"] = "provider_unavailable"
            err = {"error": {"message": str(e), "type": "provider_unavailable"}}
            yield f"data: {json.dumps(err)}\\n\\n"
            yield "data: [DONE]\\n\\n"
        except Exception as e:
            captured["status"] = "error"
            err = {"error": {"message": str(e), "type": "internal_error"}}
            yield f"data: {json.dumps(err)}\\n\\n"
            yield "data: [DONE]\\n\\n"
        finally:
            try:
                db.add(UsageEvent(
                    user_id=user.id, api_key_id=key.id,
                    provider=provider, model=body.model,
                    tokens_in=len(prompt), tokens_out=len(captured["text"]),
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    status=captured["status"], path="A"))
                key.last_used_at = datetime.now(timezone.utc)
                db.commit()
            except Exception:
                pass'''

if old_handler in src:
    src = src.replace(old_handler, new_handler, 1)
    c.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] chat_routes emits error when no deltas")
else:
    print("  [!] chat handler pattern not matched")

# ═══════════════════════════════════════════════════════════════
# 3. Enable debug in compose env
# ═══════════════════════════════════════════════════════════════
env_p = ROOT / ".env"
env_txt = env_p.read_text(encoding="utf-8")
if "AINTERCEPTOR_PATH_A_DEBUG" not in env_txt:
    env_txt = env_txt.rstrip() + "\nAINTERCEPTOR_PATH_A_DEBUG=1\n"
    env_p.write_text(env_txt, encoding="utf-8", newline="\n")
    print("  [OK] .env has AINTERCEPTOR_PATH_A_DEBUG=1")

dc = ROOT / "docker-compose.yml"
dc_txt = dc.read_text(encoding="utf-8")
if "AINTERCEPTOR_PATH_A_DEBUG" not in dc_txt:
    dc_txt = dc_txt.replace(
        "    environment:\n      DATABASE_URL:",
        "    environment:\n      AINTERCEPTOR_PATH_A_DEBUG: \"1\"\n      DATABASE_URL:",
        1,
    )
    dc.write_text(dc_txt, encoding="utf-8", newline="\n")
    print("  [OK] docker-compose passes AINTERCEPTOR_PATH_A_DEBUG")

# ═══════════════════════════════════════════════════════════════
# 4. Syntax + commit
# ═══════════════════════════════════════════════════════════════
import ast
for f in ["runtime/path_a.py", "api/chat_routes.py"]:
    try:
        ast.parse((BE / f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","debug(path_a): stream diagnostics + empty_stream error surfacing"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("=" * 60)
print("NEXT:")
print("  docker compose up -d --build api")
print("  (2 min)")
print()
print("Then repeat the curl:")
print("  $envFile = Get-Content .\\.env.test")
print("  $APIKEY = ($envFile | Where-Object { $_ -like 'API_KEY=*' }) -replace '^API_KEY=', ''")
print("  Set-Content body.json '{\"model\":\"deepseek\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":true}' -Encoding ascii -NoNewline")
print("  curl.exe -N -X POST http://localhost:8000/v1/chat/completions -H \"Authorization: Bearer $APIKEY\" -H \"Content-Type: application/json\" --data-binary \"@body.json\"")
print()
print("Then read the debug lines from container logs:")
print("  docker compose logs --tail=50 api | Select-String 'path_a'")
print("=" * 60)
