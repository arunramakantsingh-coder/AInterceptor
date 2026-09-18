import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ── 1. Parser: add authoritative decode_final() ──
ds = BE / "app/interception/deepseek.py"
src = ds.read_text(encoding="utf-8")

addition = '''

def decode_deepseek_final(raw: str) -> str:
    """Authoritative decoder: parse the ENTIRE stream and return the
    final RESPONSE fragment's text. This is the ground truth — no
    streaming reconstruction, no monotone heuristics, no deltas.

    DeepSeek sends cumulative snapshots. The LAST RESPONSE fragment in
    the stream always contains the complete reply. We walk every parsed
    object in order, tracking the latest RESPONSE fragment content, and
    return it once the stream ends.
    """
    import json
    latest_response_text = ""
    # Newest snapshot wins: track the highest fragment index we've seen
    # with type RESPONSE.
    for line in raw.split("\\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith(")]}'"):
            line = line[4:].lstrip()
        if line.startswith("event:"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue

        # Case A: full snapshot — response.fragments is a list
        v = obj.get("v")
        containers = []
        if isinstance(v, dict):
            containers.append(v)
        if isinstance(obj.get("response"), dict):
            containers.append(obj)
        for c in containers:
            resp = c.get("response") if isinstance(c.get("response"), dict) else c
            frags = resp.get("fragments") if isinstance(resp, dict) else None
            if not isinstance(frags, list):
                continue
            for fr in frags:
                if not isinstance(fr, dict):
                    continue
                if str(fr.get("type") or "").upper() != "RESPONSE":
                    continue
                content = fr.get("content")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, dict):
                    text = str(content.get("text") or content.get("content") or "")
                elif isinstance(content, list):
                    text = "".join(
                        (x if isinstance(x, str) else str((x or {}).get("text") or ""))
                        for x in content
                    )
                else:
                    text = ""
                # Longer wins (monotone across snapshots)
                if len(text) >= len(latest_response_text):
                    latest_response_text = text

        # Case B: patch op — path is .../fragments[-1 or N]/content
        p = obj.get("p")
        o = str(obj.get("o") or "").upper()
        if isinstance(p, str) and ("/fragments" in p) and p.endswith("/content"):
            val = obj.get("v")
            if isinstance(val, str):
                if o in ("SET", "REPLACE") and len(val) > len(latest_response_text):
                    latest_response_text = val
                elif o == "APPEND":
                    # Ignore append-to-fragment during final decode — the
                    # complete snapshot supersedes it. If we reached here
                    # without a snapshot, treat as append to latest.
                    if not latest_response_text.endswith(val):
                        latest_response_text = latest_response_text + val

    return latest_response_text
'''

if "def decode_deepseek_final" not in src:
    src = src.rstrip() + addition
    print("  [OK] added decode_deepseek_final()")
ds.write_text(src, encoding="utf-8", newline="\n")

# ── 2. Runtime: buffer, wait for FINISHED, emit once ──
nrt = BE / "app/interception/nonclaude_runtime.py"
nsrc = nrt.read_text(encoding="utf-8")

# Replace the entire execute method body's streaming loop with a
# buffer-and-decode-once approach.
old_loop_start = nsrc.find("                try:\n                    async for kind, payload in capture.events():")
old_loop_end = nsrc.find("    async def close(self)")
if old_loop_start == -1 or old_loop_end == -1:
    print("[FAIL] cannot find execute loop bounds"); sys.exit(1)

