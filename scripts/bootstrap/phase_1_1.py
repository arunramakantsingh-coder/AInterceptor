import pathlib, subprocess, sys, datetime

ROOT = pathlib.Path(__file__).resolve().parent
DASH = ROOT / "dashboard"
DASH.mkdir(exist_ok=True)

files = {}

files["package.json"] = """{
  "name": "ainterceptor-dashboard",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev -p 4000",
    "build": "next build",
    "start": "next start -p 4000",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "15.0.3",
    "react": "19.0.0-rc-66855b96-20241106",
    "react-dom": "19.0.0-rc-66855b96-20241106"
  },
  "devDependencies": {
    "@types/node": "22.9.0",
    "@types/react": "18.3.12",
    "typescript": "5.6.3"
  }
}
"""

files["next.config.mjs"] = """const nextConfig = { reactStrictMode: true };
export default nextConfig;
"""

files["tsconfig.json"] = """{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
"""

files[".env.local.example"] = """# Optional: set a GitHub PAT for private-repo access or higher rate limits
GITHUB_TOKEN=
GITHUB_OWNER=arunramakantsingh-coder
GITHUB_REPO=AInterceptor
"""

files[".gitignore"] = """node_modules/
.next/
out/
.env.local
next-env.d.ts
"""

files["lib/github.ts"] = """const OWNER = process.env.GITHUB_OWNER || "arunramakantsingh-coder";
const REPO  = process.env.GITHUB_REPO  || "AInterceptor";
const TOKEN = process.env.GITHUB_TOKEN;

export type Commit = {
  sha: string;
  short: string;
  message: string;
  author: string;
  date: string;
  url: string;
};

export async function listCommits(limit = 30): Promise<Commit[]> {
  const headers: Record<string,string> = { "Accept": "application/vnd.github+json" };
  if (TOKEN) headers["Authorization"] = `Bearer ${TOKEN}`;

  const res = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/commits?per_page=${limit}`,
    { headers, next: { revalidate: 60 } }
  );
  if (!res.ok) throw new Error(`GitHub API ${res.status}`);
  const data = await res.json();
  return data.map((c: any) => ({
    sha: c.sha,
    short: c.sha.slice(0,7),
    message: (c.commit.message || "").split("\\n")[0],
    author: c.commit.author?.name || "unknown",
    date: c.commit.author?.date || "",
    url: c.html_url,
  }));
}
"""

files["app/layout.tsx"] = """export const metadata = { title: "AInterceptor — Governance" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#0d1117", color: "#e6edf3" }}>
        {children}
      </body>
    </html>
  );
}
"""

files["app/page.tsx"] = """import { listCommits } from "@/lib/github";

export const revalidate = 30;

export default async function Page() {
  let commits: Awaited<ReturnType<typeof listCommits>> = [];
  let err = "";
  try { commits = await listCommits(30); } catch (e: any) { err = e.message; }

  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: "2rem" }}>
      <header style={{ borderBottom: "1px solid #30363d", paddingBottom: "1rem", marginBottom: "1.5rem" }}>
        <h1 style={{ margin: 0 }}>AInterceptor — Governance</h1>
        <p style={{ color: "#8b949e", margin: "0.25rem 0 0" }}>
          Phase 1.1 · Commit Explorer (read-only)
        </p>
      </header>

      {err && <p style={{ color: "#f85149" }}>GitHub error: {err}</p>}

      <h2 style={{ fontSize: "1rem", color: "#8b949e", textTransform: "uppercase" }}>
        Recent Commits ({commits.length})
      </h2>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {commits.map(c => (
          <li key={c.sha} style={{
            padding: "0.75rem",
            border: "1px solid #30363d",
            borderRadius: 6,
            marginBottom: "0.5rem",
            background: "#161b22"
          }}>
            <a href={c.url} style={{ color: "#58a6ff", fontFamily: "monospace", textDecoration: "none" }}>
              {c.short}
            </a>
            <span style={{ marginLeft: "0.75rem" }}>{c.message}</span>
            <div style={{ color: "#8b949e", fontSize: "0.85rem", marginTop: "0.25rem" }}>
              {c.author} · {new Date(c.date).toLocaleString()}
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
"""

created = 0
for rel, content in files.items():
    p = DASH / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists() or p.read_text(encoding="utf-8") != content:
        p.write_text(content, encoding="utf-8", newline="\n")
        created += 1
        print(f"  [OK] dashboard/{rel}")

print(f"[OK] {created} files written")

def run(args, cwd=DASH, check=True):
    print(f"  $ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=True)
    if r.stdout.strip(): print("   ", r.stdout.strip()[-2000:])
    if r.stderr.strip(): print("   ", r.stderr.strip()[-2000:])
    if check and r.returncode != 0:
        print(f"FAIL: {r.returncode}"); sys.exit(1)
    return r

print("==> npm install")
run(["npm", "install", "--no-audit", "--no-fund"])

print("==> npm run build")
run(["npm", "run", "build"])

print("==> git commit")
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
git(["add","dashboard"])
msg = "feat(phase-1.1): dashboard skeleton with commit explorer\n\nNext.js 15 + TS dashboard. Reads GitHub commits API. Build verified."
r = git(["commit","-m",msg])
print(r.stdout.strip() or r.stderr.strip())
git(["push","origin","main"])

print("="*44); print("MILESTONE: Phase 1.1"); print("RESULT: PASS")
print("NEXT: run `cd dashboard; npm run dev` -> http://localhost:4000")
print("="*44)
