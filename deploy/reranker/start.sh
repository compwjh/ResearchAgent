#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNTIME_DIR="$SCRIPT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/run.pid"
LOG_FILE="$RUNTIME_DIR/run.log"
ENV_FILE="$RUNTIME_DIR/runtime.env"
MODEL_INPUT="${RERANKER_MODEL_PATH:-$ROOT_DIR/data/models/qwen3-reranker-0.6b-q8_0.gguf}"
RAW_URL="${RERANKER_BASE_URL:-http://127.0.0.1:11435}"
mkdir -p "$RUNTIME_DIR"

[[ -f "$MODEL_INPUT" ]] || { echo "Reranker 模型不存在：$MODEL_INPUT" >&2; exit 1; }
MODEL_PATH="$(cd "$(dirname "$MODEL_INPUT")" && pwd)/$(basename "$MODEL_INPUT")"
if [[ -n "${RERANKER_SERVER_BIN:-}" ]]; then
  SERVER_BIN="$(command -v "$RERANKER_SERVER_BIN" 2>/dev/null || printf '%s' "$RERANKER_SERVER_BIN")"
elif command -v llama-server >/dev/null 2>&1; then
  SERVER_BIN="$(command -v llama-server)"
else
  SERVER_BIN="/Applications/Ollama.app/Contents/Resources/llama-server"
fi
[[ -x "$SERVER_BIN" ]] || { echo "找不到可执行的 llama-server：$SERVER_BIN" >&2; exit 1; }

if [[ "$RAW_URL" =~ ^http://(127\.0\.0\.1|localhost)(:([0-9]+))?/?$ ]]; then
  HOST="${BASH_REMATCH[1]}"; PORT="${BASH_REMATCH[3]:-11435}"; URL_HOST="$HOST"
elif [[ "$RAW_URL" =~ ^http://\[::1\](:([0-9]+))?/?$ ]]; then
  HOST="::1"; PORT="${BASH_REMATCH[2]:-11435}"; URL_HOST="[::1]"
else
  echo "RERANKER_BASE_URL 仅允许 HTTP loopback 地址：$RAW_URL" >&2; exit 1
fi
[[ "$PORT" =~ ^[0-9]+$ ]] && ((PORT >= 1 && PORT <= 65535)) || { echo "无效端口：$PORT" >&2; exit 1; }

owned_process() {
  local pid="$1" command_line
  kill -0 "$pid" 2>/dev/null || return 1
  command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$command_line" == *"$MODEL_PATH"* && "$command_line" == *"--reranking"* ]]
}
if [[ -f "$PID_FILE" ]]; then
  old_pid="$(tr -d '[:space:]' < "$PID_FILE")"
  if [[ "$old_pid" =~ ^[0-9]+$ ]] && owned_process "$old_pid"; then
    echo "Reranker 已运行（PID ${old_pid}）。"; [[ -f "$ENV_FILE" ]] && grep '^RERANKER_BASE_URL=' "$ENV_FILE" || true; exit 0
  elif [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "PID 文件指向非本项目进程，拒绝覆盖：$old_pid" >&2; exit 1
  fi
  unlink "$PID_FILE"
fi

LSOF_BIN="$(command -v lsof 2>/dev/null || true)"
[[ -n "$LSOF_BIN" ]] || { echo "缺少端口检查工具 lsof。" >&2; exit 1; }
port_busy() { "$LSOF_BIN" -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
if port_busy "$PORT"; then
  PORT=""
  for ((candidate=11435; candidate<=11455; candidate++)); do
    if ! port_busy "$candidate"; then PORT="$candidate"; break; fi
  done
  [[ -n "$PORT" ]] || { echo "端口 11435-11455 均被占用。" >&2; exit 1; }
fi
BASE_URL="http://$URL_HOST:$PORT"

nohup "$SERVER_BIN" -m "$MODEL_PATH" --embedding --reranking --pooling rank \
  --host "$HOST" --port "$PORT" --ctx-size 8192 --ubatch-size 1024 --no-webui >"$LOG_FILE" 2>&1 &
STARTED_PID=$!
printf '%s\n' "$STARTED_PID" >"$PID_FILE"
printf 'RERANKER_BASE_URL=%s\nRERANKER_MODEL_PATH=%s\n' "$BASE_URL" "$MODEL_PATH" >"$ENV_FILE"
SUCCEEDED=false
cleanup() {
  if [[ "$SUCCEEDED" != true ]]; then
    if owned_process "$STARTED_PID"; then kill -INT "$STARTED_PID" 2>/dev/null || true; wait "$STARTED_PID" 2>/dev/null || true; fi
    [[ -f "$PID_FILE" ]] && [[ "$(tr -d '[:space:]' < "$PID_FILE")" == "$STARTED_PID" ]] && unlink "$PID_FILE"
    [[ -f "$ENV_FILE" ]] && unlink "$ENV_FILE"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

ready=false
for ((attempt=1; attempt<=120; attempt++)); do
  kill -0 "$STARTED_PID" 2>/dev/null || break
  if curl -fsS --max-time 1 "$BASE_URL/health" >/dev/null 2>&1; then ready=true; break; fi
  sleep 0.25
done
[[ "$ready" == true ]] || { echo "Reranker 未就绪，日志：$LOG_FILE" >&2; exit 1; }
if [[ -x "$SCRIPT_DIR/probe.sh" ]]; then
  RERANKER_BASE_URL="$BASE_URL" "$SCRIPT_DIR/probe.sh" || { echo "Reranker 质量探针失败。" >&2; exit 1; }
fi
SUCCEEDED=true
trap - EXIT INT TERM
echo "Reranker 已启动：${BASE_URL}（PID ${STARTED_PID}，日志 ${LOG_FILE}）"