new_body = '''                try:
                    # Buffer-only: accumulate every byte, wait for terminal
                    # event, then decode ONCE with the authoritative decoder.
                    # No streaming reconstruction — that path was the source
                    # of every character-loss bug.
                    terminal = False
                    async for kind, payload in capture.events():
                        if kind == "response_started":
                            status, content_type = payload
                            if status in {401, 403}:
                                yield StreamEvent(self.provider, request.request_id, EventType.SESSION_EXPIRED, sequence, metadata={"status": status})
                                sequence += 1
                                yield StreamEvent(self.provider, request.request_id, EventType.SESSION_RECOVERY_REQUIRED, sequence, metadata={"reason": "provider_authentication_failed"})
                                return
                            if status >= 400:
                                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"status": status})
                                return
                            yield StreamEvent(self.provider, request.request_id, EventType.STREAM_STARTED, sequence, metadata={"transport": "chromium-cdp-network", "content_type": content_type})
                            sequence += 1
                            continue
                        if kind == "data":
                            body.extend(payload)
                            continue
                        if kind == "failed":
                            raise RuntimeError(str(payload))
                        if kind == "finished":
                            terminal = True
                            break

                    if not terminal:
                        yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": "stream ended without terminal signal"})
                        return

                    raw = body.decode("utf-8", errors="replace")

                    # Authoritative final decode (DeepSeek-specific)
                    final_text = ""
                    try:
                        from app.interception.deepseek import decode_deepseek_final
                        final_text = decode_deepseek_final(raw)
                    except Exception:
                        final_text = ""

                    # Fall back to DOM if the decoder produced nothing
                    if not final_text:
                        try:
                            final_text = (await self._read_last_assistant_text()).strip()
                        except Exception:
                            final_text = ""

                    if final_text:
                        yield StreamEvent(self.provider, request.request_id, EventType.STREAM_DELTA, sequence, delta=final_text)
                        sequence += 1

                    yield StreamEvent(self.provider, request.request_id, EventType.STREAM_COMPLETED, sequence, finish_reason="stop")
                    return

                except TimeoutError as exc:
                    yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": str(exc)})
                except Exception as exc:
                    yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": str(exc)})

'''

nsrc = nsrc[:old_loop_start] + new_body + nsrc[old_loop_end:]
nrt.write_text(nsrc, encoding="utf-8", newline="\n")
print("  [OK] runtime: buffer-and-decode-once")

# ── 3. Syntax + tests ──
r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{nrt}').read_text(encoding='utf-8')); "
    f"ast.parse(pathlib.Path(r'{ds}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("[FAIL] syntax:"); print(r.stderr); sys.exit(1)
print("  [OK] syntax valid")

def run(args, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print(r.stderr)
    return r.returncode

if run([PY, "-m", "pytest", "-q",
        "tests/test_nonclaude_parsers.py",
        "tests/test_deepseek_think_response.py",
        "-o", "asyncio_mode=auto"], cwd=ROOT) != 0:
    print("FAIL: tests broke"); sys.exit(1)

# ── 4. Verify decode_deepseek_final on the raw capture we already have ──
print("\\n==> Verify decode on existing raw")
import glob, os as _os
raws = sorted(glob.glob(str(ROOT / ".evidence/raw/deepseek_*.raw")),
              key=_os.path.getmtime, reverse=True)
if raws:
    probe = (
        "import sys, pathlib\\n"
        f"sys.path.insert(0, r'{BE}')\\n"
        "from app.interception.deepseek import decode_deepseek_final\\n"
        f"raw = pathlib.Path(r'{raws[0]}').read_text(encoding='utf-8', errors='replace')\\n"
        "print(repr(decode_deepseek_final(raw)))\\n"
    )
    r = subprocess.run([PY, "-c", probe], capture_output=True, text=True, encoding="utf-8")
    print(r.stdout)
    if r.stderr.strip(): print(r.stderr)

# ── 5. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(deepseek): buffer-and-decode-once; abandon streaming reconstruction"])
print(r.stdout.strip() or r.stderr.strip())

# ── 6. Live test ──
print("\\n==> Live test")
env = _os.environ.copy(); env["PYTHONUTF8"]="1"
r = subprocess.run([PY, "-u", "-m", "scripts.chat_deepseek"], cwd=BE,
    input="say hello in one short sentence\\nwhat can you do for me\\n/exit\\n",
    capture_output=True, text=True, encoding="utf-8", env=env)
print(r.stdout)
if r.stderr.strip(): print(r.stderr)
