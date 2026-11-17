@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup_and_run.bat first.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8000 after the server starts.
echo Keep this window open. Press Ctrl+C to stop.
.venv\Scripts\python.exe -m evidencedesk
if errorlevel 1 pause
