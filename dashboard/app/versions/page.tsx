import { listTags } from "@/lib/github";
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
