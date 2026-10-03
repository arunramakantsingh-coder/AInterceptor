import pathlib, subprocess, sys, textwrap, json, time

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
EVID = ROOT / ".evidence"
EVID.mkdir(exist_ok=True)
(EVID / "raw").mkdir(exist_ok=True)

def w(rel, content):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}")

def git(args, check=True):
    r = subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0 and "nothing to commit" not in (r.stdout+r.stderr):
        print(f"  [!] git {' '.join(args)}: {r.stderr.strip()[:200]}")
    return r

# ============================================================
# PART 1 — Provider registry
# ============================================================
w("backend/app/interception/registry.py", '''"""Provider registry — single source of truth for CDP port, session, transport.

Every provider has its own CDP endpoint so multiple providers can run in
parallel. Adding a provider = adding one entry here.
"""
from __future__ import annotations
import os, pathlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderEntry:
    name: str
    home_url: str
    transport: str                # "sse" (Claude) | "cdp" (non-Claude)
    cdp_port: int                 # fixed port so providers never collide
    session_env: str              # env var to override storage_state path
    login_markers: tuple[str, ...] = ()
    response_markers: tuple[str, ...] = ()
    request_markers: tuple[str, ...] = ()
    default_model: str = ""
    composer_selectors: tuple[str, ...] = ()
    extra: dict = field(default_factory=dict)


REGISTRY: dict[str, ProviderEntry] = {
    "claude": ProviderEntry(
        name="claude",
        home_url="https://claude.ai/",
        transport="sse",
        cdp_port=9222,
        session_env="AINTERCEPTOR_CLAUDE_STORAGE_STATE",
        login_markers=("/login", "/auth", "/signin"),
        response_markers=("/api/organizations/", "/completion"),
        request_markers=("/api/organizations/", "/completion"),
        default_model="claude-web",
        composer_selectors=('div[contenteditable="true"]', "textarea"),
    ),
    "deepseek": ProviderEntry(
        name="deepseek",
        home_url="https://chat.deepseek.com/",
        transport="cdp",
        cdp_port=9223,
        session_env="AINTERCEPTOR_DEEPSEEK_STORAGE_STATE",
        login_markers=("/login", "/auth", "/sign_in", "/signin"),
        response_markers=("/api/v0/chat/completion",),
        request_markers=("/api/v0/chat/completion",),
        default_model="deepseek-flash",
        composer_selectors=(
            'textarea[placeholder*="Message"]',
            'textarea[placeholder*="message"]',
            "textarea",
            '[contenteditable="true"]',
            '[role="textbox"]',
        ),
    ),
    "chatgpt": ProviderEntry(
        name="chatgpt",
        home_url="https://chatgpt.com/",
        transport="cdp",
        cdp_port=9224,
        session_env="AINTERCEPTOR_CHATGPT_STORAGE_STATE",
        login_markers=("/auth/login",),
        response_markers=("/backend-api/conversation",),
        request_markers=("/backend-api/conversation",),
        default_model="chatgpt-web",
        composer_selectors=("#prompt-textarea", 'div[contenteditable="true"]', "textarea"),
    ),
    "gemini": ProviderEntry(
        name="gemini",
        home_url="https://gemini.google.com/",
        transport="cdp",
        cdp_port=9225,
        session_env="AINTERCEPTOR_GEMINI_STORAGE_STATE",
        login_markers=("/accounts/", "signin"),
        response_markers=("StreamGenerate", "/assistant.lamda"),
        request_markers=("StreamGenerate",),
        default_model="gemini-web",
        composer_selectors=('div[contenteditable="true"]', "textarea"),
    ),
}


def get(provider: str) -> ProviderEntry:
    p = provider.lower()
    if p not in REGISTRY:
        raise KeyError(f"unknown provider: {provider}; known: {list(REGISTRY)}")
    return REGISTRY[p]


def cdp_url(provider: str) -> str | None:
    """Return CDP URL for this provider, or None if env forces fallback."""
    entry = get(provider)
    env_override = os.environ.get(f"AINTERCEPTOR_{provider.upper()}_CDP_URL")
    if env_override == "":
        return None
    if env_override:
        return env_override
    return f"http://127.0.0.1:{entry.cdp_port}"


def session_path(provider: str) -> pathlib.Path:
    entry = get(provider)
    env_override = os.environ.get(entry.session_env)
    if env_override:
        return pathlib.Path(env_override)
    return pathlib.Path(".ainterceptor") / provider / "storage_state.json"


def all_providers() -> list[str]:
    return list(REGISTRY)
''')

