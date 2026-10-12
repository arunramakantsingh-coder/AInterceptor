@echo off
set PYTHONUTF8=1
cd /d "C:\Projects\AInterceptor-M1.5\backend"
"C:\Projects\AInterceptor-M1.5\.venv-windows\Scripts\python.exe" -u -m scripts.chat_any poe %*
