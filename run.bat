@echo off
rem Double-click launcher for running from source. Needs Python 3.9+ with tkinter.
rem If you do not have Python, download the prebuilt dist\ClipNest.exe instead.
setlocal
cd /d "%~dp0"

set "PY="
where pythonw >nul 2>nul && set "PY=pythonw"
if not defined PY where py >nul 2>nul && set "PY=py -3w"

if not defined PY (
  echo Python not found.
  echo Install it from https://www.python.org/downloads/windows/
  echo and tick "Add python.exe to PATH", or use the prebuilt ClipNest.exe.
  pause
  exit /b 1
)

start "" %PY% "%~dp0run.pyw"
