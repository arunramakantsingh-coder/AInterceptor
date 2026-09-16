from pathlib import Path
import ast
import re

RUNTIME = Path("backend/app/interception/claude.py")
CHAT = Path("cli/chat.py")

def lines_for(text, node):
    lines = text.splitlines(keepends=True)
    start = node.lineno - 1
    end = getattr(node, "end_lineno", node.lineno)
    return start, end, lines

def find_class_method(tree, class_name, method_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name == method_name:
                        return child
    return None

# ============================================================
# RUNTIME
# ============================================================
runtime = RUNTIME.read_text(encoding="utf-8")
tree = ast.parse(runtime)

runtime_class = next(
    (
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "ClaudeRuntime"
    ),
    None,
)

if runtime_class is None:
    raise SystemExit("ABORT: ClaudeRuntime class not found.")

init_node = find_class_method(tree, "ClaudeRuntime", "__init__")
start_node = find_class_method(tree, "ClaudeRuntime", "start")
close_node = find_class_method(tree, "ClaudeRuntime", "close")

if not init_node:
    raise SystemExit("ABORT: ClaudeRuntime.__init__ not found.")
if not start_node:
    raise SystemExit("ABORT: ClaudeRuntime.start not found.")
if not close_node:
    raise SystemExit("ABORT: ClaudeRuntime.close not found.")

# Preserve indentation used by the existing methods.
method_indent = " " * init_node.col_offset

new_init = f'''{method_indent}def __init__(
{method_indent}    self,
{method_indent}    session_path: str | None = None,
{method_indent}    headless: bool = True,
{method_indent}    cdp_url: str = "http://127.0.0.1:9222",
{method_indent}):
{method_indent}    self.session_path = session_path
{method_indent}    self.headless = headless
{method_indent}    self.cdp_url = cdp_url
{method_indent}    self._pw = None
{method_indent}    self._browser = None
{method_indent}    self._context = None
{method_indent}    self._page = None
{method_indent}    self._cdp = None
{method_indent}    self._transport: ClaudeCDPTransport | None = None
{method_indent}    self._started = False
{method_indent}    self._owns_browser = False
{method_indent}    self._execute_lock = asyncio.Lock()
'''

new_start = f'''{method_indent}async def start(self) -> None:
{method_indent}    if self._started:
{method_indent}        return
{method_indent}    if async_playwright is None:
{method_indent}        raise RuntimeError("playwright not installed")

{method_indent}    # Attach to the already authenticated Chrome instance used
{method_indent}    # by the proven Claude Web/CDP POC.
{method_indent}    self._pw = await async_playwright().start()
{method_indent}    try:
{method_indent}        self._browser = await self._pw.chromium.connect_over_cdp(
{method_indent}            self.cdp_url
{method_indent}        )
{method_indent}    except Exception as exc:
{method_indent}        await self._pw.stop()
{method_indent}        self._pw = None
{method_indent}        raise ClaudeSessionError(
{method_indent}            f"Could not connect to Claude Chrome CDP endpoint "
{method_indent}            f"{{self.cdp_url}}: {{exc}}"
{method_indent}        ) from exc

{method_indent}    # The browser belongs to the user, not this runtime.
{method_indent}    self._owns_browser = False

{method_indent}    contexts = self._browser.contexts
{method_indent}    if not contexts:
{method_indent}        raise ClaudeSessionError(
{method_indent}            "Claude CDP browser has no browser context"
{method_indent}        )

{method_indent}    self._context = contexts[0]

{method_indent}    claude_pages = [
{method_indent}        page for page in self._context.pages
{method_indent}        if "claude.ai" in page.url
{method_indent}    ]

{method_indent}    if claude_pages:
{method_indent}        self._page = claude_pages[-1]
{method_indent}    elif self._context.pages:
{method_indent}        self._page = self._context.pages[-1]
{method_indent}        await self._page.goto(
{method_indent}            "https://claude.ai/",
{method_indent}            wait_until="domcontentloaded",
{method_indent}            timeout=30_000,
{method_indent}        )
{method_indent}    else:
{method_indent}        self._page = await self._context.new_page()
{method_indent}        await self._page.goto(
{method_indent}            "https://claude.ai/",
{method_indent}            wait_until="domcontentloaded",
{method_indent}            timeout=30_000,
{method_indent}        )

{method_indent}    self._cdp = await self._context.new_cdp_session(self._page)
{method_indent}    self._transport = ClaudeCDPTransport(self._cdp)
{method_indent}    await self._transport.start()

{method_indent}    if "/login" in self._page.url or "/auth" in self._page.url:
{method_indent}        raise ClaudeSessionError(
{method_indent}            "Claude session is expired or not authenticated"
{method_indent}        )

{method_indent}    self._started = True
'''

new_close = f'''{method_indent}async def close(self) -> None:
{method_indent}    if self._transport is not None:
{method_indent}        try:
{method_indent}            await self._transport.close()
{method_indent}        except Exception:
{method_indent}            pass
{method_indent}        self._transport = None

{method_indent}    if self._cdp is not None:
{method_indent}        try:
{method_indent}            await self._cdp.detach()
{method_indent}        except Exception:
{method_indent}            pass
{method_indent}        self._cdp = None

{method_indent}    # NEVER close the user's externally managed Chrome.
{method_indent}    if self._browser is not None and self._owns_browser:
{method_indent}        try:
{method_indent}            await self._browser.close()
{method_indent}        except Exception:
{method_indent}            pass

{method_indent}    self._browser = None
{method_indent}    self._context = None
{method_indent}    self._page = None
{method_indent}    self._started = False

{method_indent}    if self._pw is not None:
{method_indent}        try:
{method_indent}            await self._pw.stop()
{method_indent}        except Exception:
{method_indent}            pass
{method_indent}        self._pw = None
'''

# Replace bottom-up so line offsets remain valid.
replacements = []
for node, new_text in [
    (init_node, new_init),
    (start_node, new_start),
    (close_node, new_close),
]:
    s, e, ls = lines_for(runtime, node)
    replacements.append((s, e, new_text))

for s, e, new_text in sorted(replacements, reverse=True):
    ls = runtime.splitlines(keepends=True)
    runtime = "".join(ls[:s]) + new_text + "".join(ls[e:])

# Validate runtime before writing.
ast.parse(runtime)

required_runtime = [
    'connect_over_cdp(',
    'self.cdp_url',
    'self._owns_browser = False',
    'self._transport = ClaudeCDPTransport',
    'if self._browser is not None and self._owns_browser:',
]

for marker in required_runtime:
    if marker not in runtime:
        raise SystemExit(
            f"ABORT: runtime validation failed; missing: {marker}"
        )

# ============================================================
# CLI CHAT
# ============================================================
chat = CHAT.read_text(encoding="utf-8")
chat_tree = ast.parse(chat)

# Find any function containing the obsolete storage-state error.
target_guard = None
target_function = None

for fn in ast.walk(chat_tree):
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue

    segment = ast.get_source_segment(chat, fn) or ""

    if (
        "Claude session is not configured for CLI runtime" in segment
        or "Expected storage state:" in segment
        or "AINTERCEPTOR_CLAUDE_STORAGE_STATE" in segment
    ):
        target_function = fn
        for child in ast.walk(fn):
            if isinstance(child, ast.If):
                child_segment = ast.get_source_segment(chat, child) or ""
                if (
                    "storage state" in child_segment.lower()
                    or "AINTERCEPTOR_CLAUDE_STORAGE_STATE" in child_segment
                ):
                    target_guard = child
                    break
        break

if target_function is None:
    raise SystemExit(
        "ABORT: CLI function containing obsolete storage-state guard not found."
    )

if target_guard is None:
    raise SystemExit(
        "ABORT: CLI storage-state guard not found structurally."
    )

# Remove ONLY that obsolete if block.
guard_start = target_guard.lineno - 1
guard_end = target_guard.end_lineno

chat_lines = chat.splitlines(keepends=True)
chat = "".join(chat_lines[:guard_start]) + "".join(chat_lines[guard_end:])

# Reparse after guard removal.
chat_tree = ast.parse(chat)

# Locate ClaudeRuntime construction.
runtime_call = None
for node in ast.walk(chat_tree):
    if isinstance(node, ast.Call):
        func = node.func
        if (
            isinstance(func, ast.Name)
            and func.id == "ClaudeRuntime"
        ) or (
            isinstance(func, ast.Attribute)
            and func.attr == "ClaudeRuntime"
        ):
            runtime_call = node
            break

if runtime_call is None:
    raise SystemExit(
        "ABORT: ClaudeRuntime constructor call not found in cli/chat.py."
    )

# Replace the entire statement containing the constructor.
statement = runtime_call
for node in ast.walk(chat_tree):
    if isinstance(node, ast.Assign) and node.value is runtime_call:
        statement = node
        break

stmt_start = statement.lineno - 1
stmt_end = statement.end_lineno

chat_lines = chat.splitlines(keepends=True)

# Determine indentation from existing statement.
existing = "".join(chat_lines[stmt_start:stmt_end])
indent = existing[:len(existing) - len(existing.lstrip())]

new_call = (
    f'{indent}cdp_url = os.getenv('
    f'"AINTERCEPTOR_CLAUDE_CDP_URL", '
    f'"http://127.0.0.1:9222")\n'
    f'{indent}runtime = ClaudeRuntime(\n'
    f'{indent}    session_path=None,\n'
    f'{indent}    headless=False,\n'
    f'{indent}    cdp_url=cdp_url,\n'
    f'{indent})\n'
)

# Preserve assignment target if original wasn't literally "runtime =".
if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
    target_text = ast.get_source_segment(chat, statement.targets[0])
    new_call = (
        f'{indent}cdp_url = os.getenv('
        f'"AINTERCEPTOR_CLAUDE_CDP_URL", '
        f'"http://127.0.0.1:9222")\n'
        f'{indent}{target_text} = ClaudeRuntime(\n'
        f'{indent}    session_path=None,\n'
        f'{indent}    headless=False,\n'
        f'{indent}    cdp_url=cdp_url,\n'
        f'{indent})\n'
    )

chat = "".join(chat_lines[:stmt_start]) + new_call + "".join(chat_lines[stmt_end:])

# ============================================================
# Final validation
# ============================================================
ast.parse(chat)

if "Expected storage state:" in chat:
    raise SystemExit(
        "ABORT: obsolete storage-state error remains in cli/chat.py."
    )

if "AINTERCEPTOR_CLAUDE_CDP_URL" not in chat:
    raise SystemExit(
        "ABORT: CDP environment variable missing from cli/chat.py."
    )

if "cdp_url=cdp_url" not in chat:
    raise SystemExit(
        "ABORT: CLI does not pass cdp_url to ClaudeRuntime."
    )

# Write only after ALL validation succeeds.
RUNTIME.write_text(runtime, encoding="utf-8")
CHAT.write_text(chat, encoding="utf-8")

print("")
print("============================================================")
print(" AInterceptor Claude CLI integration PATCH: PASS")
print("============================================================")
print("")
print("Changed:")
print("  backend/app/interception/claude.py")
print("    * ClaudeRuntime attaches to existing Chrome via CDP")
print("    * Uses AINTERCEPTOR_CLAUDE_CDP_URL")
print("    * Does not own/close user's Chrome")
print("")
print("  cli/chat.py")
print("    * Removed obsolete storage_state.json requirement")
print("    * Passes CDP URL into ClaudeRuntime")
print("")
print("No database, migration, Git branch, or unrelated files touched.")
print("")
