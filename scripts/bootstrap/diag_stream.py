import pathlib, sys
sys.path.insert(0, "backend")
from app.interception.deepseek import DeepSeekStreamParser

raw_text = pathlib.Path(".evidence/raw/deepseek_1789710974.raw").read_text(encoding="utf-8")
raw_bytes = raw_text.encode("utf-8")

p = DeepSeekStreamParser()
emitted = ""
body = bytearray()
CHUNK = 200

print("raw bytes:", len(raw_bytes))
print("=" * 60)

for i in range(0, len(raw_bytes), CHUNK):
    body.extend(raw_bytes[i:i+CHUNK])
    text = body.decode("utf-8", errors="replace")
    last_nl = text.rfind("\n")
    if last_nl == -1:
        continue
    stable = text[:last_nl + 1]
    try:
        current = p(stable)
    except Exception as e:
        print(f"[{i:5d}] parser error: {e}")
        continue
    if current and current.startswith(emitted):
        delta = current[len(emitted):]
    else:
        delta = ""
        if current != emitted:
            print(f"[{i:5d}] DIVERGENCE")
            print(f"        emitted={emitted!r}")
            print(f"        current={current!r}")
    if delta:
        print(f"[{i:5d}] delta={delta!r}")
        emitted = current

print("=" * 60)
print("FINAL emitted:", repr(emitted))
print("EXPECTED     :", repr("Hello again! 42 is still here. What would you like to do?"))
