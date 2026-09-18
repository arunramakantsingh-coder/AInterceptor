@echo off
set PYTHONUTF8=1
cd /d "C:\Projects\AInterceptor-M1.5\backend"
if "%1"=="" goto start
if "%1"=="start" goto start
if "%1"=="stop" goto stop
if "%1"=="status" goto status
if "%1"=="restart" goto restart
goto start
:start
start "" /b "C:\Projects\Atlas\.venv\Scripts\pythonw.exe" -m scripts.aidaemon
echo daemon starting (wait 3s)...
timeout /t 3 /nobreak >nul
goto status
:stop
"C:\Projects\Atlas\.venv\Scripts\python.exe" -c "import urllib.request; urllib.request.urlopen(urllib.request.Request(\"http://127.0.0.1:7700/shutdown\", method=\"POST\"), timeout=5)"
echo daemon stopped
goto :eof
:status
"C:\Projects\Atlas\.venv\Scripts\python.exe" -c "import urllib.request,json; print(json.dumps(json.loads(urllib.request.urlopen(\"http://127.0.0.1:7700/\",timeout=3).read()),indent=2))"
goto :eof
:restart
call "%~f0" stop
timeout /t 2 /nobreak >nul
call "%~f0" start
goto :eof
