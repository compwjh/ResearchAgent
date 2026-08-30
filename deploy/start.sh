#!/usr/bin/env bash
# 简单部署脚本：激活虚拟环境并启动后端服务（前端静态资源由 FastAPI 直接挂载）。
# 用法：
#   ./deploy/start.sh            # 前台运行（Ctrl+C 停止）
#   ./deploy/start.sh -d         # 后台运行，日志写到 deploy/run.log
#
# 注意：知识库（spec-011）的向量库是 Qdrant「本地文件模式」（data/kb/qdrant），
# 同一目录不允许被多个进程同时打开。请保持单 worker 启动，
# 不要加 --workers N（N>1），否则会造成向量库数据损坏。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT_DIR/.venv"
LOG="$ROOT_DIR/deploy/run.log"
HOST="127.0.0.1"
PORT="8000"

if [ ! -d "$VENV" ]; then
  echo "未找到虚拟环境 $VENV，请先创建：python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

# 端口占用预检：避免静默启动失败
if command -v lsof >/dev/null 2>&1; then
  if lsof -ti:"$PORT" >/dev/null 2>&1; then
    echo "端口 $PORT 已被占用，请先停止占用进程（./deploy/stop.sh）再启动。" >&2
    exit 1
  fi
fi

if [ "${1:-}" = "-d" ]; then
  echo "后台启动中… 日志：$LOG"
  nohup "$VENV/bin/uvicorn" backend.app.main:app --host "$HOST" --port "$PORT" > "$LOG" 2>&1 &
  echo "PID $!"
else
  exec "$VENV/bin/uvicorn" backend.app.main:app --host "$HOST" --port "$PORT"
fi
