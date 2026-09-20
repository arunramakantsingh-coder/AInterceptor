"""AInterceptor admin ops - provider diagnostic."""
from __future__ import annotations
import pathlib, sys

_HERE = pathlib.Path(__file__).resolve()
ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))


def _read_env(path):
    d = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def provider_status(name):
    name = name.lower().strip()
    env = _read_env(ROOT / ".env")
    active = [p.strip() for p in env.get("AINTERCEPTOR_ACTIVE_PROVIDERS", "").split(",") if p.strip()]

    rows = []

    # 1. listed
    try:
        from app.providers_list import ALL_PROVIDERS
        listed = name in ALL_PROVIDERS
        rows.append(("listed in providers_list", listed, "app/providers_list.py"))
    except Exception as e:
        rows.append(("listed in providers_list", False, f"import error: {e}"))

    # 2. registry entry
    try:
        from app.interception.registry import REGISTRY
        entry = REGISTRY.get(name)
        rows.append(("registry entry", entry is not None,
                     f"home_url={entry.home_url}" if entry else "app/interception/registry.py"))
    except Exception as e:
        rows.append(("registry entry", False, f"import error: {e}"))

    # 3. runtime file
    rt = ROOT / "backend" / "app" / "interception" / f"{name}.py"
    rows.append(("runtime file", rt.exists(), str(rt.relative_to(ROOT))))

    # 4. active
    rows.append(("active in .env", name in active, "AINTERCEPTOR_ACTIVE_PROVIDERS"))

    # 5. session on disk
    sess = pathlib.Path.home() / ".ainterceptor" / "exports" / f"{name}.json"
    rows.append(("session file", sess.exists(), str(sess) if sess.exists() else "none"))

    print(f"== provider: {name} ==")
    for label, ok, detail in rows:
        mark = "OK  " if ok else "MISS"
        print(f"  [{mark}] {label:30s}  {detail}")
    print()

    # Verdict + next step
    missing = [lbl for lbl, ok, _ in rows if not ok]
    if not missing:
        print("  status: fully configured")
        print("  next:   aprobe " + name)
        return 0
    print(f"  status: incomplete ({len(missing)} gap{'s' if len(missing)!=1 else ''})")
    if "registry entry" in missing or "runtime file" in missing or "listed in providers_list" in missing:
        print(f"  next:   aproviders add {name}      (guided wizard)")
    elif "active in .env" in missing:
        print(f"  next:   aproviders enable {name}")
    elif "session file" in missing:
        print(f"  next:   alogin {name}             (VNC)")
        print(f"          airouter-agent login {name}  (agent, user machine)")
    return 0


def handle_providers_status(args):
    if not args:
        print("usage: aproviders status <name>")
        return 1
    return provider_status(args[0])


if __name__ == "__main__":
    sys.exit(handle_providers_status(sys.argv[1:]))
