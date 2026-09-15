"use client";
import { useState } from "react";
import { revertCommit } from "@/lib/actions";
import { S } from "@/lib/ui";

export default function RevertButton({ sha }: { sha: string }) {
  const [state, setState] = useState<"idle"|"busy"|"done"|"error">("idle");
  const [log, setLog] = useState("");

  async function go() {
    setState("busy");
    const r = await revertCommit(sha);
    setLog(r.log);
    setState(r.ok ? "done" : "error");
  }

  return (
    <>
      <button
        onClick={go}
        disabled={state === "busy" || state === "done"}
        style={{ padding: "0.6rem 1.2rem", background: state === "error" ? "#f85149" : "#da3633",
                 color: "#fff", border: "none", borderRadius: 4, cursor: "pointer",
                 fontSize: "1rem" }}
      >
        {state === "idle" && `Revert ${sha.slice(0,7)}`}
        {state === "busy" && "Reverting…"}
        {state === "done" && "✓ Revert complete"}
        {state === "error" && "✗ Failed — see log"}
      </button>

      {log && (
        <pre style={{ ...S.mono, marginTop: "1rem", padding: "0.75rem",
                      background: "#161b22", border: "1px solid #30363d",
                      borderRadius: 6, whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
          {log}
        </pre>
      )}

      {state === "done" && (
        <p style={{ ...S.green, marginTop: "0.5rem" }}>
          → <a href="/" style={S.link}>Back to commits</a>
        </p>
      )}
    </>
  );
}
