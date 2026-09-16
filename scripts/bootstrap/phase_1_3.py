import pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if not (ROOT / ".git").exists():
    ROOT = pathlib.Path(r"C:\Projects\AInterceptor")
DASH = ROOT / "dashboard"

files = {}

# Extend lib/github.ts with detail + compare + tags
files["lib/github.ts"] = """const OWNER = process.env.GITHUB_OWNER || "arunramakantsingh-coder";
const REPO  = process.env.GITHUB_REPO  || "AInterceptor";
const TOKEN = process.env.GITHUB_TOKEN;

const H: Record<string,string> = { "Accept": "application/vnd.github+json" };
if (TOKEN) H["Authorization"] = `Bearer ${TOKEN}`;

export type Commit = {
  sha: string; short: string; message: string;
  author: string; date: string; url: string;
};

export type CommitDetail = Commit & {
  body: string;
  files: { filename: string; status: string; additions: number; deletions: number; patch?: string }[];
};

export type Tag = { name: string; sha: string; url: string };

async function gh(path: string) {
  const res = await fetch(`https://api.github.com${path}`, {
    headers: H, next: { revalidate: 60 }
  });
  if (!res.ok) throw new Error(`GitHub ${res.status} ${path}`);
  return res.json();
}

export async function listCommits(limit = 30): Promise<Commit[]> {
  const data = await gh(`/repos/${OWNER}/${REPO}/commits?per_page=${limit}`);
  return data.map((c: any) => ({
    sha: c.sha, short: c.sha.slice(0,7),
    message: (c.commit.message||"").split("\\n")[0],
    author: c.commit.author?.name||"unknown",
    date: c.commit.author?.date||"", url: c.html_url,
  }));
}

export async function getCommit(sha: string): Promise<CommitDetail> {
  const c = await gh(`/repos/${OWNER}/${REPO}/commits/${sha}`);
  return {
    sha: c.sha, short: c.sha.slice(0,7),
    message: (c.commit.message||"").split("\\n")[0],
    body: c.commit.message||"",
    author: c.commit.author?.name||"unknown",
    date: c.commit.author?.date||"", url: c.html_url,
    files: (c.files||[]).map((f: any) => ({
      filename: f.filename, status: f.status,
      additions: f.additions||0, deletions: f.deletions||0,
      patch: f.patch,
    })),
  };
}

export async function compareCommits(base: string, head: string) {
  const c = await gh(`/repos/${OWNER}/${REPO}/compare/${base}...${head}`);
  return {
    status: c.status,
    ahead_by: c.ahead_by, behind_by: c.behind_by, total_commits: c.total_commits,
    commits: (c.commits||[]).map((x: any) => ({
      sha: x.sha, short: x.sha.slice(0,7),
      message: (x.commit.message||"").split("\\n")[0],
      author: x.commit.author?.name||"unknown",
      date: x.commit.author?.date||"",
    })),
    files: (c.files||[]).map((f: any) => ({
      filename: f.filename, status: f.status,
      additions: f.additions||0, deletions: f.deletions||0,
    })),
  };
}

export async function listTags(): Promise<Tag[]> {
  const t = await gh(`/repos/${OWNER}/${REPO}/tags?per_page=50`);
  return t.map((x: any) => ({ name: x.name, sha: x.commit.sha, url: x.commit.url }));
}
"""

# Shared UI helpers
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
};

export function Nav() {
  return (
    <nav style={S.nav}>
      <a href="/" style={S.link}>Commits</a>
      <a href="/versions" style={S.link}>Versions</a>
      <a href="/compare" style={S.link}>Compare</a>
    </nav>
  );
}
"""

# Home page (updated nav)
files["app/page.tsx"] = """import { listCommits } from "@/lib/github";
import { S, Nav } from "@/lib/ui";

export const revalidate = 30;

