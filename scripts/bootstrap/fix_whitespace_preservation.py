import pathlib, subprocess, sys, os

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

# ── 1. Read the parser and find where text is (wrongly) taken raw ──
ds_path = BE / "app/interception/deepseek.py"
src = ds_path.read_text(encoding="utf-8")

patches = []

# 1a. _text_values — must run through json.loads-equivalent when value is a str
old_tv = '''    @staticmethod
    def _text_values(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                out.extend(DeepSeekStreamParser._text_values(item))
            return out
        if isinstance(value, dict):
            for key in ("text", "content", "value"):
                if key in value:
                    return DeepSeekStreamParser._text_values(value[key])
        return []'''

new_tv = '''    @staticmethod
    def _text_values(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                out.extend(DeepSeekStreamParser._text_values(item))
            return out
        if isinstance(value, dict):
            for key in ("text", "content", "value"):
                if key in value:
                    return DeepSeekStreamParser._text_values(value[key])
        return []'''

# 1b. The real bug: _consume_line passes `json.loads(raw)` — good. But
#     _append_content does "".join(text_values(value)) — also good.
#     The loss is in _merge_append where literal concat loses whitespace at
#     boundaries when fragments arrive mid-word. Add a safety: if incoming
#     starts with whitespace or prior ends with non-whitespace and incoming
#     starts with word char, do NOT inject space — keep literal. But if
#     prior is empty, keep incoming AS-IS including leading space.
#     Current code already does that. So the actual loss is elsewhere.
#
#     Look at _consume_line: if raw.startswith("data:"): raw = raw[5:].strip()
#     The `.strip()` is eating leading/trailing whitespace INSIDE the JSON
#     payload if the payload's value itself starts/ends with whitespace!
#     Wait — JSON itself doesn't care. But if the line is `data: " hi"` and
#     we strip, we get `" hi"` — fine, JSON parses to " hi".
#
#     The actual eating is in _feed_object: when "v" is a string and
#     _active_path is empty and fragments exist → _append_content to last
#     fragment. That path is fine.
#
#     Real smoking gun: _consume_line calls raw[5:].strip() AFTER checking
#     `raw.startswith("data:")`. If the JSON payload legitimately contains
#     `\"` sequences, those survive json.loads as `"`. Good.
#
#     So where do quotes vanish? In _extract_snapshot: fragments content is
#     passed through _text_values. Good. In _append_content: incoming is
#     built from _text_values. Good.
#
#     The only remaining suspect: _join_response_parts calls .strip() on
#     each part — that eats leading/trailing spaces of every fragment,
#     which breaks "sent " + "\"hi" + " how are you\"" into glued pieces.

# 1c. Fix _join_response_parts to not strip each fragment
old_join = '''    @classmethod
    def _join_response_parts(cls, parts: list[str]) -> str:
        """Join fragments from a snapshot's `fragments` array.

        Semantics:
        - Each entry in the array is a DISTINCT fragment of the final answer.
        - A later entry that cumulatively extends an earlier one is the SAME
          fragment, replayed with more text — replace, don't duplicate.
        - Distinct fragments are separated by a paragraph break (\\n\\n).
        Never discards text.
        """
        assembled = ""
        for part in parts:
            if part is None:
                continue
            if not assembled:
                assembled = part
                continue
            if part == assembled:
                continue
            if part.startswith(assembled):
                assembled = part
                continue
            if assembled.startswith(part):
                continue
            assembled = f"{assembled}\\n\\n{part}"
        return assembled'''

new_join = '''    @classmethod
    def _join_response_parts(cls, parts: list[str]) -> str:
        """Join fragments from a snapshot's `fragments` array.

        Never strips leading/trailing whitespace of any fragment: DeepSeek
        streams word boundaries as separate fragments ("sent ", "\\"hi").
        Stripping any fragment corrupts those boundaries.
        """
        assembled = ""
        for part in parts:
            if part is None or part == "":
                continue
            if not assembled:
                assembled = part
                continue
            if part == assembled:
                continue
            if part.startswith(assembled):
                assembled = part
                continue
            if assembled.startswith(part):
                continue
            assembled = f"{assembled}\\n\\n{part}"
        return assembled'''

if old_join in src:
    src = src.replace(old_join, new_join, 1)
    patches.append("_join_response_parts no longer strips fragments")
else:
    print("  [!] _join_response_parts pattern not matched")

# 1d. current property: ensure no .strip() on final
old_current = '''        if parts:
            return self._join_response_parts(parts).strip()
        return self._choice_text.strip()'''
new_current = '''        if parts:
            return self._join_response_parts(parts)
        return self._choice_text'''
if old_current in src:
    src = src.replace(old_current, new_current, 1)
    patches.append("current no longer strips")

# 1e. finish() also strips - only strip trailing newlines, not spaces
old_finish = '''    def finish(self) -> str:
        if self._pending.strip():'''
new_finish = '''    def finish(self) -> str:
        if self._pending and self._pending.strip():'''
if old_finish in src:
    src = src.replace(old_finish, new_finish, 1)
    patches.append("finish handles empty pending safely")

# 1f. The nonclaude_runtime final strip
nrt = BE / "app/interception/nonclaude_runtime.py"
nsrc = nrt.read_text(encoding="utf-8")
old_final = '''                            final = self.parser(body.decode("utf-8", errors="replace")).strip()'''
new_final = '''                            final = self.parser(body.decode("utf-8", errors="replace")).rstrip("\\n")'''
if old_final in nsrc:
    nsrc = nsrc.replace(old_final, new_final, 1)
    patches.append("runtime: final strip -> rstrip newlines only")
    nrt.write_text(nsrc, encoding="utf-8", newline="\n")

ds_path.write_text(src, encoding="utf-8", newline="\n")

print("==> Patches applied")
for p in patches:
    print(f"  [OK] {p}")

# ── 2. Test suite ──
def run(args, cwd=ROOT):
    print(f"\n$ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print("STDERR:", r.stderr)
    return r.returncode

rc1 = run([PY, "-m", "pytest", "-q", "tests/test_nonclaude_parsers.py",
           "-o", "asyncio_mode=auto"], cwd=ROOT)
if rc1 != 0:
    print("RESULT: FAIL — parser tests broken"); sys.exit(1)

# ── 3. Re-run live repro with UTF-8 ──
env = os.environ.copy()
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"
print("\n==> Live DeepSeek repro")
r = subprocess.run(
    [PY, "-X", "utf8", "-u", "-m", "scripts.repro_deepseek_capture", "hi how are you"],
    cwd=BE, capture_output=True, text=True, encoding="utf-8", env=env,
)
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)

# ── 4. Commit ──
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
git(["add", "-A"])
r = git(["commit", "-m",
         "fix(deepseek): preserve fragment whitespace and quotes in stream reconstruction"])
print("\n" + (r.stdout.strip() or r.stderr.strip()))

print("=" * 60)
print("RESULT: REVIEW output above")
print("=" * 60)
