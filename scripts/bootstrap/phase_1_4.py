import pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if not (ROOT / ".git").exists():
    ROOT = pathlib.Path(r"C:\Projects\AInterceptor")
DASH = ROOT / "dashboard"

files = {}

files["lib/repo.ts"] = """import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");

export function readRepoFile(rel: string): string {
  const p = path.join(ROOT, rel);
  try { return fs.readFileSync(p, "utf-8"); } catch { return ""; }
}

export type Table = { headers: string[]; rows: string[][] };
export type Section = { heading: string; level: number; table?: Table; body?: string };

function splitRow(line: string): string[] {
  return line.trim().replace(/^\\||\\|$/g, "").split("|").map(s => s.trim());
}

export function parseMarkdown(md: string): Section[] {
  const sections: Section[] = [];
  let current: Section | null = null;
  const lines = md.split(/\\r?\\n/);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const h = /^(#{1,6})\\s+(.*)$/.exec(line);
    if (h) {
      if (current) sections.push(current);
      current = { heading: h[2].trim(), level: h[1].length };
      continue;
    }
    // table detection
    if (line.trim().startsWith("|") && current) {
      const next = lines[i+1] || "";
      if (/^\\|?[\\s\\-:|]+\\|?\\s*$/.test(next) && next.includes("-")) {
        const headers = splitRow(line);
        const rows: string[][] = [];
        let j = i + 2;
        while (j < lines.length && lines[j].trim().startsWith("|")) {
          rows.push(splitRow(lines[j]));
          j++;
        }
        if (!current.table) current.table = { headers, rows };
        i = j - 1;
      }
    }
  }
  if (current) sections.push(current);
  return sections;
}

export function currentStatus(): string {
  const md = readRepoFile("PROJECT/ROADMAP.md");
  const m = /Current:\\s*(.+)/.exec(md);
  return m ? m[1] : "(no status line)";
}
"""

files["lib/actions.ts"] = """"use server";

import { execSync } from "node:child_process";
import path from "node:path";
import { revalidatePath } from "next/cache";

const ROOT = path.resolve(process.cwd(), "..");

function git(args: string): string {
  return execSync(`git ${args}`, { cwd: ROOT, encoding: "utf-8" }).trim();
}

export type RevertResult = { ok: boolean; log: string };

export async function revertCommit(sha: string): Promise<RevertResult> {
  const log: string[] = [];
  try {
    if (!/^[0-9a-f]{7,40}$/.test(sha)) throw new Error("invalid sha");
    log.push(`target: ${sha}`);
    log.push(git(`revert --no-edit ${sha}`));
    log.push(git("push origin main"));
    revalidatePath("/");
    revalidatePath("/rollback");
    return { ok: true, log: log.join("\\n") };
  } catch (e: any) {
    log.push(`ERROR: ${e.message}`);
    try { git("revert --abort"); } catch {}
    return { ok: false, log: log.join("\\n") };
  }
}
"""