# ============================================================
# PART 2 — Patch nonclaude_runtime to use registry (no hardcoded 9222)
# ============================================================
rt = (BE / "app/interception/nonclaude_runtime.py").read_text(encoding="utf-8")

if "from app.interception.registry" not in rt:
    rt = rt.replace(
        "from app.interception.web_runtime import WebProviderSessionError, WebProviderSpec",
        "from app.interception.web_runtime import WebProviderSessionError, WebProviderSpec\nfrom app.interception import registry as provider_registry",
        1,
    )

# inject registry-aware CDP resolution into _ensure_page
old_block = '''        if self.cdp_url:
            self._browser = await self._pw.chromium.connect_over_cdp(self.cdp_url)'''
new_block = '''        if not self.cdp_url:
            self.cdp_url = provider_registry.cdp_url(self.provider)
        if self.cdp_url:
            self._browser = await self._pw.chromium.connect_over_cdp(self.cdp_url)'''
if old_block in rt and "provider_registry.cdp_url" not in rt:
    rt = rt.replace(old_block, new_block, 1)
    print("  [OK] nonclaude_runtime: CDP resolved via registry")

(BE / "app/interception/nonclaude_runtime.py").write_text(rt, encoding="utf-8", newline="\n")

# ============================================================
# PART 3 — Fix DeepSeek parser (path-keyed fragments, no word loss)
# ============================================================
ds_path = BE / "app/interception/deepseek.py"
ds = ds_path.read_text(encoding="utf-8")

# 3a. Replace _join_response_parts with a safe variant that never drops text
old_join = '''    @classmethod
    def _join_response_parts(cls, parts: list[str]) -> str:
        """Join distinct DeepSeek response fragments without replaying cumulative blocks."""
        assembled = ""
        for raw_part in parts:
            part = raw_part.strip()
            if not part:
                continue
            if not assembled:
                assembled = part
            elif part.startswith(assembled):
                assembled = part
            elif assembled.startswith(part) or part == assembled:
                continue
            else:
                assembled = f"{assembled}\\n\\n{part}"
        return assembled'''

new_join = '''    @classmethod
    def _join_response_parts(cls, parts: list[str]) -> str:
        """Join distinct DeepSeek response fragments without losing any text.

        Rules:
        - Consecutive fragments are joined literally (no dropped middle).
        - A fragment that is a strict cumulative extension of the accumulated
          text replaces it (this is DeepSeek replaying the growing body).
        - Any other fragment is appended as a new paragraph.
        Never discards text.
        """
        assembled = ""
        for raw_part in parts:
            part = raw_part
            if not part:
                continue
            if not assembled:
                assembled = part
                continue
            # Cumulative replay: new fragment strictly extends what we have
            if part.startswith(assembled):
                assembled = part
                continue
            # Exact duplicate: skip
            if part == assembled:
                continue
            # Literal append (fragments are sequential pieces of the SAME run)
            # Only treat as separate paragraph if there's clear paragraph signal.
            # DeepSeek uses explicit paragraph markers in `content`; here we
            # join literally and let the runtime compute deltas.
            assembled = assembled + part
        return assembled'''

if old_join in ds:
    ds = ds.replace(old_join, new_join, 1)
    print("  [OK] deepseek: _join_response_parts made lossless")
else:
    print("  [!] deepseek: _join_response_parts pattern not found — inspect manually")

# 3b. Path-keyed fragment state: track per-path buffers
# Add a dict to __init__ and use it in _apply_patch when a path is given.
if "_path_buffers" not in ds:
    # find __init__
    import re
    m = re.search(r"(def __init__\(self\)[^\n]*:\n)", ds)
    if m:
        inject = m.group(1) + '        self._path_buffers: dict[str, str] = {}\n'
        ds = ds[:m.start()] + inject + ds[m.end():]
        print("  [OK] deepseek: added _path_buffers")

# 3c. Replace _apply_patch content path handling to use _path_buffers
old_append = '''            fragment = self._ensure_fragment(index)
            if op in {"SET", "REPLACE"}:
                fragment["content"] = "".join(self._text_values(value))
            elif op in {"APPEND", ""}:
                self._append_content(fragment, value)
            return'''
new_append = '''            fragment = self._ensure_fragment(index)
            incoming = "".join(self._text_values(value))
            if op in {"SET", "REPLACE"}:
                fragment["content"] = incoming
                self._path_buffers[path] = incoming
            elif op in {"APPEND", ""}:
                prior = self._path_buffers.get(path, "")
                # Literal append: preserve every character
                fragment["content"] = prior + incoming
                self._path_buffers[path] = fragment["content"]
            return'''

