@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 -m venv .venv
if errorlevel 1 goto fail
goto install
:use_python
python -m venv .venv
if errorlevel 1 goto fail
:install
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
if not exist .env copy .env.example .env >nul
call run.bat
exit /b
:fail
echo Setup failed. Install Python 3.11 or 3.12, check your connection, and try again.
pause
exit /b 1
