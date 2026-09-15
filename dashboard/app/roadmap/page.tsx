import { readRepoFile, parseMarkdown, currentStatus } from "@/lib/repo";
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
