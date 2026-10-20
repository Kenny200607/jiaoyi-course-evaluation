@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto existing
where py.exe >nul 2>nul
if not errorlevel 1 goto pylauncher
where python.exe >nul 2>nul
if not errorlevel 1 goto systempython
echo Install Python 3.12, or download the portable Windows ZIP.
pause
exit /b 1
:existing
".venv\Scripts\python.exe" -X utf8 tools\source_launcher.py %*
exit /b %ERRORLEVEL%
:pylauncher
py -3.12 -X utf8 tools\source_launcher.py %*
exit /b %ERRORLEVEL%
:systempython
python.exe -X utf8 tools\source_launcher.py %*
exit /b %ERRORLEVEL%
