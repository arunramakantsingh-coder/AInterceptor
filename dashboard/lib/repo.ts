import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");

export function readRepoFile(rel: string): string {
  const p = path.join(ROOT, rel);
  try { return fs.readFileSync(p, "utf-8"); } catch { return ""; }
}

export type Table = { headers: string[]; rows: string[][] };
export type Section = { heading: string; level: number; table?: Table; body?: string };

function splitRow(line: string): string[] {
  return line.trim().replace(/^\||\|$/g, "").split("|").map(s => s.trim());
}

export function parseMarkdown(md: string): Section[] {
  const sections: Section[] = [];
  let current: Section | null = null;
  const lines = md.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      if (current) sections.push(current);
      current = { heading: h[2].trim(), level: h[1].length };
      continue;
    }
    // table detection
    if (line.trim().startsWith("|") && current) {
      const next = lines[i+1] || "";
      if (/^\|?[\s\-:|]+\|?\s*$/.test(next) && next.includes("-")) {
        const headers = splitRow(line);
        const rows: string[][] = [];
        let j = i + 2;
        while (j < lines.length && lines[j].trim().startsWith("|")) {
          rows.push(splitRow(lines[j]));
          j++;
        }
        if (!current.table) current.table = { headers, rows };
        i = j - 1;
      }
    }
  }
  if (current) sections.push(current);
  return sections;
}

export function currentStatus(): string {
  const md = readRepoFile("PROJECT/ROADMAP.md");
  const m = /Current:\s*(.+)/.exec(md);
  return m ? m[1] : "(no status line)";
}
