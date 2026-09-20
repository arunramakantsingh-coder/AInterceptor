"""AInterceptor extended admin dispatcher."""
from __future__ import annotations
import sys

from scripts import ops_read as R
from scripts import ops_sys  as S


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print("AInterceptor extended admin")
        print()
        print("  asessions [list|export <p> [path]|delete <p>]")
        print("  ahealth")
        print("  aversion")
        print("  alogs [daemon|chrome|x11vnc]")
        print("  aevidence [list|show <name>|clear [days]]")
        print("  astart | arestart | astop")
        print("  abootstrap")
        print("  asave \"message\"")
        print("  aconfig-reset <key>")
        return 0

    cmd, rest = args[0].lower(), args[1:]

    if cmd == "asessions":
        sub = rest[0].lower() if rest else "list"
        if sub in ("list", "ls", ""):
            return R.asessions_list()
        if sub == "export":
            if len(rest) < 2:
                print("usage: asessions export <provider> [path]")
                return 1
            return R.asessions_export(rest[1], rest[2] if len(rest) > 2 else None)
        if sub == "delete":
            if len(rest) < 2:
                print("usage: asessions delete <provider>")
                return 1
            return R.asessions_delete(rest[1])
        print(f"unknown subcommand: {sub}")
        return 1

    if cmd == "ahealth":    return R.ahealth()
    if cmd == "aversion":   return R.aversion()
    if cmd == "alogs":      return R.alogs(rest[0] if rest else "daemon")

    if cmd == "aevidence":
        sub = rest[0].lower() if rest else "list"
        if sub in ("list", "ls"):
            return R.aevidence_list()
        if sub == "show":
            if len(rest) < 2:
                print("usage: aevidence show <name>")
                return 1
            return R.aevidence_show(rest[1])
        if sub == "clear":
            days = int(rest[1]) if len(rest) > 1 else 30
            return R.aevidence_clear(days)
        print(f"unknown: {sub}")
        return 1

    if cmd == "astart":         return S.astart()
    if cmd == "arestart":       return S.arestart()
    if cmd == "astop":          return S.astop()
    if cmd == "abootstrap":     return S.abootstrap()
    if cmd == "asave":          return S.asave(" ".join(rest))
    if cmd == "aconfig-reset":
        if not rest:
            print("usage: aconfig-reset <key>")
            return 1
        return S.aconfig_reset(rest[0])

    print(f"unknown: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
