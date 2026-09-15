import { getCommit } from "@/lib/github";
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
