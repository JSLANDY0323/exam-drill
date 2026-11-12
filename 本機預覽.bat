@echo off
chcp 65001 >nul
title 刷題網站 本機預覽
cd /d "%~dp0"
set "PORT=8000"

rem ---- 找可用的 Python（python 或 py）----
set "PY="
python --version >nul 2>&1 && set "PY=python"
if not defined PY py --version >nul 2>&1 && set "PY=py"
if not defined PY goto nopy

rem ---- 8000 已被占用：多半是之前開的預覽還在執行，直接開瀏覽器 ----
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo 連接埠 %PORT% 已在使用中，可能已經開著預覽。直接開啟瀏覽器……
  start "" http://localhost:%PORT%/
  timeout /t 3 >nul
  exit /b
)

echo.
echo  刷題網站本機預覽
echo  網址：http://localhost:%PORT%/
echo  使用期間請不要關閉這個視窗；要結束時按 Ctrl+C 或直接關閉視窗。
echo.

rem ---- 1 秒後自動開啟瀏覽器，再啟動伺服器（只開放本機連線）----
start "" /b cmd /c "ping -n 2 127.0.0.1 >nul & start "" http://localhost:%PORT%/"
%PY% -m http.server %PORT% --bind 127.0.0.1
echo.
echo 伺服器已停止。
pause
exit /b

:nopy
echo.
echo 找不到 Python。請到 https://www.python.org/downloads/ 安裝，
echo 安裝時記得勾選「Add python.exe to PATH」，裝好後再雙擊這個檔案。
echo.
pause
