import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");

export type ProviderHealth = {
  name: string;
  subsystem: "Interceptor" | "Orchestrator" | "Gateway";
  status: "active" | "expiring" | "failed" | "not_implemented";
  phase: string;
  note: string;
};

const CATALOG: ProviderHealth[] = [
  { name: "Claude Web",     subsystem: "Interceptor",  status: "not_implemented", phase: "2", note: "Phase 2 PoC target" },
  { name: "Gemini Web",     subsystem: "Interceptor",  status: "not_implemented", phase: "3", note: "" },
  { name: "ChatGPT Web",    subsystem: "Interceptor",  status: "not_implemented", phase: "4", note: "" },
  { name: "DeepSeek Web",   subsystem: "Interceptor",  status: "not_implemented", phase: "4", note: "" },
  { name: "Qwen Web",       subsystem: "Interceptor",  status: "not_implemented", phase: "4", note: "" },
  { name: "Router Engine",  subsystem: "Orchestrator", status: "not_implemented", phase: "5", note: "capability routing + merge" },
  { name: "Gateway API",    subsystem: "Gateway",      status: "not_implemented", phase: "6", note: "OpenAI-compatible /v1/chat/completions" },
];

export function listProviderHealth(): ProviderHealth[] {
  return CATALOG;
}

export function readStatusBlock(): string {
  const p = path.join(ROOT, ".ai/CURRENT_TASK.md");
  try { return fs.readFileSync(p, "utf-8"); } catch { return "(missing .ai/CURRENT_TASK.md)"; }
}

export function readMilestoneTable(): { headers: string[]; rows: string[][] } | null {
  const md = (() => {
    try { return fs.readFileSync(path.join(ROOT, "PROJECT/ROADMAP.md"), "utf-8"); }
    catch { return ""; }
  })();
  const lines = md.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    if (/^\|\s*Gate\s*\|/i.test(lines[i])) {
      const headers = lines[i].replace(/^\||\|$/g, "").split("|").map(s => s.trim());
      const rows: string[][] = [];
      let j = i + 2;
      while (j < lines.length && lines[j].trim().startsWith("|")) {
        rows.push(lines[j].replace(/^\||\|$/g, "").split("|").map(s => s.trim()));
        j++;
      }
      return { headers, rows };
    }
  }
  return null;
}
