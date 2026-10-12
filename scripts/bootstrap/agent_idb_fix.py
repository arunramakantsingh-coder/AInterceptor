import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
agent_login = ROOT / "agent" / "airouter_agent" / "login.py"
src = agent_login.read_text(encoding="utf-8")

print("==> Checking agent login.py for IndexedDB capture")
if "_ainterceptor_idb" in src:
    print("  [OK] agent already captures IndexedDB")
else:
    print("  [PATCHING] agent does not capture IndexedDB")
    old = '''        state = await ctx.storage_state()
        await ctx.close()'''
    new = '''        state = await ctx.storage_state()

        # Capture IndexedDB (Playwright's storage_state does not include it)
        try:
            idb = await page.evaluate("""
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
            """)
            if idb:
                state["_ainterceptor_idb"] = idb
                total = sum(len(v) for v in idb.values())
                print(f"[agent] captured IndexedDB: {list(idb.keys())} ({total} stores)")
            else:
                print("[agent] no IndexedDB captured")
        except Exception as e:
            print(f"[agent] IndexedDB read failed: {e}")

        await ctx.close()'''
    if old in src:
        src = src.replace(old, new, 1)
        agent_login.write_text(src, encoding="utf-8", newline="\n")
        print("  [OK] agent patched")
    else:
        print("  [!] pattern not matched")
        print("  First 60 lines of login.py:")
        for i, ln in enumerate(src.splitlines()[:60], 1):
            print(f"    {i:3d} {ln}")
        sys.exit(1)

import ast
try:
    ast.parse(agent_login.read_text(encoding="utf-8"))
except SyntaxError as e:
    print("[FAIL]", e); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(agent): capture IndexedDB into uploaded storage_state"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("=" * 60)
print("NEXT: re-login deepseek with the patched agent")
print()
print("  cd agent")
print("  airouter-agent login deepseek")
print()
print("Watch for: [agent] captured IndexedDB: [...] (N stores)")
print()
print("Then re-run the curl test in the root:")
print("  cd ..")
print("  $envFile = Get-Content .\\.env.test")
print("  $APIKEY = ($envFile | Where-Object { $_ -like 'API_KEY=*' }) -replace '^API_KEY=', ''")
print("  Set-Content body.json '{\"model\":\"deepseek\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":true}' -Encoding ascii -NoNewline")
print("  curl.exe -N -X POST http://localhost:8000/v1/chat/completions -H \"Authorization: Bearer $APIKEY\" -H \"Content-Type: application/json\" --data-binary \"@body.json\"")
print("=" * 60)
