from pathlib import Path

runtime_path = Path("backend/app/interception/claude.py")
chat_path = Path("cli/chat.py")

runtime = runtime_path.read_text(encoding="utf-8")
chat = chat_path.read_text(encoding="utf-8")

# ------------------------------------------------------------
# 1. ClaudeRuntime: add CDP endpoint + ownership state
# ------------------------------------------------------------
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
        session_path: str | None = None,
        headless: bool = True,
        cdp_url: str = "http://127.0.0.1:9222",
    ):
        self.session_path = session_path
        self.headless = headless
        self.cdp_url = cdp_url
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._cdp = None
        self._transport: ClaudeCDPTransport | None = None
        self._started = False
        self._owns_browser = False
        self._execute_lock = asyncio.Lock()
'''

if old not in runtime:
    raise SystemExit("ABORT: ClaudeRuntime constructor anchor not found.")

runtime = runtime.replace(old, new, 1)

# ------------------------------------------------------------
# 2. ClaudeRuntime.start(): attach to existing Chrome
# ------------------------------------------------------------
old_start = '''        if not pathlib.Path(self.session_path).exists():
            raise ClaudeSessionError("Claude storage state file does not exist")

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            storage_state=self.session_path,
            service_workers="block",
        )
        self._page = await self._context.new_page()
        self._cdp = await self._context.new_cdp_session(self._page)
'''

new_start = '''        self._pw = await async_playwright().start()

        # CLI/runtime attaches to the already-authenticated Chrome session
        # used by the proven Claude Web/CDP POC.
        try:
            self._browser = await self._pw.chromium.connect_over_cdp(self.cdp_url)
        except Exception as exc:
            await self._pw.stop()
            self._pw = None
            raise ClaudeSessionError(
                f"Could not connect to Claude Chrome CDP endpoint "
                f"{self.cdp_url}: {exc}"
            ) from exc

        self._owns_browser = False

        contexts = self._browser.contexts
        if not contexts:
            await self._browser.close()
            await self._pw.stop()
            self._browser = None
            self._pw = None
            raise ClaudeSessionError(
                "Claude CDP browser has no browser context"
            )

        self._context = contexts[0]

        claude_pages = [
            page for page in self._context.pages
            if "claude.ai" in page.url
        ]

        if claude_pages:
            self._page = claude_pages[-1]
        elif self._context.pages:
            self._page = self._context.pages[-1]
            await self._page.goto(
                "https://claude.ai/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
        else:
            self._page = await self._context.new_page()
            await self._page.goto(
                "https://claude.ai/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )

        self._cdp = await self._context.new_cdp_session(self._page)
'''

if old_start not in runtime:
    raise SystemExit("ABORT: ClaudeRuntime.start() browser setup anchor not found.")

runtime = runtime.replace(old_start, new_start, 1)

# ------------------------------------------------------------
# 3. Runtime close(): never close user's existing Chrome
# ------------------------------------------------------------
old_close = '''        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()
'''

new_close = '''        if self._browser is not None and self._owns_browser:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()
'''

if old_close in runtime:
    runtime = runtime.replace(old_close, new_close, 1)
else:
    # Do not fail if the close implementation is structurally different.
    print("WARN: close() exact anchor not found; leaving close implementation unchanged.")

# ------------------------------------------------------------
# 4. CLI chat: remove obsolete storage_state existence gate
# ------------------------------------------------------------
guard_start = chat.find('    if not Path(session_path).exists():')
if guard_start == -1:
    raise SystemExit("ABORT: CLI storage-state guard not found.")

runtime_ctor = chat.find('    runtime = ClaudeRuntime(', guard_start)
if runtime_ctor == -1:
    raise SystemExit("ABORT: CLI ClaudeRuntime constructor not found.")

# Locate end of the guard block immediately before runtime construction.
chat = chat[:guard_start] + chat[runtime_ctor:]

# Add CDP configuration immediately before runtime construction.
runtime_ctor = chat.find('    runtime = ClaudeRuntime(')
if runtime_ctor == -1:
    raise SystemExit("ABORT: ClaudeRuntime constructor disappeared after patch.")

chat = (
    chat[:runtime_ctor]
    + '    cdp_url = os.getenv("AINTERCEPTOR_CLAUDE_CDP_URL", "http://127.0.0.1:9222")\n'
    + chat[runtime_ctor:]
)

# Replace constructor call if it still uses session_path only.
chat = chat.replace(
    '    runtime = ClaudeRuntime(session_path=session_path, headless=False)',
    '    runtime = ClaudeRuntime(\n'
    '        session_path=session_path,\n'
    '        headless=False,\n'
    '        cdp_url=cdp_url,\n'
    '    )',
    1,
)

# If the local implementation has a different constructor formatting,
# require that cdp_url actually appears in the runtime construction area.
runtime_ctor = chat.find('    runtime = ClaudeRuntime(')
runtime_tail = chat[runtime_ctor:runtime_ctor + 500]

if 'cdp_url=cdp_url' not in runtime_tail:
    raise SystemExit(
        "ABORT: CLI ClaudeRuntime constructor was not updated with cdp_url."
    )

# ------------------------------------------------------------
# 5. Validate before writing
# ------------------------------------------------------------
if 'connect_over_cdp(self.cdp_url)' not in runtime:
    raise SystemExit("ABORT: CDP attachment code missing.")

if 'AINTERCEPTOR_CLAUDE_CDP_URL' not in chat:
    raise SystemExit("ABORT: CLI CDP environment configuration missing.")

# Write only after all structural checks pass.
runtime_path.write_text(runtime, encoding="utf-8")
chat_path.write_text(chat, encoding="utf-8")

print("PATCH PASS")
print("  backend/app/interception/claude.py")
print("    - ClaudeRuntime now attaches to existing Chrome CDP")
print("    - runtime does not own/close the user's browser")
print("  cli/chat.py")
print("    - removed obsolete storage_state.json gate")
print("    - uses AINTERCEPTOR_CLAUDE_CDP_URL")
print("")
print("CDP endpoint:")
print("  http://127.0.0.1:9222")
