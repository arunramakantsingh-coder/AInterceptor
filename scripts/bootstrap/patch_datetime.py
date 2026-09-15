import pathlib
p = pathlib.Path("scripts/validate_phase.py")
s = p.read_text(encoding="utf-8")
s = s.replace(
    'stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")',
    'stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")'
)
p.write_text(s, encoding="utf-8")
print("PASS: datetime patched")
