"use client";
import { useState } from "react";
import { S, Nav } from "@/lib/ui";

export default function InterceptPage() {
  const [provider, setProvider] = useState<"fake"|"claude">("fake");
  const [prompt, setPrompt] = useState("Say hello in one sentence.");
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function send() {
    setBusy(true); setLog([]);
    try {
      const res = await fetch("http://localhost:8000/v1/intercept/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, messages: [{ role: "user", content: prompt }] }),
      });
      if (!res.body) throw new Error("no body");
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const p of parts) {
          if (!p.startsWith("data: ")) continue;
          const data = p.slice(6);
          if (data === "[DONE]") { setLog(l => [...l, "\n── DONE ──"]); continue; }
          try {
            const j = JSON.parse(data);
            if (j.delta) setLog(l => [...l, j.delta]);
            if (j.finish_reason) setLog(l => [...l, `\n[finish: ${j.finish_reason}]`]);
          } catch {}
        }
      }
    } catch (e: any) {
      setLog(l => [...l, `ERROR: ${e.message}`]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={S.page}>
      <header style={S.header}>
        <h1 style={{ margin: 0 }}>Intercept Log</h1>
        <p style={{ ...S.muted, margin: "0.25rem 0 0" }}>
          Live stream from <span style={S.mono}>POST /v1/intercept/chat</span>
        </p>
        <Nav />
      </header>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem" }}>
        <select value={provider} onChange={e => setProvider(e.target.value as any)}
          style={{ padding: "0.5rem", background: "#0d1117", color: "#e6edf3",
                   border: "1px solid #30363d", borderRadius: 4 }}>
          <option value="fake">fake (always available)</option>
          <option value="claude">claude (needs session)</option>
        </select>
        <input value={prompt} onChange={e => setPrompt(e.target.value)}
          style={{ flex: 1, padding: "0.5rem", background: "#0d1117",
                   color: "#e6edf3", border: "1px solid #30363d", borderRadius: 4 }} />
        <button onClick={send} disabled={busy}
          style={{ padding: "0.5rem 1rem", background: busy ? "#6e7681" : "#238636",
                   color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
          {busy ? "Streaming…" : "Send"}
        </button>
      </div>

      {provider === "claude" && (
        <p style={{ ...S.yellow, fontSize: "0.85rem" }}>
          First time? Run{" "}
          <span style={S.mono}>python backend\scripts\harvest_claude.py</span>{" "}
          to log in. Session stored at <span style={S.mono}>backend/sessions/claude.json</span>.
        </p>
      )}

      <pre style={{ ...S.mono, background: "#0d1117", border: "1px solid #30363d",
                    borderRadius: 6, padding: "0.75rem", minHeight: 240,
                    whiteSpace: "pre-wrap", fontSize: "0.9rem" }}>
        {log.join("") || "(no output yet — click Send)"}
      </pre>
    </main>
  );
}
