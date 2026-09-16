from pathlib import Path

for name in [
    r"cli\chat.py",
    r"backend\app\interception\claude.py",
]:
    p = Path(name)
    print("=" * 80)
    print(name)
    print("=" * 80)

    if not p.exists():
        print("MISSING")
        continue

    text = p.read_text(encoding="utf-8")

    for i, line in enumerate(text.splitlines(), 1):
        if any(x in line.lower() for x in [
            "storage_state",
            "cdp_url",
            "ClaudeRuntime",
            "session_path",
            "AINTERCEPTOR_CLAUDE",
        ]):
            print(f"{i:04d}: {line}")

    print()

print("Diagnostic complete.")
