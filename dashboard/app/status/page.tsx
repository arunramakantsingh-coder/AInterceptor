import { readStatusBlock, readMilestoneTable } from "@/lib/health";
import { S, Nav, MdTable } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default function StatusPage() {
  const status = readStatusBlock();
  const gates = readMilestoneTable();

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Project Status</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>Live from .ai/CURRENT_TASK.md + PROJECT/ROADMAP.md</p>
        <Nav />
      </header>

      <h2 style={{ fontSize: "1rem", ...S.muted, textTransform: "uppercase" }}>Current Task</h2>
      <pre style={{ ...S.mono, padding: "0.75rem", background: "#161b22",
                    border: "1px solid #30363d", borderRadius: 6,
                    whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
        {status}
      </pre>

      <h2 style={{ fontSize: "1rem", ...S.muted, textTransform: "uppercase", marginTop: "1.5rem" }}>
        Milestone Gate
      </h2>
      {gates ? <MdTable t={gates} /> : <p style={S.muted}>No gate table found.</p>}
    </main>
  );
}
