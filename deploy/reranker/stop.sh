#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNTIME_DIR="$SCRIPT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/run.pid"
ENV_FILE="$RUNTIME_DIR/runtime.env"
MODEL_PATH="${RERANKER_MODEL_PATH:-$ROOT_DIR/data/models/qwen3-reranker-0.6b-q8_0.gguf}"
if [[ ! -f "$PID_FILE" ]]; then echo "Reranker 未运行。"; exit 0; fi

PID="$(tr -d '[:space:]' < "$PID_FILE")"
[[ "$PID" =~ ^[0-9]+$ ]] || { echo "PID 文件无效，拒绝终止进程。" >&2; exit 1; }
if [[ -f "$ENV_FILE" ]]; then
  runtime_model="$(sed -n 's/^RERANKER_MODEL_PATH=//p' "$ENV_FILE")"
  [[ -z "$runtime_model" ]] || MODEL_PATH="$runtime_model"
fi
if ! kill -0 "$PID" 2>/dev/null; then
  unlink "$PID_FILE"; [[ -f "$ENV_FILE" ]] && unlink "$ENV_FILE"
  echo "已清理陈旧 PID；Reranker 未运行。"; exit 0
fi
COMMAND_LINE="$(ps -p "$PID" -o command= 2>/dev/null || true)"
if [[ "$COMMAND_LINE" != *"$MODEL_PATH"* || "$COMMAND_LINE" != *"--reranking"* ]]; then
  echo "PID $PID 不属于本项目 Reranker，拒绝终止。" >&2; exit 1
fi

kill -INT "$PID"
for ((attempt=1; attempt<=40; attempt++)); do
  kill -0 "$PID" 2>/dev/null || break; sleep 0.25
done
if kill -0 "$PID" 2>/dev/null; then
  kill -TERM "$PID"
  for ((attempt=1; attempt<=20; attempt++)); do
    kill -0 "$PID" 2>/dev/null || break; sleep 0.25
  done
fi
kill -0 "$PID" 2>/dev/null && { echo "PID $PID 未能退出；未发送强制信号。" >&2; exit 1; }
unlink "$PID_FILE"; [[ -f "$ENV_FILE" ]] && unlink "$ENV_FILE"
echo "Reranker 已停止（PID ${PID}）。"
