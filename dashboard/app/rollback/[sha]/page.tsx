import { getCommit } from "@/lib/github";
import { S, Nav } from "@/lib/ui";
import RevertButton from "./RevertButton";

export const dynamic = "force-dynamic";

export default async function RollbackConfirm({
  params,
}: { params: Promise<{ sha: string }> }) {
  const { sha } = await params;
  const c = await getCommit(sha);

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Confirm Revert</h1>
        <Nav />
      </header>

      <div style={S.card}>
        <div style={S.mono}>{c.sha}</div>
        <div style={{ marginTop: "0.5rem" }}>{c.message}</div>
        <div style={{ ...S.muted, marginTop: "0.25rem", fontSize: "0.85rem" }}>
          {c.author} · {new Date(c.date).toLocaleString()}
        </div>
      </div>

      <p style={S.yellow}>
        A new commit will be created that reverses this commit's changes and
        pushed to <span style={S.mono}>origin/main</span>.
      </p>

      <RevertButton sha={sha} />
    </main>
  );
}
