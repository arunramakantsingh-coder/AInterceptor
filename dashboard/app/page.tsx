import { listCommits } from "@/lib/github";
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
