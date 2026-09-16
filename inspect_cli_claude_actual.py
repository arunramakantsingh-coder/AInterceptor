from pathlib import Path
import ast

for name in [
    "cli/chat.py",
    "backend/app/interception/claude.py",
]:
    print()
    print("=" * 80)
    print(name)
    print("=" * 80)

    text = Path(name).read_text(encoding="utf-8")
    tree = ast.parse(text)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            print(f"\nCLASS {node.name}  lines {node.lineno}-{node.end_lineno}")

            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    print(
                        f"  METHOD {child.name} "
                        f"lines {child.lineno}-{child.end_lineno}"
                    )

    print("\n--- relevant text ---")

    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()

        if any(x in low for x in [
            "storage_state",
            "storage state",
            "clauderuntime",
            "cdp",
            "ainTERCEPTOR".lower(),
            "session_path",
            "def chat",
            "async def chat",
        ]):
            start = max(1, i - 3)
            end = min(len(text.splitlines()), i + 5)

            print(f"\n[{start}-{end}]")
            for n in range(start, end + 1):
                print(f"{n:04d}: {text.splitlines()[n-1]}")