files["lib/ui.tsx"] = """export const S = {
  page: { maxWidth: 1000, margin: "0 auto", padding: "2rem" } as const,
  header: { borderBottom: "1px solid #30363d", paddingBottom: "1rem", marginBottom: "1.5rem" } as const,
  nav: { display: "flex", gap: "1rem", marginTop: "0.5rem" } as const,
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

files["app/roadmap/page.tsx"] = """import { readRepoFile, parseMarkdown, currentStatus } from "@/lib/repo";
import { S, Nav, MdTable } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default function RoadmapPage() {
  const md = readRepoFile("PROJECT/ROADMAP.md");
  const sections = parseMarkdown(md);
  const status = currentStatus();

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Roadmap</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>Source: PROJECT/ROADMAP.md</p>
        <Nav />
      </header>

      <div style={S.card}><strong>Current:</strong> {status}</div>

      {sections.map((s, i) => (
        <section key={i} style={{ marginTop: "1.5rem" }}>
          <h2 style={{ fontSize: "1.1rem" }}>{s.heading}</h2>
          {s.table && <MdTable t={s.table} />}
        </section>
      ))}
    </main>
  );
}
"""

files["app/bugs/page.tsx"] = """import { readRepoFile, parseMarkdown } from "@/lib/repo";
import { S, Nav, MdTable } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default function BugsPage() {
  const md = readRepoFile("PROJECT/BUGS.md");
  const sections = parseMarkdown(md);

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Bugs</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>Source: PROJECT/BUGS.md</p>
        <Nav />
      </header>

      {sections.map((s, i) => (
        <section key={i} style={{ marginTop: "1.5rem" }}>
          <h2 style={{ fontSize: "1.1rem" }}>{s.heading}</h2>
          {s.table ? <MdTable t={s.table} /> : <p style={S.muted}>(no table)</p>}
        </section>
      ))}
    </main>
  );
}
"""

files["app/rollback/page.tsx"] = """import { listCommits } from "@/lib/github";
import { S, Nav } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function RollbackPage() {
  let commits: Awaited<ReturnType<typeof listCommits>> = [];
  let err = "";
  try { commits = await listCommits(30); } catch (e: any) { err = e.message; }

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Rollback</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>
          Safe rollback via <strong>git revert</strong>. History is preserved.
        </p>
        <Nav />
      </header>

      <p style={{ ...S.yellow }}>
        ⚠ Revert creates a NEW commit that undoes the target. Never force-pushes.
      </p>

      {err && <p style={S.red}>GitHub error: {err}</p>}

      <ul style={{ listStyle: "none", padding: 0 }}>
        {commits.map(c => (
          <li key={c.sha} style={S.card}>
            <a href={`/commit/${c.sha}`} style={{ ...S.link, ...S.mono }}>{c.short}</a>
            <span style={{ marginLeft: "0.75rem" }}>{c.message}</span>
            <div style={{ ...S.muted, fontSize: "0.85rem", marginTop: "0.25rem" }}>
              {c.author} · {new Date(c.date).toLocaleString()}
            </div>
            <div style={{ marginTop: "0.5rem" }}>
              <a href={`/rollback/${c.sha}`} style={{ ...S.link, ...S.red }}>
                Revert this commit →
              </a>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
"""

files["app/rollback/[sha]/page.tsx"] = """import { getCommit } from "@/lib/github";
import { S, Nav } from "@/lib/ui";
import RevertButton from "./RevertButton";

export const dynamic = "force-dynamic";

export default async function RollbackConfirm({
  params,
}: { params: Promise<{ sha: string }> }) {
  const { sha } = await params;
  const c = await getCommit(sha);

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Confirm Revert</h1>
        <Nav />
      </header>

      <div style={S.card}>
        <div style={S.mono}>{c.sha}</div>
        <div style={{ marginTop: "0.5rem" }}>{c.message}</div>
        <div style={{ ...S.muted, marginTop: "0.25rem", fontSize: "0.85rem" }}>
          {c.author} · {new Date(c.date).toLocaleString()}
        </div>
      </div>

      <p style={S.yellow}>
        A new commit will be created that reverses this commit's changes and
        pushed to <span style={S.mono}>origin/main</span>.
      </p>

      <RevertButton sha={sha} />
    </main>
  );
}
"""

files["app/rollback/[sha]/RevertButton.tsx"] = """"use client";
import { useState } from "react";
import { revertCommit } from "@/lib/actions";
import { S } from "@/lib/ui";

export default function RevertButton({ sha }: { sha: string }) {
  const [state, setState] = useState<"idle"|"busy"|"done"|"error">("idle");
  const [log, setLog] = useState("");

  async function go() {
    setState("busy");
    const r = await revertCommit(sha);
    setLog(r.log);
    setState(r.ok ? "done" : "error");
  }

  return (
    <>
      <button
        onClick={go}
        disabled={state === "busy" || state === "done"}
        style={{ padding: "0.6rem 1.2rem", background: state === "error" ? "#f85149" : "#da3633",
                 color: "#fff", border: "none", borderRadius: 4, cursor: "pointer",
                 fontSize: "1rem" }}
      >
        {state === "idle" && `Revert ${sha.slice(0,7)}`}
        {state === "busy" && "Reverting…"}
        {state === "done" && "✓ Revert complete"}
        {state === "error" && "✗ Failed — see log"}
      </button>

      {log && (
        <pre style={{ ...S.mono, marginTop: "1rem", padding: "0.75rem",
                      background: "#161b22", border: "1px solid #30363d",
                      borderRadius: 6, whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
          {log}
        </pre>
      )}

      {state === "done" && (
        <p style={{ ...S.green, marginTop: "0.5rem" }}>
          → <a href="/" style={S.link}>Back to commits</a>
        </p>
      )}
    </>
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
msg = ("feat(M1.4): rollback via revert + roadmap + bugs trackers\n\n"
       "- /roadmap parses PROJECT/ROADMAP.md\n"
       "- /bugs parses PROJECT/BUGS.md\n"
       "- /rollback + /rollback/[sha] safe git revert workflow")
r = subprocess.run(["git","commit","-m",msg], cwd=ROOT, capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())
subprocess.run(["git","push","origin","main"], cwd=ROOT, capture_output=True)

sha = subprocess.run(["git","rev-parse","HEAD"], cwd=ROOT,
                     capture_output=True, text=True).stdout.strip()
ls = subprocess.run(["git","ls-remote","origin","refs/heads/main"],
                    cwd=ROOT, capture_output=True, text=True).stdout
print("="*44)
print("MILESTONE: M1.4")
print("RESULT:", "PASS" if sha in ls else "BLOCKED")
print("COMMIT:", sha)
print("="*44)
print("NEXT: cd dashboard; npm run dev -> http://localhost:4000")
