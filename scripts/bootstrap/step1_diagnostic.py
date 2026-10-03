import pathlib, subprocess, sys, socket, urllib.request

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"

def hr(title):
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)

def cat(path, head=None):
    p = pathlib.Path(path)
    if not p.exists():
        print(f"[MISSING] {p}")
        return
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if head:
        lines = lines[:head]
    for i, ln in enumerate(lines, 1):
        print(f"{i:4d}  {ln}")

# ── A. browser_supervisor.py ──
hr("A. browser_supervisor.py  (current, full)")
cat(BE / "runtime" / "browser_supervisor.py")

# ── B. chat_any.py (CLI) ──
hr("B. backend/scripts/chat_any.py  (current, full)")
cat(BE / "scripts" / "chat_any.py")

# ── C. bin/chatgpt.cmd ──
hr("C. bin/chatgpt.cmd")
cat(ROOT / "bin" / "chatgpt.cmd")

# ── D. Ports currently in use ──
hr("D. Listening ports 9222-9225")
r = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-NetTCPConnection -LocalPort 9222,9223,9224,9225 -State Listen -EA SilentlyContinue | "
     "Select-Object LocalPort, OwningProcess | Format-Table -AutoSize | Out-String"],
    capture_output=True, text=True,
)
print(r.stdout or "(no listeners)")

# ── E. Chrome processes alive ──
hr("E. Chrome processes currently running")
r = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
     "Select-Object ProcessId, @{n='Cmd';e={$_.CommandLine.Substring(0,[Math]::Min(120,$_.CommandLine.Length))}} | "
     "Format-Table -AutoSize | Out-String"],
    capture_output=True, text=True,
)
print(r.stdout or "(no chrome)")

# ── F. Session files on disk ──
hr("F. Exported session files")
sess = ROOT / ".ainterceptor" / "exports"
if sess.exists():
    for f in sorted(sess.glob("*.json")):
        print(f"  {f.name}  ({f.stat().st_size} bytes)")
else:
    print("(no exports dir)")

# ── G. Daemon state (is anything running) ──
hr("G. Is daemon / API running?")
for port in (8000,):
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"Get-NetTCPConnection -LocalPort {port} -State Listen -EA SilentlyContinue | "
         "Select-Object LocalPort, OwningProcess | Format-Table -AutoSize | Out-String"],
        capture_output=True, text=True,
    )
    print(f"port {port}:")
    print(r.stdout or "(nothing)")

# ── H. Git state ──
hr("H. Recent commits on this branch")
r = subprocess.run(["git", "log", "--oneline", "-15"], cwd=ROOT,
                   capture_output=True, text=True)
print(r.stdout)

hr("I. Files changed in the last 20 commits (top 30)")
r = subprocess.run(["git", "log", "--name-only", "--oneline", "-20"], cwd=ROOT,
                   capture_output=True, text=True)
seen = set()
for ln in r.stdout.splitlines():
    if not ln or ln[0].isalnum() and " " in ln and len(ln.split()[0]) == 7:
        continue
    if ln not in seen:
        seen.add(ln)
print("\n".join(sorted(seen)[:40]))

print()
print("=" * 72)
print("END OF DIAGNOSTIC — no changes made")
print("=" * 72)