if old_append in ds:
    ds = ds.replace(old_append, new_append, 1)
    print("  [OK] deepseek: _apply_patch uses per-path buffers")
else:
    print("  [!] deepseek: _apply_patch pattern not found — inspect manually")

ds_path.write_text(ds, encoding="utf-8", newline="\n")

# ============================================================
# PART 4 — Golden test (uses synthetic bytes now, real capture later)
# ============================================================
w("backend/tests/fixtures/deepseek_golden_synthetic.raw", """data: {"p":"response/fragments/-1/content","o":"APPEND","v":"hi "}
data: {"p":"response/fragments/-1/content","o":"APPEND","v":"how "}
data: {"p":"response/fragments/-1/content","o":"APPEND","v":"are "}
data: {"p":"response/fragments/-1/content","o":"APPEND","v":"you"}
data: {"v":{"response":{"fragments":[{"type":"RESPONSE","content":"hi how are you"}]}}}
""")

w("backend/tests/test_deepseek_golden.py", '''import pathlib
from app.interception.deepseek import parse_deepseek_web

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "deepseek_golden_synthetic.raw"


def test_deepseek_golden_synthetic_round_trip():
    body = FIXTURE.read_text(encoding="utf-8")
    result = parse_deepseek_web(body)
    assert result == "hi how are you", f"got {result!r}"


def test_deepseek_no_word_loss_across_fragments():
    lines = [
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"That"}',
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"\'s a "}',
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"good thing "}',
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"to want."}',
    ]
    body = "\\n".join(lines)
    assert parse_deepseek_web(body) == "That's a good thing to want."
''')

# ============================================================
# PART 5 — Gitignore accidental artifacts
# ============================================================
gi = ROOT / ".gitignore"
g = gi.read_text(encoding="utf-8") if gi.exists() else ""
for line in [".evidence/dump/", "ainterceptor.egg-info/", "discover_layout.py",
             "scripts/bootstrap/find_capture.py", "scripts/bootstrap/snapshot_parser.py"]:
    if line not in g:
        g = g.rstrip() + "\n" + line + "\n"
gi.write_text(g, encoding="utf-8", newline="\n")
print("  [OK] .gitignore updated")

git(["rm", "-r", "--cached", ".evidence/dump", "ainterceptor.egg-info"], check=False)

# ============================================================
# PART 6 — Run tests
# ============================================================
print("\n==> Running backend tests")
r = subprocess.run(
    ["python", "-m", "pytest", "-q", "tests/test_deepseek_golden.py",
     "tests/test_nonclaude_parsers.py"],
    cwd=BE, capture_output=True, text=True, shell=True,
)
print(r.stdout)
print(r.stderr)

if r.returncode != 0:
    print("=" * 60)
    print("RESULT: FAIL — tests did not pass. Do not commit.")
    print("Paste the failure above.")
    print("=" * 60)
    sys.exit(1)

# ============================================================
# PART 7 — Commit
# ============================================================
git(["add", "-A"])
msg = textwrap.dedent("""\
    fix(deepseek): lossless fragment assembly + provider registry

    - Add provider registry (CDP port, session, transport per provider)
    - Resolve CDP URL per provider (no more 9222 collision)
    - DeepSeek: per-path fragment buffers preserve every character
    - DeepSeek: _join_response_parts never discards text
    - Add golden fixture test (synthetic baseline)
    - Gitignore .evidence/dump and ainterceptor.egg-info
""")
r = git(["commit", "-m", msg])
print(r.stdout.strip() or r.stderr.strip())

print("=" * 60)
print("RESULT: PASS")
print("COMMIT:", git(["rev-parse", "HEAD"]).stdout.strip())
print("BRANCH:", git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip())
print()
print("NEXT — run real DeepSeek capture:")
print("  1. Launch DeepSeek Chrome on 9223 (one-time):")
print("     $chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'")
print("     Start-Process $chrome -ArgumentList '--remote-debugging-port=9223','--user-data-dir=C:\\Projects\\AInterceptor-M1.5\\.ainterceptor\\chrome-profile-deepseek','https://chat.deepseek.com/'")
print("  2. Log into DeepSeek in that window.")
print("  3. cd backend; python -u -m scripts.repro_deepseek_capture \"hi how are you\"")
print("  4. Paste the AIRouter output + .evidence/raw/deepseek_*.raw")
print("=" * 60)
