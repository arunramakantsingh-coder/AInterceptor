import pathlib, sys

# Look for any saved raw capture around the repo
candidates = []
for root in [".evidence", ".ainterceptor", "scripts", "backend"]:
    p = pathlib.Path(root)
    if not p.exists():
        continue
    for f in p.rglob("*"):
        if f.is_file() and f.suffix.lower() in {".jsonl",".txt",".log",".raw"}:
            try:
                sz = f.stat().st_size
            except OSError:
                continue
            if 200 <= sz <= 5_000_000:
                candidates.append((f, sz))

candidates.sort(key=lambda x: -x[1])
print("Candidates (size desc, top 20):")
for f, sz in candidates[:20]:
    print(f"  {sz:>9}  {f}")

# Print the tail of the biggest one that mentions "chat/completion"
for f, sz in candidates[:40]:
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    if "chat/completion" in text or "data:" in text[:2000]:
        print("\n" + "="*72)
        print(f"CAPTURE: {f}  ({sz} bytes)")
        print("="*72)
        # print last 4000 chars
        print(text[-4000:])
        break
