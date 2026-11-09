@echo off
setlocal
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo Chua co moi truong Python. Hay chay Setup.cmd truoc.
  pause
  exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
