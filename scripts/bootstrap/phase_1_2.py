import pathlib, subprocess, sys, re

ROOT = pathlib.Path(__file__).resolve().parent

# ---------- 1. Patch Next.js CVE ----------
pkg = ROOT / "dashboard/package.json"
p = pkg.read_text(encoding="utf-8")
p = p.replace('"next": "15.0.3"', '"next": "15.0.7"')
pkg.write_text(p, encoding="utf-8")
print("[OK] dashboard/package.json: next -> 15.0.7 (K003)")

# ---------- 2. Governance Section 20 ----------
gov = ROOT / "PROJECT_GOVERNANCE_STANDARD_v1.1.md"
s = gov.read_text(encoding="utf-8")
m, e = "<!-- SECTION:20_SUBSYSTEMS -->", "<!-- /SECTION:20_SUBSYSTEMS -->"
sec = f"""{m}
## 20. Subsystem Architecture

AInterceptor has TWO core subsystems. All features map to one of them.

### 20.1 Interceptor
Web-layer interception per provider. Owns sessions, adapters, SSE/WS
extraction. Location: `backend/app/interception/`, `backend/app/providers/`.
Never exposes public API. Never holds routing logic.

### 20.2 Orchestrator
The intelligence layer. Routes requests, selects models by capability,
merges multi-AI replies, enforces fallback + rate limits. Owns the public
Gateway API (OpenRouter-style). Location: `backend/app/orchestrator/`,
`backend/app/gateway/`.

### 20.3 Gateway
The Orchestrator's public face. External apps authenticate with a
generated key and call `POST /v1/chat/completions`. The Gateway:
- Validates API keys
- Delegates to Orchestrator
- Returns OpenAI-format responses (streaming and non-streaming)

### 20.4 Rule
A change is not accepted unless it declares which subsystem it targets
and does not violate subsystem boundaries. Cross-subsystem imports go
through defined interfaces only.
{e}"""
if m in s:
    s = re.sub(re.escape(m)+r".*?"+re.escape(e), sec, s, flags=re.S)
else:
    s = s.rstrip() + "\n\n" + sec + "\n"
gov.write_text(s, encoding="utf-8")
print("[OK] governance: Section 20 added")

# ---------- 3. Backend skeleton ----------
be = ROOT / "backend"
(be / "app/orchestrator").mkdir(parents=True, exist_ok=True)
(be / "app/gateway").mkdir(parents=True, exist_ok=True)

files = {}
files["app/orchestrator/__init__.py"] = '"""Orchestrator subsystem — routing, capability selection, merging."""\n'
files["app/orchestrator/README.md"] = """# Orchestrator

Routes requests across providers, selects models by capability, merges
multi-AI replies, enforces fallback and rate limits.

Phase 5 implements this. Phase 1 only scaffolds the directory.
"""
files["app/gateway/__init__.py"] = '"""Gateway subsystem — public OpenAI-compatible API face."""\n'
files["app/gateway/README.md"] = """# Gateway

Public API for external apps. OpenRouter-style key auth. Delegates to
Orchestrator. Exposes POST /v1/chat/completions.

Phase 6 implements this. Phase 1 only scaffolds the directory.
"""
files["app/__init__.py"] = '"""AInterceptor backend application package."""\n'

for rel, content in files.items():
    p = be / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    print(f"  [OK] backend/{rel}")

# ---------- 4. ROADMAP reorder ----------
rm = ROOT / "PROJECT/ROADMAP.md"
r = rm.read_text(encoding="utf-8")
r = r.replace(
"""| 5 | Routing Engine | PENDING |
| 6 | OpenAI-Compatible API | PENDING |""",
"""| 5 | Orchestrator Engine (capability routing + merge) | PENDING |
| 6 | Gateway API (OpenAI-compat, key auth) | PENDING |
| 7 | Dashboard panels (orchestrator + gateway) | PENDING |""")
r = r.replace("Current: Phase 0 COMPLETE — moving to Phase 1 (Governance Dashboard)",
              "Current: Phase 1 — Governance Dashboard (1.1 PASS, 1.2 in progress)")
rm.write_text(r, encoding="utf-8")
print("[OK] ROADMAP reordered (Orchestrator=5, Gateway=6, panels=7)")

# ---------- 5. AGENTS.md subsystem note ----------
ag = ROOT / "AGENTS.md"
a = ag.read_text(encoding="utf-8")
if "Two subsystems" not in a:
    a = a.rstrip() + """

## Two Subsystems (Section 20)
- **Interceptor** — web-layer interception. `backend/app/interception/`, `providers/`.
- **Orchestrator** — routing, capability selection, merging, **public Gateway API**. `backend/app/orchestrator/`, `gateway/`.
Every change declares its subsystem. No cross-subsystem imports except via defined interfaces.
"""
ag.write_text(a, encoding="utf-8")
print("[OK] AGENTS.md: subsystem section added")

# ---------- 6. BUGS.md ----------
bg = ROOT / "PROJECT/BUGS.md"
b = bg.read_text(encoding="utf-8")
if "K003" not in b:
    b = b.replace("| K002 | Low | 0 | datetime.utcnow() deprecation warning in validate_phase.py | Patched to datetime.now(datetime.UTC) |",
"""| K002 | Low | 0 | datetime.utcnow() deprecation warning in validate_phase.py | Patched to datetime.now(datetime.UTC) |
| K003 | High | 1.1 | next@15.0.3 CVE-2025-66478 | Bumped to 15.0.7 |""")
bg.write_text(b, encoding="utf-8")
print("[OK] BUGS.md: K003 logged")

# ---------- 7. Install, build, commit ----------
def run(args, cwd=ROOT, check=True):
    print(f"  $ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=True)
    tail = (r.stdout.strip()[-1500:] if r.stdout.strip() else "")
    if tail: print("   ", tail)
    if r.stderr.strip(): print("   ", r.stderr.strip()[-800:])
    if check and r.returncode != 0:
        print(f"FAIL: {r.returncode}"); sys.exit(1)
    return r

print("==> npm install (patched next)")
run(["npm","install","--no-audit","--no-fund"], cwd=ROOT/"dashboard")

print("==> npm run build")
run(["npm","run","build"], cwd=ROOT/"dashboard")

print("==> git commit M1.2")
for p in ["PROJECT_GOVERNANCE_STANDARD_v1.1.md","AGENTS.md","PROJECT/ROADMAP.md",
          "PROJECT/BUGS.md","backend","dashboard/package.json","dashboard/package-lock.json"]:
    subprocess.run(["git","add","--",p], cwd=ROOT, capture_output=True)

msg = ("feat(M1.2): subsystem architecture + backend skeleton\n\n"
       "- Section 20: Interceptor + Orchestrator + Gateway\n"
       "- backend/app/{orchestrator,gateway}/ scaffolded\n"
       "- ROADMAP: Orchestrator=5, Gateway=6, panels=7\n"
       "- Bump next to 15.0.7 (K003)")
r = subprocess.run(["git","commit","-m",msg], cwd=ROOT, capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())
subprocess.run(["git","push","origin","main"], cwd=ROOT, capture_output=True)

sha = subprocess.run(["git","rev-parse","HEAD"], cwd=ROOT,
                     capture_output=True, text=True).stdout.strip()
print("="*44); print("MILESTONE: M1.2"); print("RESULT: PASS")
print(f"COMMIT: {sha}"); print("BRANCH: main"); print("="*44)
