export const S = {
  page: { maxWidth: 1000, margin: "0 auto", padding: "2rem" } as const,
  header: { borderBottom: "1px solid #30363d", paddingBottom: "1rem", marginBottom: "1.5rem" } as const,
  nav: { display: "flex", gap: "1rem", marginTop: "0.5rem" } as const,
  link: { color: "#58a6ff", textDecoration: "none" } as const,
  card: { padding: "0.75rem", border: "1px solid #30363d", borderRadius: 6,
          marginBottom: "0.5rem", background: "#161b22" } as const,
  mono: { fontFamily: "monospace" } as const,
  muted: { color: "#8b949e" } as const,
  red: { color: "#f85149" } as const,
  green: { color: "#3fb950" } as const,
  yellow: { color: "#d29922" } as const,
};

export function Nav() {
  return (
    <nav style={S.nav}>
      <a href="/" style={S.link}>Commits</a>
      <a href="/versions" style={S.link}>Versions</a>
      <a href="/compare" style={S.link}>Compare</a>
    </nav>
  );
}