export default async function Page() {
  let commits: Awaited<ReturnType<typeof listCommits>> = [];
  let err = "";
  try { commits = await listCommits(30); } catch (e: any) { err = e.message; }

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>AInterceptor — Governance</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>Phase 1.3 · Commit Explorer</p>
        <Nav />
      </header>

      {err && <p style={S.red}>GitHub error: {err}</p>}

      <h2 style={{ fontSize: "1rem", ...S.muted, textTransform: "uppercase" }}>
        Recent Commits ({commits.length})
      </h2>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {commits.map(c => (
          <li key={c.sha} style={S.card}>
            <a href={`/commit/${c.sha}`} style={{ ...S.link, ...S.mono }}>{c.short}</a>
            <span style={{ marginLeft: "0.75rem" }}>{c.message}</span>
            <div style={{ ...S.muted, fontSize: "0.85rem", marginTop: "0.25rem" }}>
              {c.author} · {new Date(c.date).toLocaleString()}
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
"""

# Commit detail page
files["app/commit/[sha]/page.tsx"] = """import { getCommit } from "@/lib/github";
import { S, Nav } from "@/lib/ui";

export const revalidate = 60;

const statusColor: Record<string,string> = {
  added: "#3fb950", removed: "#f85149",
  modified: "#d29922", renamed: "#58a6ff",
};

export default async function CommitPage({ params }: { params: Promise<{ sha: string }> }) {
  const { sha } = await params;
  let c: Awaited<ReturnType<typeof getCommit>> | null = null;
  let err = "";
  try { c = await getCommit(sha); } catch (e: any) { err = e.message; }

  if (err) return <main style={S.page}><p style={S.red}>Error: {err}</p></main>;
  if (!c) return <main style={S.page}><p>Loading…</p></main>;

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Commit {c.short}</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>{c.message}</p>
        <Nav />
      </header>

      <div style={S.card}>
        <div style={S.mono}>{c.sha}</div>
        <div style={{ ...S.muted, marginTop: "0.5rem" }}>
          {c.author} · {new Date(c.date).toLocaleString()}
        </div>
        {c.body && c.body !== c.message && (
          <pre style={{ ...S.mono, whiteSpace: "pre-wrap", marginTop: "0.75rem", fontSize: "0.85rem" }}>
            {c.body}
          </pre>
        )}
      </div>

      <h2 style={{ fontSize: "1rem", ...S.muted, textTransform: "uppercase", marginTop: "1.5rem" }}>
        Files ({c.files.length})
      </h2>
      {c.files.map(f => (
        <div key={f.filename} style={S.card}>
          <div>
            <span style={{ color: statusColor[f.status] || S.muted.color, ...S.mono, fontSize: "0.8rem" }}>
              [{f.status}]
            </span>
            <span style={{ ...S.mono, marginLeft: "0.5rem" }}>{f.filename}</span>
            <span style={{ marginLeft: "0.75rem", ...S.green }}>+{f.additions}</span>
            <span style={{ marginLeft: "0.25rem", ...S.red }}>-{f.deletions}</span>
          </div>
          {f.patch && (
            <pre style={{ ...S.mono, fontSize: "0.78rem", background: "#0d1117",
                          padding: "0.5rem", borderRadius: 4, overflow: "auto",
                          marginTop: "0.5rem", maxHeight: 400 }}>
              {f.patch}
            </pre>
          )}
        </div>
      ))}
    </main>
  );
}
"""

# Versions (tags) page
files["app/versions/page.tsx"] = """import { listTags } from "@/lib/github";
import { S, Nav } from "@/lib/ui";

export const revalidate = 60;

export default async function VersionsPage() {
  let tags: Awaited<ReturnType<typeof listTags>> = [];
  let err = "";
  try { tags = await listTags(); } catch (e: any) { err = e.message; }

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Versions</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>Tagged releases</p>
        <Nav />
      </header>

      {err && <p style={S.red}>GitHub error: {err}</p>}
      {tags.length === 0 && !err && (
        <p style={S.muted}>No tags yet. Tag a commit to see versions here.</p>
      )}
      <ul style={{ listStyle: "none", padding: 0 }}>
        {tags.map(t => (
          <li key={t.name} style={S.card}>
            <strong>{t.name}</strong>
            <a href={`/commit/${t.sha}`} style={{ ...S.link, ...S.mono, marginLeft: "0.75rem" }}>
              {t.sha.slice(0,7)}
            </a>
            <div style={{ marginTop: "0.4rem", display: "flex", gap: "0.5rem" }}>
              <a href={`/compare?base=${t.sha}&head=main`} style={S.link}>Compare to main →</a>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
"""

# Compare page
files["app/compare/page.tsx"] = """import { compareCommits } from "@/lib/github";
import { S, Nav } from "@/lib/ui";

export const revalidate = 0;

export default async function ComparePage({
  searchParams,
}: { searchParams: Promise<{ base?: string; head?: string }> }) {
  const { base = "HEAD~5", head = "main" } = await searchParams;
  let data: Awaited<ReturnType<typeof compareCommits>> | null = null;
  let err = "";

  try {
    if (base && head) data = await compareCommits(base, head);
  } catch (e: any) { err = e.message; }

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Compare Commits</h1>
        <Nav />
      </header>

      <form method="get" style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <input name="base" defaultValue={base} placeholder="base SHA / ref"
               style={{ padding: "0.4rem", background: "#0d1117", color: "#e6edf3",
                        border: "1px solid #30363d", borderRadius: 4, flex: 1, ...S.mono }} />
        <span style={{ alignSelf: "center" }}>...</span>
        <input name="head" defaultValue={head} placeholder="head SHA / ref"
               style={{ padding: "0.4rem", background: "#0d1117", color: "#e6edf3",
                        border: "1px solid #30363d", borderRadius: 4, flex: 1, ...S.mono }} />
        <button type="submit" style={{ padding: "0.4rem 1rem", background: "#238636",
                                        color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
          Compare
        </button>
      </form>

      {err && <p style={S.red}>Error: {err}</p>}

      {data && (
        <>
          <div style={S.card}>
            <strong>Status:</strong> {data.status} · {data.ahead_by} ahead · {data.behind_by} behind
            · {data.total_commits} commits
          </div>

          <h2 style={{ fontSize: "1rem", ...S.muted, textTransform: "uppercase", marginTop: "1.5rem" }}>
            Commits ({data.commits.length})
          </h2>
          <ul style={{ listStyle: "none", padding: 0 }}>
            {data.commits.map(c => (
              <li key={c.sha} style={S.card}>
                <a href={`/commit/${c.sha}`} style={{ ...S.link, ...S.mono }}>{c.short}</a>
                <span style={{ marginLeft: "0.75rem" }}>{c.message}</span>
              </li>
            ))}
          </ul>

          <h2 style={{ fontSize: "1rem", ...S.muted, textTransform: "uppercase", marginTop: "1.5rem" }}>
            Files ({data.files.length})
          </h2>
          <ul style={{ listStyle: "none", padding: 0 }}>
            {data.files.map(f => (
              <li key={f.filename} style={S.card}>
                <span style={{ ...S.mono, fontSize: "0.8rem", ...S.muted }}>[{f.status}]</span>
                <span style={{ ...S.mono, marginLeft: "0.5rem" }}>{f.filename}</span>
                <span style={{ marginLeft: "0.75rem", ...S.green }}>+{f.additions}</span>
                <span style={{ marginLeft: "0.25rem", ...S.red }}>-{f.deletions}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
"""

# Write files
for rel, content in files.items():
    p = DASH / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    print(f"  [OK] dashboard/{rel}")

def run(args, cwd=DASH, check=True):
    print(f"  $ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=True)
    if r.stdout.strip(): print("   ", r.stdout.strip()[-1500:])
    if r.stderr.strip(): print("   ", r.stderr.strip()[-800:])
    if check and r.returncode != 0:
        print(f"FAIL: {r.returncode}"); sys.exit(1)
    return r

print("==> npm run build")
run(["npm","run","build"])

print("==> commit M1.3")
subprocess.run(["git","add","dashboard"], cwd=ROOT, capture_output=True)
msg = ("feat(M1.3): commit detail, versions, and compare views\n\n"
       "- /commit/[sha] — full diff view\n"
       "- /versions — tagged releases\n"
       "- /compare — two-ref comparison\n"
       "- shared Nav + UI helpers")
r = subprocess.run(["git","commit","-m",msg], cwd=ROOT, capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())
subprocess.run(["git","push","origin","main"], cwd=ROOT, capture_output=True)

sha = subprocess.run(["git","rev-parse","HEAD"], cwd=ROOT,
                     capture_output=True, text=True).stdout.strip()
ls = subprocess.run(["git","ls-remote","origin","refs/heads/main"],
                    cwd=ROOT, capture_output=True, text=True).stdout
print("="*44)
print("MILESTONE: M1.3")
print("RESULT:", "PASS" if sha in ls else "BLOCKED")
print("COMMIT:", sha)
print("="*44)
print("NEXT: cd dashboard; npm run dev -> http://localhost:4000")
