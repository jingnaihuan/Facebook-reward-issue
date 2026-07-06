#!/bin/bash
# 社群互动发奖中台 — 一键启动（Mac）。双击即可运行。
cd "$(dirname "$0")/backend" || exit 1
echo "正在启动 社群互动发奖中台…"
echo "（首次运行会自动安装依赖：openpyxl / playwright + 浏览器内核，可能需要几分钟）"
python3 -c "import openpyxl" 2>/dev/null || pip3 install -r requirements.txt
echo "服务启动后会自动打开浏览器。关闭此窗口或按 Ctrl+C 可停止服务。"
# 浏览器由 server.py 自行打开（用 localhost，FB 方式 A 登录才不会被拦）
exec python3 server.py
