@echo off
rem Benro Polaris libgphoto2 patcher - Windows double-click launcher.
rem Wraps patch-polaris.ps1 so you don't need VS Code or a pre-configured shell.
rem Only host requirement: Docker Desktop (Linux container engine).
setlocal

if not exist "%~dp0patch-polaris.ps1" (
  echo [ERROR] patch-polaris.ps1 not found next to this file. & exit /b 1
)

if "%~1"=="" (
  set /p FWPKT="Path to stock FwPkt folder or FwPkt.zip (type without quotes): "
  if defined FWPKT (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0patch-polaris.ps1" -FwPkt "%FWPKT%"
  ) else (
    echo [ERROR] No path given. Usage: patch-polaris.bat ^<FwPkt-folder-or-zip^> [options]
    pause & exit /b 1
  )
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0patch-polaris.ps1" %*
)
set "RC=%ERRORLEVEL%"
echo.
if %RC% neq 0 (echo [FAILED] exit code %RC%. See output above.) else (echo [DONE] Output is in .\out by default.)
pause
exit /b %RC%
