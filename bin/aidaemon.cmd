@echo off
set PYTHONUTF8=1
cd /d "C:\Projects\AInterceptor-M1.5\backend"
if "%1"=="" goto help
if "%1"=="start" goto start
if "%1"=="stop" goto stop
if "%1"=="status" goto status
if "%1"=="restart" goto restart
if "%1"=="help" goto help
if "%1"=="log" goto log
echo Unknown command: %1
goto help

:start
echo Starting aidaemon...
start "aidaemon" /min "C:\Projects\Atlas\.venv\Scripts\python.exe" -u -m scripts.aidaemon
timeout /t 3 /nobreak >nul
goto status

:stop
"C:\Projects\Atlas\.venv\Scripts\python.exe" -c "import urllib.request; urllib.request.urlopen(urllib.request.Request(\"http://127.0.0.1:7700/shutdown\", method=\"POST\"), timeout=5)" 2>nul
echo aidaemon stopped
goto :eof

:status
"C:\Projects\Atlas\.venv\Scripts\python.exe" -u scripts\\daemon_status.py
goto :eof

:log
type "C:\Projects\AInterceptor-M1.5\.ainterceptor\daemon.log"
goto :eof

:restart
call "%~f0" stop
timeout /t 2 /nobreak >nul
call "%~f0" start
goto :eof

:help
echo.
echo AIDAEMON - AInterceptor session manager
echo.
echo USAGE:
echo   aidaemon start       Start the background daemon
echo   aidaemon stop        Stop the daemon and all browsers
echo   aidaemon status      Show provider status
echo   aidaemon restart     Restart the daemon
echo   aidaemon log         Show daemon log
echo.
echo CHAT:
echo   deepseek             Open DeepSeek chat
echo   claude               Open Claude chat
echo   chatgpt              Open ChatGPT chat
echo   aigemini             Open Gemini chat
echo.
echo LOGIN:
echo   daemon login ^<provider^>    Open browser for login
echo   daemon hide  ^<provider^>    Hide the browser again
echo   daemon show  ^<provider^>    Bring browser on-screen
echo.
goto :eof
