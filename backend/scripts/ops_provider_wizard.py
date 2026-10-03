"""AInterceptor provider wizard: add / remove."""
from __future__ import annotations
import argparse
import pathlib
import re
import sys

_HERE = pathlib.Path(__file__).resolve()
ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))


def _ask(prompt, default=None):
    if default is not None:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "
    try:
        v = input(prompt).strip()
    except EOFError:
        return default
    if not v and default is not None:
        return default
    return v


def _ask_yes_no(prompt, default=True):
    suffix = " [Y/n]: " if default else " [y/N]: "
    try:
        v = input(prompt + suffix).strip().lower()
    except EOFError:
        return default
    if not v:
        return default
    return v in ("y", "yes")


def _add_to_providers_list(name):
    pl = ROOT / "backend" / "app" / "providers_list.py"
    src = pl.read_text()
    if f'"{name}"' in src:
        print(f"  [SKIP] {name} already in providers_list")
        return True
    m = re.search(r'ALL_PROVIDERS: list\[str\] = \[(.*?)\]', src, re.S)
    if not m:
        print("  [FAIL] ALL_PROVIDERS pattern not found")
        return False
    body = m.group(1).rstrip()
    if not body.endswith(","):
        body += ","
    body += '\n    "' + name + '",\n'
    src = src[:m.start(1)] + body + src[m.end(1):]
    pl.write_text(src)
    print(f"  [OK] added {name} to providers_list.py")
    return True


def _add_to_registry(name, home_url, tab_prefix, login_markers, composer_selectors):
    reg = ROOT / "backend" / "app" / "interception" / "registry.py"
    src = reg.read_text()
    if f'"{name}": ProviderEntry(' in src:
        print(f"  [SKIP] {name} already in registry")
        return True

    entry_lines = [
        f'    "{name}": ProviderEntry(',
        f'        name="{name}",',
        f'        home_url="{home_url}",',
        f'        tab_url_prefix="{tab_prefix}",',
        f'        default_model="{name}-web",',
        f'        composer_selectors={composer_selectors!r},',
        f'        login_markers={login_markers!r},',
        f'        response_markers=(),',
        f'        request_markers=(),',
        f'    ),',
        '',
    ]
    entry = "\n".join(entry_lines)

    marker = "REGISTRY: dict[str, ProviderEntry] = {"
    idx = src.find(marker)
    if idx == -1:
        print("  [FAIL] REGISTRY dict marker not found")
        return False
    insert_at = src.find("\n", idx) + 1
    src = src[:insert_at] + entry + src[insert_at:]
    reg.write_text(src)
    print(f"  [OK] added {name} to registry.py")
    return True


def _scaffold_runtime(name):
    rt = ROOT / "backend" / "app" / "interception" / f"{name}.py"
    if rt.exists():
        print(f"  [SKIP] {rt.relative_to(ROOT)} already exists")
        return True
    cls_name = "".join(p.title() for p in name.split("_")) + "Runtime"
    tmpl = (
        '"""' + name + ' runtime (scaffold - fill in TODO markers)."""\n'
        'from __future__ import annotations\n\n'
        'from app.interception.nonclaude_runtime import NonClaudeWebRuntime\n'
        'from app.interception.web_runtime import WebProviderSpec\n\n\n'
        'class ' + cls_name + '(NonClaudeWebRuntime):\n'
        '    provider = "' + name + '"\n\n'
        '    spec = WebProviderSpec(\n'
        '        name="' + name + '",\n'
        '        composer_selectors=(\n'
        '            \'div[contenteditable="true"]\',\n'
        '            "textarea",\n'
        '        ),\n'
        '        send_button_selectors=(\n'
        '            \'button[type="submit"]\',\n'
        '            \'button[aria-label*="Send"]\',\n'
        '        ),\n'
        '        response_container_selectors=(\n'
        '            \'div[data-message-author-role="assistant"]\',\n'
        '            \'div[class*="response"]\',\n'
        '        ),\n'
        '        stop_button_selectors=(\n'
        '            \'button[aria-label*="Stop"]\',\n'
        '        ),\n'
        '    )\n\n'
        '    # TODO: provider-specific streaming if not SSE\n'
    )
    rt.write_text(tmpl, encoding="utf-8")
    print(f"  [OK] scaffolded {rt.relative_to(ROOT)}")
    return True


def _enable_in_env(name):
    env_file = ROOT / ".env"
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    out, found = [], False
    for line in lines:
        if line.startswith("AINTERCEPTOR_ACTIVE_PROVIDERS="):
            current = line.split("=", 1)[1].strip()
            parts = [p.strip() for p in current.split(",") if p.strip()]
            if name not in parts:
                parts.append(name)
            out.append("AINTERCEPTOR_ACTIVE_PROVIDERS=" + ",".join(parts))
            found = True
        else:
            out.append(line)
    if not found:
        out.append("AINTERCEPTOR_ACTIVE_PROVIDERS=" + name)
    env_file.write_text("\n".join(out) + "\n")
    print(f"  [OK] added {name} to AINTERCEPTOR_ACTIVE_PROVIDERS")


