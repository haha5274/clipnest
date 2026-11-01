@echo off
rem Build a standalone dist\ClipNest.exe (no Python required on the target machine).
rem Needs: Python 3.9+, then  pip install pyinstaller
setlocal
cd /d "%~dp0"

echo [1/2] rendering icon
python tools\make_icon.py || goto :err

echo [2/2] packaging
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name ClipNest ^
  --icon docs\clipnest.ico ^
  --add-data "docs\clipnest.ico;." ^
  run.pyw || goto :err

echo.
echo done: dist\ClipNest.exe
exit /b 0

:err
echo.
echo build failed
exit /b 1
