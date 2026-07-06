@echo off
chcp 65001 >nul
rem 社群互动发奖中台 — 一键启动（Windows）。双击即可运行。
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0backend"
echo 正在启动 社群互动发奖中台…
echo （首次运行会自动安装依赖：openpyxl / playwright + 浏览器内核，可能需要几分钟）

rem 探测可用的 Python 命令：优先 py（官方 launcher），其次 python
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo.
  echo [错误] 未检测到 Python。请先安装 Python 3.9 及以上（安装时勾选 Add python.exe to PATH）：
  echo         https://www.python.org/downloads/
  echo 安装完成后，重新双击本文件即可。
  echo.
  pause
  exit /b 1
)

rem 依赖检查：缺 openpyxl 才安装（首次会稍慢）
%PY% -c "import openpyxl" 2>nul || %PY% -m pip install -r requirements.txt

echo 服务启动后会自动打开浏览器。关闭此窗口可停止服务。
%PY% server.py
echo.
echo 服务已停止。
pause
