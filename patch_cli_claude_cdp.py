from pathlib import Path
import re

runtime_path = Path(r"backend\app\interception\claude.py")
chat_path = Path(r"cli\chat.py")

runtime = runtime_path.read_text(encoding="utf-8")
chat = chat_path.read_text(encoding="utf-8")

# ============================================================
# CLAUDE RUNTIME
# ============================================================

old_init = '''    def __init__(self, session_path: str, headless: bool = True):
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

new_init = '''    def __init__(
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

if old_init not in runtime:
    raise SystemExit("ABORT: ClaudeRuntime __init__ anchor not found.")

runtime = runtime.replace(old_init, new_init, 1)

old_start = '''        if not pathlib.Path(self.session_path).exists():
            raise ClaudeSessionError("Claude storage state file does not exist")

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            storage_state=self.session_path,
            service_workers="block",
        )
        self._page = await self._context.new_page()
'''

new_start = '''        self._pw = await async_playwright().start()

        if self.cdp_url:
            # Attach to the already-running authenticated Chromium session.
            # The live M1.4 Claude Web runtime uses CDP on port 9222.
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

if old_start not in runtime:
    raise SystemExit("ABORT: ClaudeRuntime start browser block not found.")

runtime = runtime.replace(old_start, new_start, 1)

old_close = '''        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
'''

new_close = '''        if self._browser is not None and self._owns_browser:
            try:
                await self._browser.close()
            except Exception:
                pass
'''

if old_close not in runtime:
    raise SystemExit("ABORT: ClaudeRuntime browser close block not found.")

runtime = runtime.replace(old_close, new_close, 1)

runtime_path.write_text(runtime, encoding="utf-8")

# ============================================================
# CLI CHAT
# ============================================================

if "import os" not in chat:
    chat = "import os\n" + chat

if "import uuid" not in chat:
    chat = chat.replace("import os\n", "import os\nimport uuid\n", 1)

# Remove the CLI-level storage-state existence gate.
# Keep _session_path() because storage-state remains the fallback
# runtime mode.
pattern = re.compile(
    r'''(?ms)
    ^\s*session_path\s*=\s*_session_path\(\)\s*
    \n
    ^\s*if\s+not\s+Path\(session_path\)\.exists\(\):\s*
    \n
    ^\s*print\(\s*
    \n?
    .*?
    ^\s*\)\s*
    \n
    '''
)

match = pattern.search(chat)

if match:
    replacement = '''    session_path = _session_path()
'''
    chat = chat[:match.start()] + replacement + chat[match.end():]
else:
    # The current CLI should contain the known guard. Refuse to make
    # an unsafe broad edit if its shape has unexpectedly changed.
    if "Claude session is not configured for CLI runtime" in chat:
        raise SystemExit(
            "ABORT: storage-state guard was found but its structure "
            "did not match the expected patch."
        )

# Add CDP URL and replace runtime construction.
old_runtime = '''    runtime = ClaudeRuntime(
        session_path=session_path,
        headless=False,
    )
'''

new_runtime = '''    cdp_url = os.getenv(
        "AINTERCEPTOR_CLAUDE_CDP_URL",
        "http://127.0.0.1:9222",
    )

    runtime = ClaudeRuntime(
        session_path=session_path,
        headless=False,
        cdp_url=cdp_url,
    )
'''

if old_runtime not in chat:
    raise SystemExit("ABORT: CLI ClaudeRuntime construction block not found.")

chat = chat.replace(old_runtime, new_runtime, 1)

# Replace non-unique request ID if still present.
chat = chat.replace(
    'request_id = f"cli-{id(prompt)}"',
    'request_id = f"cli-{uuid.uuid4()}"',
)

chat_path.write_text(chat, encoding="utf-8")

print("Claude CLI CDP integration patch applied.")
print("CDP endpoint:", "http://127.0.0.1:9222")
print("Storage-state remains available as fallback.")
