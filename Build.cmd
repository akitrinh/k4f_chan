@echo off
setlocal
set "TEMP=%~dp0.cache"
set "TMP=%~dp0.cache"
set "PYINSTALLER_CONFIG_DIR=%~dp0.cache\pyinstaller"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run Setup.cmd first. Python 3.14 x64 is required to build.
  exit /b 1
)
pushd "%~dp0"
"%~dp0.venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath dist --workpath build k4f_chan.spec
if errorlevel 1 goto :failure
for %%D in (assets models LICENSES) do (
  xcopy "%%D" "dist\k4f_chan\%%D\" /E /I /Y >nul
  if errorlevel 1 goto :failure
)
for %%F in (README.md README-VI.md CHANGELOG.md LICENSE THIRD_PARTY_NOTICES.md DEPENDENCIES.json) do (
  copy /Y "%%F" "dist\k4f_chan\%%F" >nul
  if errorlevel 1 goto :failure
)
echo Build complete: dist\k4f_chan\k4f_chan.exe
popd
exit /b 0
:failure
popd
echo Build failed. No provider or credential fallback was used.
exit /b 1
