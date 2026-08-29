#!/usr/bin/env bash
# 停止后台运行的服务（匹配 uvicorn backend.app.main:app 进程）。
set -euo pipefail
PIDS=$(pgrep -f "uvicorn backend.app.main:app" || true)
if [ -z "$PIDS" ]; then
  echo "未发现运行中的服务进程。"
  exit 0
fi
echo "停止进程：$PIDS"
kill $PIDS
echo "已发送停止信号。"
