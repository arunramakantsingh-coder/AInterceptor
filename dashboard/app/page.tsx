import { listCommits } from "@/lib/github";

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
