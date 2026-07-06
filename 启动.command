#!/bin/bash
# 社群互动发奖中台 — 一键启动（Mac）。双击即可运行。
cd "$(dirname "$0")/backend" || exit 1
echo "正在启动 社群互动发奖中台…"
echo "（首次运行会自动安装依赖：openpyxl / playwright + 浏览器内核，可能需要几分钟）"
python3 -c "import openpyxl" 2>/dev/null || pip3 install -r requirements.txt
python3 server.py &
SERVER_PID=$!
trap "kill $SERVER_PID 2>/dev/null" EXIT
for i in $(seq 1 150); do
  if curl -s -m 2 http://127.0.0.1:8765/api/ping >/dev/null 2>&1; then break; fi
  sleep 2
done
open "http://localhost:8765"   # 用 localhost 而非 127.0.0.1，方式 A（FB 登录）才不会被拦
echo "已在浏览器打开。关闭此窗口或按 Ctrl+C 可停止服务。"
wait $SERVER_PID
