import { listProviderHealth } from "@/lib/health";
import { S, Nav } from "@/lib/ui";

export const dynamic = "force-dynamic";

const color: Record<string,string> = {
  active: "#3fb950",
  expiring: "#d29922",
  failed: "#f85149",
  not_implemented: "#8b949e",
};

export default function ProvidersPage() {
  const list = listProviderHealth();
  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Provider Health</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>Interceptor + Orchestrator + Gateway readiness</p>
        <Nav />
      </header>

      <table style={S.table}>
        <thead>
          <tr>
            <th style={S.th}>Provider</th>
            <th style={S.th}>Subsystem</th>
            <th style={S.th}>Phase</th>
            <th style={S.th}>Status</th>
            <th style={S.th}>Note</th>
          </tr>
        </thead>
        <tbody>
          {list.map(p => (
            <tr key={p.name}>
              <td style={S.td}>{p.name}</td>
              <td style={S.td}>{p.subsystem}</td>
              <td style={S.td}>{p.phase}</td>
              <td style={{ ...S.td, color: color[p.status] }}>● {p.status}</td>
              <td style={{ ...S.td, ...S.muted }}>{p.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
