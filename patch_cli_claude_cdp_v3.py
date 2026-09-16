from pathlib import Path

runtime_path = Path(r"backend\app\interception\claude.py")
chat_path = Path(r"cli\chat.py")

runtime = runtime_path.read_text(encoding="utf-8")
chat = chat_path.read_text(encoding="utf-8")

# ============================================================
# BUILD RUNTIME CHANGE IN MEMORY FIRST
# Nothing is written until ALL validations pass.
# ============================================================

runtime_lines = runtime.splitlines(keepends=True)

# ---------- constructor ----------
init_idx = next(
    (i for i, line in enumerate(runtime_lines)
     if line.startswith("    def __init__(self, session_path: str, headless: bool = True):")),
    None,
)

start_idx = next(
    (i for i, line in enumerate(runtime_lines)
     if line.startswith("    async def start(self) -> None:")),
    None,
)

if init_idx is None:
    raise SystemExit("ABORT: Could not locate ClaudeRuntime.__init__.")

if start_idx is None or start_idx <= init_idx:
    raise SystemExit("ABORT: Could not locate ClaudeRuntime.start().")

new_constructor = '''    def __init__(
        self,
        session_path: str,
        headless: bool = True,
        cdp_url: str | None = None,
    ):
        self.session_path = session_path
        self.headless = headless
        self.cdp_url = cdp_url
        self._pw = None
        self._browser = None
        self._owns_browser = False
        self._context = None
        self._page = None
        self._cdp = None
        self._transport: ClaudeCDPTransport | None = None
        self._started = False
        self._execute_lock = asyncio.Lock()

'''

runtime_lines = (
    runtime_lines[:init_idx]
    + new_constructor.splitlines(keepends=True)
    + runtime_lines[start_idx:]
)

# ---------- start browser block ----------
start_idx = next(
    i for i, line in enumerate(runtime_lines)
    if line.startswith("    async def start(self) -> None:")
)

browser_guard_idx = next(
    (i for i in range(start_idx, len(runtime_lines))
     if "if not pathlib.Path(self.session_path).exists():" in runtime_lines[i]),
    None,
)

pw_idx = next(
    (i for i in range(start_idx, len(runtime_lines))
     if "self._pw = await async_playwright().start()" in runtime_lines[i]),
    None,
)

page_idx = next(
    (i for i in range(start_idx, len(runtime_lines))
     if "self._page = await self._context.new_page()" in runtime_lines[i]),
    None,
)

if browser_guard_idx is None:
    raise SystemExit("ABORT: storage-state guard not found in ClaudeRuntime.start().")

if pw_idx is None or page_idx is None:
    raise SystemExit("ABORT: ClaudeRuntime browser setup anchors not found.")

# We expect the current start() setup to run from the storage-state
# guard through the first page creation.
if not (browser_guard_idx < pw_idx <= page_idx):
    raise SystemExit("ABORT: Unexpected ClaudeRuntime.start() structure.")

new_browser_block = '''        self._pw = await async_playwright().start()

        if self.cdp_url:
            # Attach to the already-running authenticated Chromium session.
            # M1.4 live Claude Web session uses localhost:9222.
            self._browser = await self._pw.chromium.connect_over_cdp(
                self.cdp_url
            )
            self._owns_browser = False

            contexts = self._browser.contexts
            if not contexts:
                raise ClaudeSessionError(
                    "Claude CDP browser has no browser contexts"
                )

            self._context = contexts[0]

            pages = self._context.pages
            if pages:
                self._page = pages[0]
            else:
                self._page = await self._context.new_page()

        else:
            if not pathlib.Path(self.session_path).exists():
                raise ClaudeSessionError(
                    "Claude storage state file does not exist"
                )

            self._browser = await self._pw.chromium.launch(
                headless=self.headless
            )
            self._owns_browser = True

            self._context = await self._browser.new_context(
                storage_state=self.session_path,
                service_workers="block",
            )
            self._page = await self._context.new_page()
'''

# Find the first page creation after the storage-state guard and replace
# the entire setup region.
block_end = page_idx + 1

runtime_lines = (
    runtime_lines[:browser_guard_idx]
    + new_browser_block.splitlines(keepends=True)
    + runtime_lines[block_end:]
)

# ---------- close() ----------
close_idx = next(
    (i for i, line in enumerate(runtime_lines)
     if line.startswith("    async def close(self) -> None:")),
    None,
)

if close_idx is None:
    raise SystemExit("ABORT: ClaudeRuntime.close() not found.")

browser_close_idx = next(
    (i for i in range(close_idx, len(runtime_lines))
     if "if self._browser is not None:" in runtime_lines[i]),
    None,
)

if browser_close_idx is None:
    raise SystemExit("ABORT: ClaudeRuntime browser cleanup not found.")

