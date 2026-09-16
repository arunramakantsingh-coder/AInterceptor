import pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if not (ROOT / ".git").exists():
    ROOT = pathlib.Path(r"C:\Projects\AInterceptor")
DASH = ROOT / "dashboard"

files = {}

files["lib/ui.tsx"] = """export const S = {
  page: { maxWidth: 1000, margin: "0 auto", padding: "2rem" } as const,
  header: { borderBottom: "1px solid #30363d", paddingBottom: "1rem", marginBottom: "1.5rem" } as const,
  nav: { display: "flex", gap: "1rem", marginTop: "0.5rem", flexWrap: "wrap" as const } as const,
  link: { color: "#58a6ff", textDecoration: "none" } as const,
  card: { padding: "0.75rem", border: "1px solid #30363d", borderRadius: 6,
          marginBottom: "0.5rem", background: "#161b22" } as const,
  mono: { fontFamily: "monospace" } as const,
  muted: { color: "#8b949e" } as const,
  red: { color: "#f85149" } as const,
  green: { color: "#3fb950" } as const,
  yellow: { color: "#d29922" } as const,
  table: { borderCollapse: "collapse" as const, width: "100%", marginTop: "0.5rem" },
  th: { textAlign: "left" as const, borderBottom: "1px solid #30363d",
        padding: "0.4rem 0.6rem", background: "#161b22" },
  td: { borderBottom: "1px solid #21262d", padding: "0.4rem 0.6rem" },
};

export function Nav() {
  return (
    <nav style={S.nav}>
      <a href="/" style={S.link}>Commits</a>
      <a href="/versions" style={S.link}>Versions</a>
      <a href="/compare" style={S.link}>Compare</a>
      <a href="/roadmap" style={S.link}>Roadmap</a>
      <a href="/bugs" style={S.link}>Bugs</a>
      <a href="/providers" style={S.link}>Providers</a>
      <a href="/status" style={S.link}>Status</a>
      <a href="/rollback" style={S.link}>Rollback</a>
    </nav>
  );
}

export function MdTable({ t }: { t: { headers: string[]; rows: string[][] } }) {
  return (
    <table style={S.table}>
      <thead><tr>{t.headers.map((h, i) => <th key={i} style={S.th}>{h}</th>)}</tr></thead>
      <tbody>
        {t.rows.map((r, i) => (
          <tr key={i}>{r.map((c, j) => <td key={j} style={S.td}>{c}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}
"""

files["lib/health.ts"] = """import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");

export type ProviderHealth = {
  name: string;
  subsystem: "Interceptor" | "Orchestrator" | "Gateway";
  status: "active" | "expiring" | "failed" | "not_implemented";
  phase: string;
  note: string;
};

const CATALOG: ProviderHealth[] = [
  { name: "Claude Web",     subsystem: "Interceptor",  status: "not_implemented", phase: "2", note: "Phase 2 PoC target" },
  { name: "Gemini Web",     subsystem: "Interceptor",  status: "not_implemented", phase: "3", note: "" },
  { name: "ChatGPT Web",    subsystem: "Interceptor",  status: "not_implemented", phase: "4", note: "" },
  { name: "DeepSeek Web",   subsystem: "Interceptor",  status: "not_implemented", phase: "4", note: "" },
  { name: "Qwen Web",       subsystem: "Interceptor",  status: "not_implemented", phase: "4", note: "" },
  { name: "Router Engine",  subsystem: "Orchestrator", status: "not_implemented", phase: "5", note: "capability routing + merge" },
  { name: "Gateway API",    subsystem: "Gateway",      status: "not_implemented", phase: "6", note: "OpenAI-compatible /v1/chat/completions" },
];

export function listProviderHealth(): ProviderHealth[] {
  return CATALOG;
}

export function readStatusBlock(): string {
  const p = path.join(ROOT, ".ai/CURRENT_TASK.md");
  try { return fs.readFileSync(p, "utf-8"); } catch { return "(missing .ai/CURRENT_TASK.md)"; }
}

export function readMilestoneTable(): { headers: string[]; rows: string[][] } | null {
  const md = (() => {
    try { return fs.readFileSync(path.join(ROOT, "PROJECT/ROADMAP.md"), "utf-8"); }
    catch { return ""; }
  })();
  const lines = md.split(/\\r?\\n/);
  for (let i = 0; i < lines.length; i++) {
    if (/^\\|\\s*Gate\\s*\\|/i.test(lines[i])) {
      const headers = lines[i].replace(/^\\||\\|$/g, "").split("|").map(s => s.trim());
      const rows: string[][] = [];
      let j = i + 2;
      while (j < lines.length && lines[j].trim().startsWith("|")) {
        rows.push(lines[j].replace(/^\\||\\|$/g, "").split("|").map(s => s.trim()));
        j++;
      }
      return { headers, rows };
    }
  }
  return null;
}
"""

