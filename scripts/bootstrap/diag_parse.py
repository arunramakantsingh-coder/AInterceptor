import pathlib, sys
sys.path.insert(0, str(pathlib.Path("backend")))
from app.interception.deepseek import parse_deepseek_web

raw_dir = pathlib.Path(".evidence/raw")
newest = sorted(raw_dir.glob("deepseek_*.raw"), key=lambda p: p.stat().st_mtime)[-1]
print("FILE:", newest)
text = newest.read_text(encoding="utf-8", errors="replace")
print("=" * 60)
print("PARSED:", repr(parse_deepseek_web(text)))
print("=" * 60)
