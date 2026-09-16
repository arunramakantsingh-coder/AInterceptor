import pathlib
p = pathlib.Path("run.py")
s = p.read_text(encoding="utf-8")
s = s.replace(
'''    while True:
        alive = False
        for name, p in procs:
            if p.poll() is None:
                alive = True
                line = p.stdout.readline() if p.stdout else ""
                if line and line.strip():
                    print(f"[{name}] {line.rstrip()}")
        if not alive:
            break
        time.sleep(0.1)''',
'''    import threading, queue
    q = queue.Queue()
    def reader(name, p):
        for line in p.stdout:
            q.put((name, line.rstrip()))
    for name, p in procs:
        threading.Thread(target=reader, args=(name, p), daemon=True).start()
    while True:
        try:
            name, line = q.get(timeout=0.3)
            if line: print(f"[{name}] {line}")
        except queue.Empty:
            if all(p.poll() is not None for _, p in procs):
                break''')
p.write_text(s, encoding="utf-8")
print("[OK] run.py patched (non-blocking output)")
