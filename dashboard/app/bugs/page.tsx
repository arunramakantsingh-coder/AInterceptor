import { readRepoFile, parseMarkdown } from "@/lib/repo";
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
