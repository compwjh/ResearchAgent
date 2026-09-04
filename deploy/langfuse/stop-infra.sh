#!/usr/bin/env bash
# 停止 Langfuse v4 的全部基础设施（顺序与启动相反）
#
# 关联：spec-013 / docs/sdd/plans/013/task-02-deploy-langfuse.md
# 每一步都允许失败（|| true），确保单个服务异常不阻断其余停止动作
#
# 用法：bash deploy/langfuse/stop-infra.sh

set -uo pipefail

PGBIN="/opt/homebrew/opt/postgresql@17/bin"
PGDATA="$HOME/opt/pgdata"

echo "== Langfuse 基础设施停止 =="

stop_by_port() {
  local port="$1" name="$2"
  local pid
  pid="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  if [ -n "$pid" ]; then
    kill "$pid" 2>/dev/null && echo "  [STOP] $name (port $port, pid $pid)" || echo "  [SKIP] $name 停止失败"
  else
    echo "  [SKIP] $name 未在运行 (port $port)"
  fi
}

# ---------- 1. MinIO ----------
echo "[1/4] MinIO"
stop_by_port 9002 MinIO

# ---------- 2. Redis ----------
echo "[2/4] Redis"
if lsof -nP -iTCP:6379 -sTCP:LISTEN -t >/dev/null 2>&1; then
  redis-cli -p 6379 shutdown nosave 2>/dev/null && echo "  [STOP] Redis" || stop_by_port 6379 Redis
else
  echo "  [SKIP] Redis 未在运行"
fi

# ---------- 3. PostgreSQL ----------
echo "[3/4] PostgreSQL"
if lsof -nP -iTCP:5432 -sTCP:LISTEN -t >/dev/null 2>&1; then
  LC_ALL=C LANG=C "$PGBIN/pg_ctl" -D "$PGDATA" stop >/dev/null 2>&1 \
    && echo "  [STOP] PostgreSQL" || stop_by_port 5432 PostgreSQL
else
  echo "  [SKIP] PostgreSQL 未在运行"
fi

# ---------- 4. ClickHouse ----------
echo "[4/4] ClickHouse"
if lsof -nP -iTCP:8123 -sTCP:LISTEN -t >/dev/null 2>&1; then
  # 优先用 SQL 优雅关闭，失败再按进程停止
  curl -s --max-time 5 'http://127.0.0.1:8123/' --data-binary "SYSTEM SHUTDOWN" >/dev/null 2>&1 || true
  sleep 3
fi
if lsof -nP -iTCP:8123 -sTCP:LISTEN -t >/dev/null 2>&1; then
  stop_by_port 8123 ClickHouse
else
  echo "  [SKIP] ClickHouse 未在运行"
fi

echo "== 停止完成 =="
echo "注意：本脚本不停止 Langfuse web/worker，如需停止请单独停 3000/3030 端口进程"
