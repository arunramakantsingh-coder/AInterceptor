import pathlib, subprocess, sys, textwrap, re

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend"
TARGET = BE / "app/interception/nonclaude_runtime.py"

def run(args, cwd=ROOT):
    print(f"\n$ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=True)
    if r.stdout.strip(): print(r.stdout)
    if r.stderr.strip(): print(r.stderr)
    return r.returncode

# ---------- 1. Patch NonClaudeNetworkCapture to dump raw bytes ----------
src = TARGET.read_text(encoding="utf-8")

if "AINTERCEPTOR_RAW_CAPTURE_DIR" not in src:
    # insert import os if missing
    if "\nimport os\n" not in src:
        src = src.replace("import asyncio\n", "import asyncio\nimport os\n", 1)

    # add dump helper into class
    helper = textwrap.dedent('''
        def _raw_capture_path(self) -> str | None:
            d = os.environ.get("AINTERCEPTOR_RAW_CAPTURE_DIR")
            if not d:
                return None
            p = pathlib.Path(d)
            p.mkdir(parents=True, exist_ok=True)
            fname = f"{self.spec.provider}_{int(__import__('time').time())}.raw"
            return str(p / fname)
    ''')

    marker = "    def _on_request(self, event: dict[str, Any]) -> None:"
    src = src.replace(marker, helper + "\n" + marker, 1)

    # in _on_data, append to raw file
    old = """        try:
            payload = base64.b64decode(data)
        except Exception:
            payload = str(data).encode("utf-8", errors="replace")
        self._queue.put_nowait(("data", payload))"""
    new = """        try:
            payload = base64.b64decode(data)
        except Exception:
            payload = str(data).encode("utf-8", errors="replace")
        raw_path = getattr(self, "_raw_path", None)
        if raw_path is None:
            raw_path = self._raw_capture_path()
            self._raw_path = raw_path
        if raw_path:
            with open(raw_path, "ab") as fh:
                fh.write(payload)
        self._queue.put_nowait(("data", payload))"""
    if old in src:
        src = src.replace(old, new, 1)
        print("[OK] patched _on_data to dump raw bytes")
    else:
        print("[WARN] _on_data pattern not found — inspect file manually")

    TARGET.write_text(src, encoding="utf-8")
else:
    print("[OK] raw capture patch already present")

# ---------- 2. Write a repro harness ----------
harness = textwrap.dedent('''
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
                    print(f"\\n[{et}]", flush=True)
            print()
        finally:
            await rt.close()
        print("-" * 60)
        print("AIRouter emitted:")
        print(repr(emitted))
        files = sorted(RAW_DIR.glob("deepseek_*.raw"))
        if files:
            print(f"\\nRAW CAPTURE: {files[-1]}  ({files[-1].stat().st_size} bytes)")
            print("Paste that file's content back.")
        else:
            print("\\nWARN: no raw capture file written.")
        return 0

    if __name__ == "__main__":
        sys.exit(asyncio.run(main()))
''')

hpath = BE / "scripts/repro_deepseek_capture.py"
hpath.write_text(harness, encoding="utf-8")
print(f"[OK] wrote {hpath.relative_to(ROOT)}")

# ---------- 3. Commit the capture-enabled instrumentation ----------
subprocess.run(["git","add","-A"], cwd=ROOT)
msg = ("feat(deepseek): raw CDP capture for parser ground truth\n\n"
       "- NonClaudeNetworkCapture dumps raw bytes when AINTERCEPTOR_RAW_CAPTURE_DIR set\n"
       "- backend/scripts/repro_deepseek_capture.py runs one real round-trip\n"
       "- no parser change, no transport change")
r = subprocess.run(["git","commit","-m",msg], cwd=ROOT, capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())

print("=" * 60)
print("NEXT — reproduce the failing case with capture on:")
print()
print('  cd C:\\Projects\\AInterceptor-M1.5\\backend')
print('  .\\.venv\\Scripts\\Activate.ps1')
print('  python -m scripts.repro_deepseek_capture "hi how are you"')
print()
print("Then paste:")
print("  1. the AIRouter output lines")
print("  2. the content of the newest .evidence/raw/deepseek_*.raw file")
print("  3. the EXACT reply the browser showed")
print("=" * 60)
