import pathlib, subprocess, sys, textwrap

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
BIN  = ROOT / "bin"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ── Rewrite chat_any.py cleanly. Fewer moving parts. ──
chat = textwrap.dedent('''\
    """Chat CLI — talks to aidaemon at http://127.0.0.1:7700."""
    import asyncio, json, os, sys, pathlib, urllib.request, urllib.error

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    DAEMON = "http://127.0.0.1:7700"

    def http_get(path, timeout=2.0):
        with urllib.request.urlopen(DAEMON + path, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")

    def http_post(path, timeout=30.0):
        req = urllib.request.Request(DAEMON + path, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")

    def daemon_alive():
        try:
            http_get("/", timeout=1.0)
            return True
        except Exception:
            return False

    SUBCOMMANDS = {"login", "show", "hide", "status"}


    def dispatch(args):
        """Return (action, provider) or (None, None)."""
        if not args:
            return None, None
        a0 = args[0].lower()
        # verb-first: daemon login deepseek
        if a0 in SUBCOMMANDS:
            if a0 == "status":
                return "status", None
            if len(args) < 2:
                print(f"usage: {a0} <provider>")
                return "help", None
            return a0, args[1].lower()
        # provider-first: deepseek [login|show|hide]
        provider = a0
        if len(args) > 1 and args[1].lower() in SUBCOMMANDS:
            return args[1].lower(), provider
        return "chat", provider


    def do_status():
        if not daemon_alive():
            print("aidaemon  ●  not running")
            return 1
        with urllib.request.urlopen(DAEMON + "/", timeout=2) as r:
            import json as _j
            data = _j.loads(r.read())
        print("aidaemon  ●  running")
        print()
        print(f"  {'PROVIDER':<10} {'PORT':<6} {'BROWSER':<10} {'ATTACHED':<10}")
        print("  " + "-" * 40)
        for name, cfg in data["providers"].items():
            b = "alive" if cfg["chrome_alive"] else "off"
            a = "yes" if cfg["attached"] else "no"
            print(f"  {name:<10} {cfg['port']:<6} {b:<10} {a:<10}")
        return 0


    async def do_chat(provider):
        if not daemon_alive():
            print("[FAIL] aidaemon is not running.")
            print("       Start it with:  aidaemon start")
            print("       Then retry:     " + provider)
            return 2
        print(f"Connected to {provider} (daemon). /exit or Ctrl+C to leave.\\n")
        while True:
            try:
                line = input(f"{provider}> ")
            except (EOFError, KeyboardInterrupt):
                print(); break
            if not line.strip(): continue
            if line.strip() in {"/exit","/back","exit","quit"}: break

            body = json.dumps({"prompt": line}).encode()
            req = urllib.request.Request(
                f"{DAEMON}/chat/{provider}",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            print()
            try:
                with urllib.request.urlopen(req, timeout=240) as resp:
                    buf = b""
                    for chunk in resp:
                        buf += chunk
                        while b"\\n\\n" in buf:
                            ev, buf = buf.split(b"\\n\\n", 1)
                            for ln in ev.split(b"\\n"):
                                if not ln.startswith(b"data: "): continue
                                payload = ln[6:].decode("utf-8","replace")
                                if payload == "[DONE]": break
                                try:
                                    j = json.loads(payload)
                                    if "delta" in j:
                                        print(j["delta"], end="", flush=True)
                                    elif "error" in j:
                                        print(f"\\n[ERROR] {j['error']}")
                                except Exception:
                                    pass
            except Exception as e:
                print(f"[FAIL] {e}")
            print()
        return 0


    def main():
        action, provider = dispatch(sys.argv[1:])
        if action is None or action == "help":
            print("usage: <provider> [login|show|hide]")
            print("       login|show|hide|status <provider>")
            return 1
        if action == "status":
            return do_status()

        if action in {"login","show","hide"}:
            if not daemon_alive():
                print("[FAIL] aidaemon is not running.")
                print(f"       Start it with:  aidaemon start")
                print(f"       Then retry:     {action} {provider}")
                return 2
            try:
                print(http_post(f"/{action}/{provider}", timeout=60))
            except Exception as e:
                print(f"[FAIL] {e}")
            return 0

        if action == "chat":
            return asyncio.run(do_chat(provider))
        return 1


    if __name__ == "__main__":
        sys.exit(main())
''')

(BE / "scripts" / "chat_any.py").write_text(chat, encoding="utf-8", newline="\n")
print("  [OK] chat_any.py rewritten (no local fallback)")

# syntax
import ast
try: ast.parse(chat)
except SyntaxError as e:
    print("[FAIL]", e); sys.exit(1)
print("  [OK] syntax valid")

# Commit
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(cli): clean daemon-only chat_any; correct subcommand dispatch"])
print(r.stdout.strip() or r.stderr.strip())

# Test daemon health
import urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:7700/", timeout=2) as r:
        print("\n  [OK] daemon reachable:", r.status)
except Exception as e:
    print("\n  [!] daemon not reachable:", e)
    print("       Run: aidaemon start")

print()
print("=" * 60)
print("NOW TRY:")
print("  aidaemon status")
print("  deepseek login")
print("  deepseek")
print("=" * 60)