files["app/providers/page.tsx"] = """import { listProviderHealth } from "@/lib/health";
import { S, Nav } from "@/lib/ui";

export const dynamic = "force-dynamic";

const color: Record<string,string> = {
  active: "#3fb950",
  expiring: "#d29922",
  failed: "#f85149",
  not_implemented: "#8b949e",
};

export default function ProvidersPage() {
  const list = listProviderHealth();
  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Provider Health</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>Interceptor + Orchestrator + Gateway readiness</p>
        <Nav />
      </header>

      <table style={S.table}>
        <thead>
          <tr>
            <th style={S.th}>Provider</th>
            <th style={S.th}>Subsystem</th>
            <th style={S.th}>Phase</th>
            <th style={S.th}>Status</th>
            <th style={S.th}>Note</th>
          </tr>
        </thead>
        <tbody>
          {list.map(p => (
            <tr key={p.name}>
              <td style={S.td}>{p.name}</td>
              <td style={S.td}>{p.subsystem}</td>
              <td style={S.td}>{p.phase}</td>
              <td style={{ ...S.td, color: color[p.status] }}>● {p.status}</td>
              <td style={{ ...S.td, ...S.muted }}>{p.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
"""

files["app/status/page.tsx"] = """import { readStatusBlock, readMilestoneTable } from "@/lib/health";
import { S, Nav, MdTable } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default function StatusPage() {
  const status = readStatusBlock();
  const gates = readMilestoneTable();

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Project Status</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>Live from .ai/CURRENT_TASK.md + PROJECT/ROADMAP.md</p>
        <Nav />
      </header>

      <h2 style={{ fontSize: "1rem", ...S.muted, textTransform: "uppercase" }}>Current Task</h2>
      <pre style={{ ...S.mono, padding: "0.75rem", background: "#161b22",
                    border: "1px solid #30363d", borderRadius: 6,
                    whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
        {status}
      </pre>

      <h2 style={{ fontSize: "1rem", ...S.muted, textTransform: "uppercase", marginTop: "1.5rem" }}>
        Milestone Gate
      </h2>
      {gates ? <MdTable t={gates} /> : <p style={S.muted}>No gate table found.</p>}
    </main>
  );
}
"""

for rel, content in files.items():
    p = DASH / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    print(f"  [OK] dashboard/{rel}")

def run(args, cwd=DASH, check=True):
    print(f"  $ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=True)
    if r.stdout.strip(): print("   ", r.stdout.strip()[-2000:])
    if r.stderr.strip(): print("   ", r.stderr.strip()[-1500:])
    if check and r.returncode != 0:
        print(f"FAIL: {r.returncode}"); sys.exit(1)
    return r

print("==> npm run build")
run(["npm","run","build"])

subprocess.run(["git","add","dashboard"], cwd=ROOT, capture_output=True)
msg = ("feat(M1.5): provider health + status panels\n\n"
       "- /providers: subsystem readiness table\n"
       "- /status: current task + milestone gate\n"
       "- Closes Phase 1 governance dashboard")
r = subprocess.run(["git","commit","-m",msg], cwd=ROOT, capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())
subprocess.run(["git","push","origin","main"], cwd=ROOT, capture_output=True)

sha = subprocess.run(["git","rev-parse","HEAD"], cwd=ROOT,
                     capture_output=True, text=True).stdout.strip()
ls = subprocess.run(["git","ls-remote","origin","refs/heads/main"],
                    cwd=ROOT, capture_output=True, text=True).stdout
print("="*44)
print("MILESTONE: M1.5")
print("RESULT:", "PASS" if sha in ls else "BLOCKED")
print("COMMIT:", sha)
print("="*44)
