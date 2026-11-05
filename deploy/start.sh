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
HOST="${HOST:-127.0.0.1}"
# 默认 8000；可用环境变量覆盖，例如：PORT=8300 ./deploy/start.sh -d
PORT="${PORT:-8000}"
RERANKER_START="$ROOT_DIR/deploy/reranker/start.sh"
RERANKER_STOP="$ROOT_DIR/deploy/reranker/stop.sh"
RERANKER_RUNTIME_ENV="$ROOT_DIR/deploy/reranker/.runtime/runtime.env"
RERANKER_ENABLED="${RERANKER_ENABLED:-true}"
# 文件描述符软限制：默认 4096，可用环境变量覆盖。
# macOS 的 launchctl 默认 maxfiles 软限制为 256，长跑服务会因 SQLite/静态资源句柄
# 累积触发 "Too many open files"（表现为前端 CSS/JS 0 字节、数据库打不开）。
RA_FD_SOFT_LIMIT="${RA_FD_SOFT_LIMIT:-4096}"

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
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
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
      echo "使用 Reranker：${RERANKER_BASE_URL}"
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

# 在启动 uvicorn 之前**只抬升、不降级** FD 软限制。
# 无条件 `ulimit -n 4096` 会把开发终端已经很宽松的限制（如 1048575）向下压，
# 与加固意图相反；这里仅在当前软限制低于目标时才设置。失败只告警、不中断启动
# （`set -e` 下用 if 保护）。`unlimited` / 空值按「已足够」处理，不做数字比较。
current_fd_soft="$(ulimit -Sn 2>/dev/null || echo "")"
case "$current_fd_soft" in
  ""|unlimited)
    echo "FD 软限制当前为 ${current_fd_soft:-unknown}（不限制），已不低于目标 ${RA_FD_SOFT_LIMIT}，保持不变。"
    ;;
  *)
    # 非数字目标视为非法：不做比较（避免 "integer expression expected"），直接尝试设置。
    case "$RA_FD_SOFT_LIMIT" in
      ""|*[!0-9]*) needs_raise=1 ;;
      *) if { [ "$current_fd_soft" -lt "$RA_FD_SOFT_LIMIT" ]; } 2>/dev/null; then needs_raise=1; else needs_raise=0; fi ;;
    esac
    if [ "$needs_raise" = "1" ]; then
      if ulimit -n "$RA_FD_SOFT_LIMIT" 2>/dev/null; then
        echo "FD 软限制已从 ${current_fd_soft} 抬升到 ${RA_FD_SOFT_LIMIT}（当前 ulimit -n = $(ulimit -n)）。"
      else
        echo "警告：无法将 FD 软限制从 ${current_fd_soft} 抬升到 ${RA_FD_SOFT_LIMIT}，继续以降级限制启动（当前 ulimit -n = $(ulimit -n 2>/dev/null || echo unknown)）。" >&2
      fi
    else
      echo "FD 软限制当前为 ${current_fd_soft}，已不低于目标 ${RA_FD_SOFT_LIMIT}，保持不变。"
      true
    fi
    ;;
esac

if [ "${1:-}" = "-d" ]; then
  echo "后台启动中… 日志：${LOG}"
  nohup "$VENV/bin/uvicorn" backend.app.main:app --host "$HOST" --port "$PORT" > "$LOG" 2>&1 &
  APP_PID=$!
  printf '%s\n' "$APP_PID" > "$PID_FILE"
  echo "PID ${APP_PID}"
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
