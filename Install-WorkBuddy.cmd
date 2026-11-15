@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set "installResult=%errorlevel%"
if "%installResult%"=="0" (
  echo Open the custom connectors in WorkBuddy and trust windows-desktop-control.
) else (
  echo Check that domestic WorkBuddy has run once and Python 3.10+ is installed.
)
pause
exit /b %installResult%
