import { S, Nav } from "@/lib/ui";

export default function GatewayPage() {
  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>AIRouter Gateway</h1>
        <p style={{ ...S.muted, margin: '0.25rem 0 0' }}>Public API surface for external applications</p>
        <Nav />
      </header>
      <section style={S.card}>
        <h2 style={{ marginTop: 0 }}>Endpoints</h2>
        <ul>
          <li><code>GET /v1/health</code></li>
          <li><code>GET /v1/providers</code></li>
          <li><code>GET /v1/models</code></li>
          <li><code>GET /v1/usage</code></li>
          <li><code>POST /v1/chat/completions</code></li>
        </ul>
      </section>
      <section style={S.card}>
        <h2 style={{ marginTop: 0 }}>Runtime</h2>
        <p style={S.muted}>Claude is the first backed provider. The Gateway delegates through the Orchestrator while provider transport stays provider-local.</p>
      </section>
    </main>
  );
}
