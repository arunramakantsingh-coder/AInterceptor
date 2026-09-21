"""ashell — interactive Cisco-style CLI for AInterceptor.

Features:
  - Readline history (persisted to ~/.ainterceptor/cli_history)
  - Tab completion for top-level commands AND subcommands
  - '?' at start of line → list all commands by category
  - '?' at end of line → context help for that command
  - 'show <category>' → commands in that category
  - Dispatches to ~/bin/<command> via subprocess
  - 'exit' / 'quit' / Ctrl+D to leave
"""
from __future__ import annotations
import cmd
import os
import readline
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.api.command_tree import COMMAND_TREE

HIST = Path.home() / ".ainterceptor" / "cli_history"
HIST_LEN = 2000

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║  AInterceptor CLI                                            ║
║  Type ? for commands, ?<cmd> for help, Tab to complete.     ║
║  exit to leave.                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


class AirShell(cmd.Cmd):
    prompt = "AIRouter> "
    intro = BANNER

    def __init__(self):
        super().__init__()
        self._load_history()

    # ── history ────────────────────────────────────────────────
    def _load_history(self):
        try:
            HIST.parent.mkdir(parents=True, exist_ok=True)
            if HIST.exists():
                readline.read_history_file(str(HIST))
            readline.set_history_length(HIST_LEN)
        except Exception:
            pass

    def _save_history(self):
        try:
            readline.write_history_file(str(HIST))
        except Exception:
            pass

    # ── control ────────────────────────────────────────────────
    def do_exit(self, arg):
        """exit — leave the shell"""
        print()
        self._save_history()
        return True
    do_quit = do_exit
    do_q = do_exit

    def do_help(self, arg):
        """help [command] — context help"""
        self._show_help(arg.strip())

    def do_show(self, arg):
        """show [category] — list commands by category"""
        self._show_categories(arg.strip())

    def do_categories(self, arg):
        """categories — list all categories"""
        cats = sorted({n.get("category", "Other") for n in COMMAND_TREE.values()})
        print()
        for c in cats:
            print(f"  {c}")
        print()

    def emptyline(self):
        return False

    # ── dispatch ───────────────────────────────────────────────
    def default(self, line):
        s = line.strip()
        if not s:
            return
        # ? or ?<cmd> at start
        if s.startswith("?"):
            self._show_help(s[1:].strip())
            return
        # <cmd>? at end
        if s.endswith("?"):
            self._show_help(s[:-1].strip().split()[0] if s[:-1].strip() else "")
            return
        try:
            parts = shlex.split(s)
        except ValueError as e:
            print(f"[FAIL] parse error: {e}")
            return
        head = parts[0]
        node = COMMAND_TREE.get(head)
        if node is None:
            print(f"[FAIL] unknown command: {head}")
            print(f"       type ? to see all commands")
            return
        if node.get("subcommands") and len(parts) == 1:
            self._show_subcommands(head, node)
            return
        if node.get("subcommands") and len(parts) >= 2:
            sub = parts[1]
            if sub not in node["subcommands"]:
                print(f"[FAIL] unknown subcommand: {head} {sub}")
                print(f"       valid: {', '.join(sorted(node['subcommands']))}")
                return
        self._exec(line)

    def _exec(self, line):
        try:
            rc = subprocess.call(["bash", "-lc", line])
            if rc != 0:
                print(f"       [exit {rc}]")
        except KeyboardInterrupt:
            print("\n       (interrupted)")
        except Exception as e:
            print(f"[FAIL] {e}")

    # ── help renderers ─────────────────────────────────────────
    def _show_help(self, arg):
        if not arg:
            self._show_categories("")
            return
        parts = arg.split()
        node = COMMAND_TREE.get(parts[0])
        if not node:
            print(f"[FAIL] unknown command: {parts[0]}")
            return
        if len(parts) >= 2 and node.get("subcommands"):
            sub = node["subcommands"].get(parts[1])
            if not sub:
                print(f"[FAIL] unknown subcommand: {parts[0]} {parts[1]}")
                return
            self._print_detail(f"{parts[0]} {parts[1]}", sub)
            return
        self._print_detail(parts[0], node)

    def _print_detail(self, name, node):
        print()
        print(f"  {name}")
        print(f"  {'-' * len(name)}")
        print(f"  {node.get('desc', '')}")
        print()
        print(f"  Syntax:  {node.get('syntax', name)}")
        ex = node.get("examples") or []
        if ex:
            print(f"  Example{'s' if len(ex) > 1 else ''}:")
            for e in ex:
                print(f"      {e}")
        if node.get("note"):
            print()
            print(f"  Note: {node['note']}")
        if node.get("subcommands"):
            print()
            print(f"  Subcommands:")
            self._print_sub_table(node["subcommands"])
        if not node.get("built", True):
            print()
            print("  STATUS: not yet built")
        print()

    def _print_sub_table(self, subs):
        w = max((len(k) for k in subs), default=0) + 2
        for k in sorted(subs):
            v = subs[k]
            line = f"      {k.ljust(w)}{v.get('desc', '')}"
            if not v.get("built", True):
                line += "  [not yet built]"
            print(line)

    def _show_subcommands(self, name, node):
        print()
        print(f"  {name} — {node.get('desc', '')}")
        print(f"  syntax: {node.get('syntax', name)}")
        print()
        self._print_sub_table(node["subcommands"])
        print()
        print(f"  ?{name} <sub>  for detail on one subcommand")
        print()

    def _show_categories(self, want):
        cats: dict[str, list[str]] = {}
        for name, node in COMMAND_TREE.items():
            cats.setdefault(node.get("category", "Other"), []).append(name)
        for c in sorted(cats):
            if want and c.lower() != want.lower():
                continue
            print()
            print(f"  {c}")
            print(f"  {'-' * len(c)}")
            for n in sorted(cats[c]):
                nd = COMMAND_TREE[n]
                suffix = "" if nd.get("built", True) else "  [not yet built]"
                print(f"    {n.ljust(24)}{nd.get('desc', '')}{suffix}")
        print()

    # ── tab completion ─────────────────────────────────────────
    def completenames(self, text, *ignored):
        return [n for n in COMMAND_TREE if n.startswith(text)]

    def complete(self, text, state):
        try:
            line = readline.get_line_buffer()
        except Exception:
            line = ""
        buf = line.lstrip()
        if " " not in buf:
            matches = [n for n in COMMAND_TREE if n.startswith(text)]
        else:
            parts = buf.split()
            parent = COMMAND_TREE.get(parts[0], {})
            subs = parent.get("subcommands", {})
            matches = [n for n in subs if n.startswith(text)]
        try:
            return matches[state]
        except IndexError:
            return None


def main() -> int:
    binpath = str(Path.home() / "bin")
    cur = os.environ.get("PATH", "")
    if binpath not in cur.split(os.pathsep):
        os.environ["PATH"] = binpath + os.pathsep + cur

    sh = AirShell()
    try:
        sh.cmdloop()
    except KeyboardInterrupt:
        print()
        sh._save_history()
    return 0


if __name__ == "__main__":
    sys.exit(main())
