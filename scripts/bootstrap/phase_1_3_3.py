import pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if not (ROOT / ".git").exists():
    ROOT = pathlib.Path(r"C:\Projects\AInterceptor")
DASH = ROOT / "dashboard"

github = """const OWNER = process.env.GITHUB_OWNER || "arunramakantsingh-coder";
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

export type CompareCommit = {
  sha: string; short: string; message: string; author: string; date: string;
};

export type CompareFile = {
  filename: string; status: string; additions: number; deletions: number;
};

export type CompareResult = {
  status: string;
  ahead_by: number;
  behind_by: number;
  total_commits: number;
  commits: CompareCommit[];
  files: CompareFile[];
};

async function gh(path: string) {
  const res = await fetch(`https://api.github.com${path}`, {
    headers: H, cache: "no-store"
  });
  if (!res.ok) throw new Error(`GitHub ${res.status} ${path}`);
  return res.json();
}

export async function listCommits(limit = 30): Promise<Commit[]> {
  const data: any[] = await gh(`/repos/${OWNER}/${REPO}/commits?per_page=${limit}`);
  return data.map((c: any) => ({
    sha: c.sha, short: c.sha.slice(0,7),
    message: (c.commit.message||"").split("\\n")[0],
    author: c.commit.author?.name||"unknown",
    date: c.commit.author?.date||"", url: c.html_url,
  }));
}

export async function getCommit(sha: string): Promise<CommitDetail> {
  const c: any = await gh(`/repos/${OWNER}/${REPO}/commits/${sha}`);
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

export async function compareCommits(base: string, head: string): Promise<CompareResult> {
  const c: any = await gh(`/repos/${OWNER}/${REPO}/compare/${base}...${head}`);
  const commits: CompareCommit[] = (c.commits||[]).map((x: any) => ({
    sha: x.sha, short: x.sha.slice(0,7),
    message: (x.commit.message||"").split("\\n")[0],
    author: x.commit.author?.name||"unknown",
    date: x.commit.author?.date||"",
  }));
  const files: CompareFile[] = (c.files||[]).map((f: any) => ({
    filename: f.filename, status: f.status,
    additions: f.additions||0, deletions: f.deletions||0,
  }));
  return {
    status: c.status,
    ahead_by: c.ahead_by, behind_by: c.behind_by,
    total_commits: c.total_commits,
    commits, files,
  };
}

export async function listTags(): Promise<Tag[]> {
  const t: any[] = await gh(`/repos/${OWNER}/${REPO}/tags?per_page=50`);
  return t.map((x: any) => ({ name: x.name, sha: x.commit.sha, url: x.commit.url }));
}
"""

(DASH / "lib/github.ts").write_text(github, encoding="utf-8", newline="\n")
print("[OK] lib/github.ts rewritten with explicit types")

compare = """import { compareCommits, type CompareResult } from "@/lib/github";
import { S, Nav } from "@/lib/ui";

export const dynamic = "force-dynamic";

function Results({ d }: { d: CompareResult }) {
  return (
    <>
      <div style={S.card}>
        <strong>Status:</strong> {d.status} · {d.ahead_by} ahead · {d.behind_by} behind
        · {d.total_commits} commits
      </div>

      <h2 style={{ fontSize: "1rem", ...S.muted, textTransform: "uppercase", marginTop: "1.5rem" }}>
        Commits ({d.commits.length})
      </h2>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {d.commits.map((c) => (
          <li key={c.sha} style={S.card}>
            <a href={`/commit/${c.sha}`} style={{ ...S.link, ...S.mono }}>{c.short}</a>
            <span style={{ marginLeft: "0.75rem" }}>{c.message}</span>
          </li>
        ))}
      </ul>

      <h2 style={{ fontSize: "1rem", ...S.muted, textTransform: "uppercase", marginTop: "1.5rem" }}>
        Files ({d.files.length})
      </h2>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {d.files.map((f) => (
          <li key={f.filename} style={S.card}>
            <span style={{ ...S.mono, fontSize: "0.8rem", ...S.muted }}>[{f.status}]</span>
            <span style={{ ...S.mono, marginLeft: "0.5rem" }}>{f.filename}</span>
            <span style={{ marginLeft: "0.75rem", ...S.green }}>+{f.additions}</span>
            <span style={{ marginLeft: "0.25rem", ...S.red }}>-{f.deletions}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

export default async function ComparePage({
  searchParams,
}: { searchParams: Promise<{ base?: string; head?: string }> }) {
  const { base = "HEAD~5", head = "main" } = await searchParams;
  let data: CompareResult | null = null;
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
      {data && <Results d={data} />}
    </main>
  );
}
"""

(DASH / "app/compare/page.tsx").write_text(compare, encoding="utf-8", newline="\n")
print("[OK] app/compare/page.tsx rewritten")

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
msg = "fix(M1.3.3): explicit CompareResult type; strict-mode clean"
r = subprocess.run(["git","commit","-m",msg], cwd=ROOT, capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())
subprocess.run(["git","push","origin","main"], cwd=ROOT, capture_output=True)

sha = subprocess.run(["git","rev-parse","HEAD"], cwd=ROOT,
                     capture_output=True, text=True).stdout.strip()
ls = subprocess.run(["git","ls-remote","origin","refs/heads/main"],
                    cwd=ROOT, capture_output=True, text=True).stdout
print("="*44)
print("MILESTONE: M1.3.3")
print("RESULT:", "PASS" if sha in ls else "BLOCKED")
print("COMMIT:", sha)
print("="*44)
