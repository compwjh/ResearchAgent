#!/usr/bin/env bash
# 停止项目 FastAPI 与专用 Reranker；仅操作各自 PID 文件确认的进程。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/deploy/run.pid"
RERANKER_STOP="$ROOT_DIR/deploy/reranker/stop.sh"
STATUS=0

if [ ! -f "$PID_FILE" ]; then
  echo "未发现 FastAPI PID 文件。"
else
  PID="$(tr -d '[:space:]' < "$PID_FILE")"
  if [[ ! "$PID" =~ ^[0-9]+$ ]]; then
    echo "FastAPI PID 文件无效，拒绝终止进程。" >&2
    STATUS=1
  elif ! kill -0 "$PID" 2>/dev/null; then
    unlink "$PID_FILE"
    echo "已清理陈旧 FastAPI PID。"
  else
    COMMAND_LINE="$(ps -p "$PID" -o command= 2>/dev/null || true)"
    if [[ "$COMMAND_LINE" != *"uvicorn backend.app.main:app"* ]]; then
      echo "PID $PID 不属于本项目 FastAPI，拒绝终止。" >&2
      STATUS=1
    else
      kill -TERM "$PID" 2>/dev/null || STATUS=1
      for ((attempt=1; attempt<=40; attempt++)); do
        kill -0 "$PID" 2>/dev/null || break
        sleep 0.25
      done
      if kill -0 "$PID" 2>/dev/null; then
        echo "FastAPI PID $PID 未在超时内退出。" >&2
        STATUS=1
      else
        unlink "$PID_FILE"
        echo "FastAPI 已停止（PID ${PID}）。"
      fi
    fi
  fi
fi

if [ -x "$RERANKER_STOP" ]; then
  "$RERANKER_STOP" || STATUS=1
else
  echo "警告：找不到 Reranker 停止脚本：$RERANKER_STOP" >&2
  STATUS=1
fi

exit "$STATUS"
