"use server";

import { execSync } from "node:child_process";
import path from "node:path";
import { revalidatePath } from "next/cache";

const ROOT = path.resolve(process.cwd(), "..");

function git(args: string): string {
  return execSync(`git ${args}`, { cwd: ROOT, encoding: "utf-8" }).trim();
}

export type RevertResult = { ok: boolean; log: string };

export async function revertCommit(sha: string): Promise<RevertResult> {
  const log: string[] = [];
  try {
    if (!/^[0-9a-f]{7,40}$/.test(sha)) throw new Error("invalid sha");
    log.push(`target: ${sha}`);
    log.push(git(`revert --no-edit ${sha}`));
    log.push(git("push origin main"));
    revalidatePath("/");
    revalidatePath("/rollback");
    return { ok: true, log: log.join("\n") };
  } catch (e: any) {
    log.push(`ERROR: ${e.message}`);
    try { git("revert --abort"); } catch {}
    return { ok: false, log: log.join("\n") };
  }
}