def add_provider(name, interactive=True, home_url=None, tab_prefix=None,
                 login_markers=None, composer_selectors=None, activate=True):
    name = name.lower().strip()
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        print(f"[FAIL] invalid name (a-z, 0-9, _): {name}")
        return 1

    print(f"== add provider: {name} ==")
    print()

    if interactive and not home_url:
        home_url = _ask("Home URL", default=f"https://{name}.com/")
        tab_prefix = _ask("Tab URL prefix", default=f"{name}.com")
        lm_raw = _ask("Login markers (comma-sep)", default="/login,/signin")
        login_markers = tuple(m.strip() for m in lm_raw.split(",") if m.strip())
        cs_raw = _ask("Composer selectors (comma-sep)",
                      default='div[contenteditable="true"],textarea')
        composer_selectors = tuple(s.strip() for s in cs_raw.split(",") if s.strip())
        activate = _ask_yes_no("Activate now?", default=True)
    else:
        home_url = home_url or f"https://{name}.com/"
        tab_prefix = tab_prefix or f"{name}.com"
        login_markers = login_markers or ("/login", "/signin")
        composer_selectors = composer_selectors or ('div[contenteditable="true"]', "textarea")

    print("Summary:")
    print(f"  name:               {name}")
    print(f"  home_url:           {home_url}")
    print(f"  tab_prefix:         {tab_prefix}")
    print(f"  login_markers:      {login_markers}")
    print(f"  composer_selectors: {composer_selectors}")
    print(f"  activate:           {activate}")
    if interactive and not _ask_yes_no("Proceed?", default=True):
        print("aborted")
        return 1

    ok = True
    ok &= _add_to_providers_list(name)
    ok &= _add_to_registry(name, home_url, tab_prefix, login_markers, composer_selectors)
    ok &= _scaffold_runtime(name)
    if activate:
        _enable_in_env(name)

    print()
    if ok:
        print(f"[OK] provider {name} added")
        print()
        print("Next steps:")
        print(f"  1. Edit backend/app/interception/{name}.py - fill TODO markers")
        print(f"  2. arestart")
        if activate:
            print(f"  3. alogin {name}      (VNC login)")
        print(f"  4. aproviders validate {name}")
        return 0
    print("[FAIL] one or more steps failed")
    return 1


def remove_provider(name, interactive=True, yes=False):
    name = name.lower().strip()
    print(f"== remove provider: {name} ==")
    print("Removes from AINTERCEPTOR_ACTIVE_PROVIDERS only.")
    print("Does NOT delete runtime file, registry entry, or providers_list entry.")
    if interactive and not yes:
        if not _ask_yes_no("Proceed?", default=False):
            print("aborted")
            return 1

    env_file = ROOT / ".env"
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    out, changed = [], False
    for line in lines:
        if line.startswith("AINTERCEPTOR_ACTIVE_PROVIDERS="):
            parts = [p.strip() for p in line.split("=", 1)[1].split(",") if p.strip()]
            new = [p for p in parts if p != name]
            if new != parts:
                changed = True
            out.append("AINTERCEPTOR_ACTIVE_PROVIDERS=" + ",".join(new))
        else:
            out.append(line)
    env_file.write_text("\n".join(out) + "\n")
    print(f"[OK] deactivated {name}" if changed else f"[i] {name} was not active")
    print()
    print("Manual cleanup (optional):")
    print(f"  git rm backend/app/interception/{name}.py")
    print("  # edit registry.py and providers_list.py to remove the entry")
    print()
    print("restart daemon:  arestart")
    return 0


def main():
    p = argparse.ArgumentParser(prog="provider_wizard")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("add")
    pa.add_argument("name")
    pa.add_argument("--url")
    pa.add_argument("--tab-prefix")
    pa.add_argument("--login-markers")
    pa.add_argument("--composer-selectors")
    pa.add_argument("--no-activate", action="store_true")
    pa.add_argument("--yes", action="store_true")

    pr = sub.add_parser("remove")
    pr.add_argument("name")
    pr.add_argument("--yes", action="store_true")

    args = p.parse_args()
    if args.cmd == "add":
        lm = tuple(m.strip() for m in args.login_markers.split(",")) if args.login_markers else None
        cs = tuple(s.strip() for s in args.composer_selectors.split(",")) if args.composer_selectors else None
        return add_provider(args.name, interactive=not args.yes,
                            home_url=args.url, tab_prefix=args.tab_prefix,
                            login_markers=lm, composer_selectors=cs,
                            activate=not args.no_activate)
    if args.cmd == "remove":
        return remove_provider(args.name, interactive=not args.yes, yes=args.yes)
    return 1


if __name__ == "__main__":
    sys.exit(main())
