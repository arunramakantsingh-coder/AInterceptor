from pathlib import Path

runtime_path = Path(r"backend\app\interception\claude.py")
chat_path = Path(r"cli\chat.py")

runtime = runtime_path.read_text(encoding="utf-8")
chat = chat_path.read_text(encoding="utf-8")

# ============================================================
# 1. Patch ClaudeRuntime constructor
# ============================================================

old = '''    def __init__(self, session_path: str, headless: bool = True):
        self.session_path = session_path
        self.headless = headless
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._cdp = None
        self._transport: ClaudeCDPTransport | None = None
        self._started = False
        self._execute_lock = asyncio.Lock()
'''

new = '''    def __init__(
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

if old not in runtime:
    raise SystemExit("ABORT: ClaudeRuntime constructor anchor not found.")

runtime = runtime.replace(old, new, 1)

# ============================================================
# 2. Patch ClaudeRuntime.start()
# ============================================================

old = '''        if not pathlib.Path(self.session_path).exists():
            raise ClaudeSessionError("Claude storage state file does not exist")

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            storage_state=self.session_path,
            service_workers="block",
        )
        self._page = await self._context.new_page()
'''

new = '''        self._pw = await async_playwright().start()

        if self.cdp_url:
            # Attach to the existing authenticated Chromium instance.
            # M1.4 live Claude session uses CDP on localhost:9222.
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

if old not in runtime:
    raise SystemExit("ABORT: ClaudeRuntime.start() browser block not found.")

runtime = runtime.replace(old, new, 1)

# ============================================================
# 3. Do not close externally managed Chrome
# ============================================================

old = '''        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
'''

new = '''        if self._browser is not None and self._owns_browser:
            try:
                await self._browser.close()
            except Exception:
                pass
'''

if old not in runtime:
    raise SystemExit("ABORT: ClaudeRuntime.close() browser block not found.")

runtime = runtime.replace(old, new, 1)

runtime_path.write_text(runtime, encoding="utf-8")

# ============================================================
# 4. Patch CLI chat.py
# ============================================================

if "import os" not in chat:
    chat = "import os\n" + chat

if "import uuid" not in chat:
    chat = chat.replace(
        "import os\n",
        "import os\nimport uuid\n",
        1,
    )

# The actual CLI structure is:
#
#     session_path = _session_path()
#     if not Path(session_path).exists():
#         ...
#     runtime = ClaudeRuntime(...)
#
# Remove only that guard using stable anchors.

guard_start = chat.find("    if not Path(session_path).exists():")

if guard_start == -1:
    raise SystemExit(
        "ABORT: CLI storage-state guard anchor not found."
    )

runtime_anchor = chat.find(
    "    runtime = ClaudeRuntime(",
    guard_start,
)

if runtime_anchor == -1:
    raise SystemExit(
        "ABORT: CLI ClaudeRuntime construction anchor not found."
    )

# Preserve session_path assignment and remove everything between it
# and the runtime construction.
chat = (
    chat[:guard_start]
    + chat[runtime_anchor:]
)

# Replace the existing runtime construction block.
old = '''    runtime = ClaudeRuntime(
        session_path=session_path,
        headless=False,
    )
'''

new = '''    cdp_url = os.getenv(
        "AINTERCEPTOR_CLAUDE_CDP_URL",
        "http://127.0.0.1:9222",
    )

    runtime = ClaudeRuntime(
        session_path=session_path,
        headless=False,
        cdp_url=cdp_url,
    )
'''

if old not in chat:
    raise SystemExit(
        "ABORT: CLI ClaudeRuntime constructor block not found."
    )

chat = chat.replace(old, new, 1)

# Use UUID request IDs.
chat = chat.replace(
    'request_id = f"cli-{id(prompt)}"',
    'request_id = f"cli-{uuid.uuid4()}"',
)

chat_path.write_text(chat, encoding="utf-8")

print("")
print("==============================================")
print(" Claude CLI CDP wiring applied successfully")
print("==============================================")
print("")
print("CLI CDP endpoint:")
print("  http://127.0.0.1:9222")
print("")
print("Behavior:")
print("  CDP mode       -> attach to existing Chrome")
print("  Storage state  -> fallback mode")
print("  Chrome closing -> disabled for external CDP")
print("")
