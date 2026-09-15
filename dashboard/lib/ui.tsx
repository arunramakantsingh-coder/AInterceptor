export const S = {
  page: { maxWidth: 1000, margin: "0 auto", padding: "2rem" } as const,
  header: { borderBottom: "1px solid #30363d", paddingBottom: "1rem", marginBottom: "1.5rem" } as const,
  nav: { display: "flex", gap: "1rem", marginTop: "0.5rem", flexWrap: "wrap" as const } as const,
  link: { color: "#58a6ff", textDecoration: "none" } as const,
  card: { padding: "0.75rem", border: "1px solid #30363d", borderRadius: 6,
          marginBottom: "0.5rem", background: "#161b22" } as const,
  mono: { fontFamily: "monospace" } as const,
  muted: { color: "#8b949e" } as const,
  red: { color: "#f85149" } as const,
  green: { color: "#3fb950" } as const,
  yellow: { color: "#d29922" } as const,
  table: { borderCollapse: "collapse" as const, width: "100%", marginTop: "0.5rem" },
  th: { textAlign: "left" as const, borderBottom: "1px solid #30363d",
        padding: "0.4rem 0.6rem", background: "#161b22" },
  td: { borderBottom: "1px solid #21262d", padding: "0.4rem 0.6rem" },
};

export function Nav() {
  return (
    <nav style={S.nav}>
      <a href="/" style={S.link}>Commits</a>
      <a href="/versions" style={S.link}>Versions</a>
      <a href="/compare" style={S.link}>Compare</a>
      <a href="/roadmap" style={S.link}>Roadmap</a>
      <a href="/bugs" style={S.link}>Bugs</a>
      <a href="/providers" style={S.link}>Providers</a>
      <a href="/status" style={S.link}>Status</a>
      <a href="/intercept" style={S.link}>Intercept</a>
      <a href="/sessions" style={S.link}>Sessions</a>
      <a href="/rollback" style={S.link}>Rollback</a>
    </nav>
  );
}

export function MdTable({ t }: { t: { headers: string[]; rows: string[][] } }) {
  return (
    <table style={S.table}>
      <thead><tr>{t.headers.map((h, i) => <th key={i} style={S.th}>{h}</th>)}</tr></thead>
      <tbody>
        {t.rows.map((r, i) => (
          <tr key={i}>{r.map((c, j) => <td key={j} style={S.td}>{c}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}
