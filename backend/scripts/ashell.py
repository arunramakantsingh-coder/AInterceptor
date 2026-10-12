"""ashell - interactive Cisco IOS/Nexus-style CLI for AInterceptor.

Features:
  - Readline history (persisted to ~/.ainterceptor/cli_history)
  - TAB completion at any depth: commands, subcommands and argument
    values (provider names, log names, key ids, commit shas)
  - '?' at the cursor shows the valid NEXT tokens (IOS-style), filtered
    by what has already been typed
  - '?' alone lists all commands by category; '?<cmd>' details one
  - 'show <category>' filters by category, 'categories' lists them
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
from app.api.command_tree import COMMAND_TREE, args_for, categories

HIST = Path.home() / ".ainterceptor" / "cli_history"
HIST_LEN = 2000

BANNER = """
+--------------------------------------------------------------+
|  AInterceptor CLI                                            |
|  ? for commands, <cmd> ? for the next token, Tab to complete.|
|  exit to leave.                                              |
+--------------------------------------------------------------+
"""


# â”€â”€ dynamic value sources â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def provider_names() -> list[str]:
    """Live provider catalog (falls back to the static tree list)."""
    try:
        from app.control_plane.state import ALL_KNOWN
        return sorted(ALL_KNOWN)
    except Exception:
        return []


def recent_shas(limit: int = 20) -> list[str]:
    try:
        r = subprocess.run(["git", "-C", str(Path(__file__).resolve().parents[2]),
                            "log", "--format=%h", f"-{limit}"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.split()
    except Exception:
        return []


def values_for(spec: dict) -> list[str]:
    t = spec.get("type")
    if t == "provider":
        return provider_names()
    if t == "choice":
        return list(spec.get("choices") or [])
    if t == "sha":
        return recent_shas()
    return []


# â”€â”€ completion engine (shared by TAB and ?) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def valid_next(cmd: str, sub: str | None, partial: str) -> list[tuple[str, str]]:
    """Return [(value, description)] valid for the next token.

    Cisco behaviour: at the command position offer commands; at the
    subcommand position offer subcommands; at an argument position offer
    the declared values for that argument.
    """
    out: list[tuple[str, str]] = []

    if cmd is None:
        for name, node in COMMAND_TREE.items():
            if name.startswith(partial):
                out.append((name, node.get("desc", "")))
        return out

    node = COMMAND_TREE.get(cmd) or {}
    subs = node.get("subcommands") or {}

    if sub is None and subs:
        for sn, sv in subs.items():
            if sn.startswith(partial):
                out.append((sn, sv.get("desc", "")))
        return out

    args = args_for(cmd, sub)
    for spec in args.values():
        for v in values_for(spec):
            if v.startswith(partial):
                out.append((v, spec.get("desc", "")))
    return out


class AirShell(cmd.Cmd):
    prompt = "AIRouter> "
    intro = BANNER

    def __init__(self):
        super().__init__()
        self._load_history()
        readline.set_completer_delims(" \t")
        readline.parse_and_bind("tab: complete")
        readline.set_completer(self.complete_cisco)

    # â”€â”€ state parse â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _state(self, line: str):
        """Parse the line before the cursor -> (cmd, sub, partial)."""
        toks = line.split()
        if not toks:
            return None, None, ""
        trailing_space = line.endswith(" ")
        if len(toks) == 1 and not trailing_space:
            return None, None, toks[0]
        cmd = toks[0]
        node = COMMAND_TREE.get(cmd) or {}
        subs = node.get("subcommands") or {}
        if len(toks) == 1 and trailing_space:
            return cmd, None, ""
        if len(toks) >= 2:
            if subs:
                if toks[1] in subs:
                    sub = toks[1]
                    partial = toks[-1] if not trailing_space else ""
                    if len(toks) == 2 and not trailing_space:
                        # completing the subcommand itself
                        return cmd, None, toks[1]
                    return cmd, sub, partial
                # still completing the subcommand token
                return cmd, None, (toks[1] if not trailing_space else "")
            partial = toks[-1] if not trailing_space else ""
            return cmd, None, partial
        return cmd, None, ""

    # â”€â”€ TAB â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def complete_cisco(self, text, state):
        line = readline.get_line_buffer()[:readline.get_endidx()]
        cmd, sub, partial = self._state(line)
        matches = [v for v, _ in valid_next(cmd, sub, partial)]
        if state == 0:
            self._tab_matches = matches
        try:
            return matches[state]
        except IndexError:
            return None

    # â”€â”€ readline history â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ control â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def do_exit(self, arg):
        """exit - leave the shell"""
        print()
        self._save_history()
        return True
    do_quit = do_exit
    do_q = do_exit

    def do_help(self, arg):
        """help [command] - context help"""
        self._show_help(arg.strip())

    def do_show(self, arg):
        """show [category] - list commands by category"""
        self._show_categories(arg.strip())

    def do_categories(self, arg):
        """categories - list all categories"""
        print()
        for c in sorted(categories()):
            print(f"  {c}")
        print()

    def emptyline(self):
        return False

    # â”€â”€ dispatch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def default(self, line):
        s = line.strip()
        if not s:
            return
        # '?' anywhere -> help for the token before the cursor
        if "?" in s:
            head = s.split("?", 1)[0].strip()
            self._inline_help(head)
            return
        if s in ("exit", "quit"):
            self._save_history()
            raise SystemExit(0)
        try:
            parts = shlex.split(s)
        except ValueError as e:
            print(f"[FAIL] parse error: {e}")
            return
        head = parts[0]
        node = COMMAND_TREE.get(head)
        if node is None:
            print(f"[FAIL] unknown command: {head}")
            print("       type ? to see all commands")
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

    # â”€â”€ IOS-style inline help â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _inline_help(self, head: str):
        """Show the valid next tokens for what has been typed so far."""
        toks = head.split()
        if not toks:
            self._show_categories("")
            return

        cmd = toks[0]
        if cmd not in COMMAND_TREE:
            print(f"[FAIL] unknown command: {cmd}")
            # offer near matches
            near = [n for n in COMMAND_TREE if n.startswith(cmd[:2])]
            if near:
                print(f"       did you mean: {', '.join(sorted(near))}")
            return

        node = COMMAND_TREE[cmd]
        subs = node.get("subcommands") or {}
        sub = toks[1] if len(toks) >= 2 and toks[1] in subs else None

        # what comes next?
        options = valid_next(cmd, sub, "")
        if not options:
            # no more tokens: show the command's own detail
            self._print_detail(cmd, node)
            return

        label = cmd + (f" {sub}" if sub else "")
        print()
        print(f"  {label}  -  valid next tokens")
        print("  " + "-" * 62)
        width = max(len(v) for v, _ in options) + 2
        for v, d in sorted(options):
            print(f"    {v.ljust(width)}{d}")
        print()

    # â”€â”€ help renderers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
            print("  Subcommands:")
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
        print(f"  {name} - {node.get('desc', '')}")
        print(f"  syntax: {node.get('syntax', name)}")
        print()
        self._print_sub_table(node["subcommands"])
        print()
        print(f"  {name} ?   for the valid next tokens")
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


def main() -> int:
    binpath = str(Path.home() / "bin")
    cur = os.environ.get("PATH", "")
    if binpath not in cur.split(os.pathsep):
        os.environ["PATH"] = binpath + os.pathsep + cur

    sh = AirShell()
    try:
        sh.cmdloop()
    except (KeyboardInterrupt, SystemExit):
        print()
        sh._save_history()
    return 0


if __name__ == "__main__":
    sys.exit(main())
