@echo off
setlocal
py -X utf8 "%~dp0capture_ebook_background.py" --check-deps >nul 2>&1
if errorlevel 1 (
  echo Installing Playwright / Pillow...
  py -m pip install --target "%~dp0..\private\.ebook_capture_packages" "playwright>=1.41,<2" pillow
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
py -X utf8 "%~dp0capture_ebook_background.py" %*
set result=%errorlevel%
pause
exit /b %result%
