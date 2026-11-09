@echo off
setlocal
set "TEMP=%~dp0.cache"
set "TMP=%~dp0.cache"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%~dp0.venv\Scripts\python.exe" (
  py -3.14 -m venv "%~dp0.venv"
  if errorlevel 1 goto :failure
)
"%~dp0.venv\Scripts\python.exe" -m pip install --disable-pip-version-check --cache-dir "%~dp0.cache\pip" -r "%~dp0build-requirements.txt"
if errorlevel 1 goto :failure
echo Cai dat thanh cong. Mo Launch.cmd de dung app.
pause
exit /b 0
:failure
echo Cai dat that bai. Can Python 3.14 x64 va ket noi Internet.
pause
exit /b 1