# Replace only the browser-close condition.
runtime_lines[browser_close_idx] = (
    "        if self._browser is not None and self._owns_browser:\n"
)

new_runtime = "".join(runtime_lines)

# ============================================================
# BUILD CLI CHANGE IN MEMORY
# ============================================================

chat_lines = chat.splitlines(keepends=True)

if not any(line.strip() == "import os" for line in chat_lines):
    # Put imports before the first non-import section.
    insert_at = 0
    while insert_at < len(chat_lines) and (
        chat_lines[insert_at].startswith("from ")
        or chat_lines[insert_at].startswith("import ")
        or chat_lines[insert_at].strip() == ""
    ):
        insert_at += 1
    chat_lines.insert(insert_at, "import os\n")

if not any(line.strip() == "import uuid" for line in chat_lines):
    insert_at = 0
    while insert_at < len(chat_lines) and (
        chat_lines[insert_at].startswith("from ")
        or chat_lines[insert_at].startswith("import ")
        or chat_lines[insert_at].strip() == ""
    ):
        insert_at += 1
    chat_lines.insert(insert_at, "import uuid\n")

# Locate storage path assignment.
session_idx = next(
    (i for i, line in enumerate(chat_lines)
     if "session_path = _session_path()" in line),
    None,
)

if session_idx is None:
    raise SystemExit("ABORT: CLI session_path assignment not found.")

# Locate the storage-state guard after that assignment.
guard_idx = next(
    (i for i in range(session_idx + 1, len(chat_lines))
     if "if not Path(session_path).exists():" in chat_lines[i]),
    None,
)

runtime_idx = next(
    (i for i in range(session_idx + 1, len(chat_lines))
     if "runtime = ClaudeRuntime(" in chat_lines[i]),
    None,
)

if guard_idx is None:
    raise SystemExit("ABORT: CLI storage-state guard not found.")

if runtime_idx is None or runtime_idx <= guard_idx:
    raise SystemExit("ABORT: CLI runtime construction not found after guard.")

# Remove only the guard/error block.
chat_lines = (
    chat_lines[:guard_idx]
    + chat_lines[runtime_idx:]
)

# Recalculate runtime constructor.
runtime_idx = next(
    i for i, line in enumerate(chat_lines)
    if "runtime = ClaudeRuntime(" in line
)

# Find end of constructor: closing line with 4-space indentation.
constructor_end = None
for i in range(runtime_idx, len(chat_lines)):
    if i > runtime_idx and chat_lines[i].strip() == ")":
        constructor_end = i + 1
        break

if constructor_end is None:
    raise SystemExit("ABORT: CLI ClaudeRuntime constructor end not found.")

new_cli_runtime = '''    cdp_url = os.getenv(
        "AINTERCEPTOR_CLAUDE_CDP_URL",
        "http://127.0.0.1:9222",
    )

    runtime = ClaudeRuntime(
        session_path=session_path,
        headless=False,
        cdp_url=cdp_url,
    )
'''

chat_lines = (
    chat_lines[:runtime_idx]
    + new_cli_runtime.splitlines(keepends=True)
    + chat_lines[constructor_end:]
)

new_chat = "".join(chat_lines)

# UUID request IDs.
new_chat = new_chat.replace(
    'request_id = f"cli-{id(prompt)}"',
    'request_id = f"cli-{uuid.uuid4()}"',
)

# ============================================================
# FINAL VALIDATION BEFORE WRITING
# ============================================================

required_runtime = [
    "cdp_url: str | None = None",
    "self._owns_browser = False",
    "connect_over_cdp",
    "self._owns_browser = True",
    "self._browser is not None and self._owns_browser",
]

required_chat = [
    "AINTERCEPTOR_CLAUDE_CDP_URL",
    'http://127.0.0.1:9222',
    "cdp_url=cdp_url",
]

for item in required_runtime:
    if item not in new_runtime:
        raise SystemExit(f"ABORT: Runtime validation failed: {item}")

for item in required_chat:
    if item not in new_chat:
        raise SystemExit(f"ABORT: CLI validation failed: {item}")

# The old CLI error must no longer exist.
if "Claude session is not configured for CLI runtime" in new_chat:
    raise SystemExit(
        "ABORT: Old CLI storage-state error path still present."
    )

# Only now write files.
runtime_path.write_text(new_runtime, encoding="utf-8")
chat_path.write_text(new_chat, encoding="utf-8")

print("")
print("==============================================")
print(" Claude CLI CDP wiring applied")
print("==============================================")
print("")
print("ClaudeRuntime:")
print("  CDP attach       : ENABLED")
print("  External Chrome  : NOT CLOSED")
print("  Storage state    : fallback")
print("")
print("CLI:")
print("  CDP endpoint     : http://127.0.0.1:9222")
print("  Storage gate     : REMOVED")
print("  UUID request IDs : ENABLED")
