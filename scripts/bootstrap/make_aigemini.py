import pathlib
BIN = pathlib.Path("bin"); BIN.mkdir(exist_ok=True)
PY  = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
BE  = pathlib.Path("backend").resolve()
(BIN / "aigemini.cmd").write_text(
    "@echo off\r\n"
    "set PYTHONUTF8=1\r\n"
    f'cd /d "{BE}"\r\n'
    f'"{PY}" -u -m scripts.chat_any gemini\r\n',
    encoding="utf-8", newline="",
)
print("wrote", (BIN / "aigemini.cmd").resolve())
