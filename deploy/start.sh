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
PID_FILE="$ROOT_DIR/deploy/run.pid"
HOST="127.0.0.1"
PORT="8000"
RERANKER_START="$ROOT_DIR/deploy/reranker/start.sh"
RERANKER_STOP="$ROOT_DIR/deploy/reranker/stop.sh"
RERANKER_RUNTIME_ENV="$ROOT_DIR/deploy/reranker/.runtime/runtime.env"
RERANKER_ENABLED="${RERANKER_ENABLED:-true}"

if [ ! -d "$VENV" ]; then
  echo "未找到虚拟环境 ${VENV}，请先创建：python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
if [ ! -x "$VENV/bin/uvicorn" ]; then
  echo "未找到可执行的 $VENV/bin/uvicorn，请先安装 requirements.txt。" >&2
  exit 1
fi

# 端口占用预检：避免静默启动失败
if command -v lsof >/dev/null 2>&1; then
  if lsof -ti:"$PORT" >/dev/null 2>&1; then
    echo "端口 $PORT 已被占用，请先停止占用进程（./deploy/stop.sh）再启动。" >&2
    exit 1
  fi
fi

case "$RERANKER_ENABLED" in
  true|false) export RERANKER_ENABLED ;;
  *) echo "RERANKER_ENABLED 仅接受 true 或 false。" >&2; exit 1 ;;
esac

RERANKER_STARTED=false
if [ "$RERANKER_ENABLED" = "true" ]; then
  if [ -x "$RERANKER_START" ] && "$RERANKER_START"; then
    runtime_url=""
    if [ -f "$RERANKER_RUNTIME_ENV" ]; then
      while IFS= read -r runtime_line; do
        case "$runtime_line" in
          RERANKER_BASE_URL=*) runtime_url="${runtime_line#RERANKER_BASE_URL=}" ;;
        esac
      done < "$RERANKER_RUNTIME_ENV"
    fi
    if [[ "$runtime_url" =~ ^http://(127\.0\.0\.1|localhost):[0-9]+$ ]] || \
       [[ "$runtime_url" =~ ^http://\[::1\]:[0-9]+$ ]]; then
      export RERANKER_BASE_URL="$runtime_url"
      RERANKER_STARTED=true
      echo "使用 Reranker：$RERANKER_BASE_URL"
    else
      echo "警告：Reranker 未提供有效的本机运行地址，FastAPI 将降级启动。" >&2
      [ -x "$RERANKER_STOP" ] && "$RERANKER_STOP" || true
    fi
  else
    echo "警告：Reranker 启动失败，FastAPI 将以 RRF 降级模式继续启动。" >&2
  fi
else
  echo "Reranker 已禁用，跳过启动与质量探针。"
fi

if [ "${1:-}" = "-d" ]; then
  echo "后台启动中… 日志：$LOG"
  nohup "$VENV/bin/uvicorn" backend.app.main:app --host "$HOST" --port "$PORT" > "$LOG" 2>&1 &
  APP_PID=$!
  printf '%s\n' "$APP_PID" > "$PID_FILE"
  echo "PID $APP_PID"
else
  cleanup() {
    status=$?
    trap - EXIT INT TERM
    if [ -n "${APP_PID:-}" ] && kill -0 "$APP_PID" 2>/dev/null; then
      kill -TERM "$APP_PID" 2>/dev/null || true
      wait "$APP_PID" 2>/dev/null || true
    fi
    if [ -f "$PID_FILE" ] && [ "$(tr -d '[:space:]' < "$PID_FILE")" = "${APP_PID:-}" ]; then
      unlink "$PID_FILE"
    fi
    if [ "$RERANKER_STARTED" = "true" ] && [ -x "$RERANKER_STOP" ]; then
      "$RERANKER_STOP" || echo "警告：Reranker 停止失败，请检查其运行状态。" >&2
    fi
    exit "$status"
  }
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  "$VENV/bin/uvicorn" backend.app.main:app --host "$HOST" --port "$PORT" &
  APP_PID=$!
  printf '%s\n' "$APP_PID" > "$PID_FILE"
  wait "$APP_PID"
fi
