import { compareCommits, type CompareResult } from "@/lib/github";
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
