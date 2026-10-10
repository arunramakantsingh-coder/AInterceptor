import pathlib
p = pathlib.Path("run-windows.ps1")
txt = p.read_text(encoding="utf-8")

# Remove the pip upgrade line — not needed
txt = txt.replace(
    '    & "$venv\\Scripts\\pip.exe" install -q --upgrade pip\n',
    '',
)

# Ensure we retry install if it failed previously
p.write_text(txt, encoding="utf-8", newline="\r\n")
print("  [OK] run-windows.ps1: pip upgrade line removed")
