from pathlib import Path

runtime = Path(r"backend\app\interception\claude.py")
chat = Path(r"cli\chat.py")

runtime_text = runtime.read_text(encoding="utf-8")
chat_text = chat.read_text(encoding="utf-8")

# ------------------------------------------------------------
# 1. ClaudeRuntime: add optional CDP attachment
# ------------------------------------------------------------

old = '''    def __init__(self, session_path: str, headless: bool = True):
        self.provider = "claude"
        self.session_path = Path(session_path)
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._cdp = None
        self._transport = None
        self._started = False
        self._lock = asyncio.Lock()
'''

new = '''    def __init__(
        self,
        session_path: str,
        headless: bool = True,
        cdp_url: str | None = None,
    ):
        self.provider = "claude"
        self.session_path = Path(session_path)
        self.headless = headless
        self.cdp_url = cdp_url
        self._playwright = None
        self._browser = None
        self._owns_browser = False
        self._context = None
        self._page = None
        self._cdp = None
        self._transport = None
        self._started = False
        self._lock = asyncio.Lock()
'''

if old not in runtime_text:
    raise SystemExit(
        "ABORT: ClaudeRuntime.__init__ anchor not found. "
        "No files were modified."
    )

runtime_text = runtime_text.replace(old, new, 1)

# ------------------------------------------------------------
# 2. Replace browser launch section with CDP-or-launch logic
# ------------------------------------------------------------

old = '''        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless
        )
        self._context = await self._browser.new_context(
            storage_state=str(self.session_path)
        )
'''

new = '''        self._playwright = await async_playwright().start()

        if self.cdp_url:
            # Attach to an already-running authenticated Chromium instance.
            # This is the M1.4 live Claude Web session boundary.
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self.cdp_url
            )
            self._owns_browser = False

            contexts = self._browser.contexts
            if not contexts:
                raise ClaudeSessionError(
                    "CDP browser is connected but has no browser context."
                )

            self._context = contexts[0]

            pages = self._context.pages
            if pages:
                self._page = pages[0]
            else:
                self._page = await self._context.new_page()
        else:
            if not self.session_path.exists():
                raise ClaudeSessionError(
                    f"Claude session state not found: {self.session_path}"
                )

            self._browser = await self._playwright.chromium.launch(
                headless=self.headless
            )
            self._owns_browser = True
            self._context = await self._browser.new_context(
                storage_state=str(self.session_path)
            )
'''

if old not in runtime_text:
    raise SystemExit(
        "ABORT: ClaudeRuntime browser-launch anchor not found. "
        "No files were modified."
    )

runtime_text = runtime_text.replace(old, new, 1)

# ------------------------------------------------------------
# 3. Avoid closing user's externally-managed Chrome
# ------------------------------------------------------------

old = '''        if self._browser is not None:
            await self._browser.close()

        if self._playwright is not None:
            await self._playwright.stop()
'''

new = '''        if self._browser is not None and self._owns_browser:
            await self._browser.close()

        if self._playwright is not None:
            await self._playwright.stop()
'''

if old not in runtime_text:
    raise SystemExit(
        "ABORT: ClaudeRuntime.close browser cleanup anchor not found. "
        "No files were modified."
    )

runtime_text = runtime_text.replace(old, new, 1)

runtime.write_text(runtime_text, encoding="utf-8")

# ------------------------------------------------------------
# 4. CLI chat: use the existing M1.4 CDP session
# ------------------------------------------------------------

chat_text_old = chat_text

# Add os import if necessary.
if "import os" not in chat_text:
    if "from " in chat_text:
        first_import = chat_text.find("\n", chat_text.find("import "))
        if first_import == -1:
            raise SystemExit(
                "ABORT: Could not safely add os import. No CLI changes made."
            )
        chat_text = chat_text[:first_import + 1] + "import os\n" + chat_text[first_import + 1:]
    else:
        chat_text = "import os\n" + chat_text

# Replace the runtime construction.
old = '''        runtime = ClaudeRuntime(
            session_path=str(session_path),
            headless=False,
        )
'''

new = '''        cdp_url = os.environ.get(
            "AINTERCEPTOR_CLAUDE_CDP_URL",
            "http://127.0.0.1:9222",
        )

        runtime = ClaudeRuntime(
            session_path=str(session_path),
            headless=False,
            cdp_url=cdp_url,
        )
'''

if old not in chat_text:
    raise SystemExit(
        "ABORT: CLI ClaudeRuntime construction anchor not found. "
        "No CLI changes were made."
    )

chat_text = chat_text.replace(old, new, 1)

# UUID request IDs instead of process-object IDs.
if "import uuid" not in chat_text:
    marker = "import os\n"
    chat_text = chat_text.replace(marker, marker + "import uuid\n", 1)

old = 'request_id = f"cli-{id(prompt)}"'
new = 'request_id = f"cli-{uuid.uuid4()}"'

if old in chat_text:
    chat_text = chat_text.replace(old, new, 1)

chat.write_text(chat_text, encoding="utf-8")

print("Claude CLI CDP wiring applied.")
print("")
print("Runtime:")
print("  - supports existing Chromium CDP session")
print("  - defaults to http://127.0.0.1:9222")
print("  - does not close externally-managed Chrome")
print("")
print("CLI:")
print("  - chat -> ClaudeRuntime -> CDP transport")
print("  - request IDs use UUIDs")
