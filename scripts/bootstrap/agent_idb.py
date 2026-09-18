import pathlib, subprocess, sys, textwrap

ROOT = pathlib.Path.cwd()
p = ROOT / "agent" / "airouter_agent" / "login.py"
src = p.read_text(encoding="utf-8")

# Add IDB reader + include it in the uploaded storage_state
idb_js = textwrap.dedent("""
    async () => {
        if (!indexedDB.databases) return {};
        const dbs = await indexedDB.databases();
        const out = {};
        for (const info of dbs) {
            if (!info.name) continue;
            try {
                const db = await new Promise((resolve, reject) => {
                    const req = indexedDB.open(info.name);
                    req.onsuccess = () => resolve(req.result);
                    req.onerror = () => reject(req.error);
                });
                const stores = Array.from(db.objectStoreNames);
                out[info.name] = {};
                for (const sn of stores) {
                    try {
                        const tx = db.transaction(sn, 'readonly');
                        const store = tx.objectStore(sn);
                        const all = await new Promise((resolve, reject) => {
                            const req = store.getAll();
                            req.onsuccess = () => resolve(req.result);
                            req.onerror = () => reject(req.error);
                        });
                        // JSON-stringify each value; IDB values may be Maps/objects
                        out[info.name][sn] = all.map(v => {
                            try { return JSON.parse(JSON.stringify(v)); }
                            catch { return String(v); }
                        });
                    } catch (e) { out[info.name][sn] = []; }
                }
                db.close();
            } catch (e) {}
        }
        return out;
    }
""").strip()

old = '''        state = await ctx.storage_state()
        await ctx.close()'''
new = '''        state = await ctx.storage_state()

        # ── Capture IndexedDB (Playwright's storage_state does not include it) ──
        try:
            idb = await page.evaluate("""''' + idb_js + '''""")
            if idb:
                state["_ainterceptor_idb"] = idb
                print(f"[agent] captured IndexedDB: {list(idb.keys())}")
            else:
                print("[agent] no IndexedDB captured")
        except Exception as e:
            print(f"[agent] IndexedDB read failed: {e}")

        await ctx.close()'''

if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] agent reads IndexedDB")
else:
    print("  [!] agent pattern not matched")

import ast
try:
    ast.parse(p.read_text(encoding="utf-8"))
except SyntaxError as e:
    print("[FAIL]", e); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(agent): capture IndexedDB into storage_state (DeepSeek auth lives there)"])
print((r.stdout.strip() or r.stderr.strip())[:300])
