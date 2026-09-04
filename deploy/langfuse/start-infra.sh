#!/usr/bin/env bash
# 启动 Langfuse v4 依赖的四个基础设施（非 Docker，全部以命令行常驻进程方式运行）
#
# 关联：spec-013 / docs/sdd/plans/013/task-02-deploy-langfuse.md
# 幂等：已在运行的服务会跳过（[SKIP]），可重复执行
# 日志：/tmp/langfuse-<service>.log
#
# 用法：bash deploy/langfuse/start-infra.sh

set -euo pipefail

PGBIN="/opt/homebrew/opt/postgresql@17/bin"
PGDATA="$HOME/opt/pgdata"
CH_DIR="$HOME/opt/clickhouse"
CH_DATA="$HOME/opt/clickhouse/data"
MINIO_DATA="$HOME/opt/minio-data"

echo "== Langfuse 基础设施启动 =="

# 端口是否已在监听
port_up() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1
}

# 等待端口就绪，超时判失败
wait_port() {
  local port="$1" name="$2" tries="${3:-40}" i=0
  while [ "$i" -lt "$tries" ]; do
    if port_up "$port"; then
      echo "  [OK]   $name 就绪 (port $port)"
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  echo "  [FAIL] $name 未就绪 (port $port)，检查 /tmp/langfuse-$name.log"
  return 1
}

# ---------- 1. ClickHouse（HTTP 8123 / native 9000）----------
# 重要：必须用「稳定版 26.4」官方二进制，不要用 builds.clickhouse.com 的 master 构建。
# 实测踩坑：master 构建（如 26.9.x）在与 Langfuse v4 配合时，会因 events_full 表
# start_time 列（DateTime64(6)，期望微秒）写入纳秒值而超出范围，导致 ALL observation
# 事件被丢弃（score 却能写入），表现成「能连上但看不到任何调用记录」。
echo "[1/4] ClickHouse"
if [ ! -x "$CH_DIR/clickhouse" ]; then
  echo "  [DL]  下载 ClickHouse 稳定版 26.4（官方二进制，非 master 构建）"
  mkdir -p "$CH_DIR"
  curl -sL --max-time 500 -o "$CH_DIR/clickhouse" \
    "https://builds.clickhouse.com/26.4/macos-aarch64/clickhouse"
  chmod +x "$CH_DIR/clickhouse"
fi
if port_up 8123; then
  echo "  [SKIP] ClickHouse 已在运行"
else
  mkdir -p "$CH_DATA"
  (cd "$CH_DIR" && nohup ./clickhouse server -- \
    --path="$CH_DATA/" \
    --logger.log=/tmp/langfuse-clickhouse.log \
    > /tmp/langfuse-clickhouse-stdout.log 2>&1 &)
  echo "  [START] ClickHouse 启动中"
fi
wait_port 8123 clickhouse

# ---------- 2. PostgreSQL（5432）----------
echo "[2/4] PostgreSQL"
if port_up 5432; then
  echo "  [SKIP] PostgreSQL 已在运行"
else
  mkdir -p "$PGDATA"
  # LC_ALL=C 必须显式设置：locale 为空时报 "postmaster became multithreaded during startup"
  LC_ALL=C LANG=C "$PGBIN/pg_ctl" -D "$PGDATA" \
    -l /tmp/langfuse-postgres.log -o "-p 5432 -k /tmp" start >/dev/null
  echo "  [START] PostgreSQL 启动中"
fi
wait_port 5432 postgres

# ---------- 3. Redis（6379）----------
echo "[3/4] Redis"
if port_up 6379; then
  echo "  [SKIP] Redis 已在运行"
else
  redis-server --daemonize yes --port 6379 \
    --logfile /tmp/langfuse-redis.log --dir /tmp >/dev/null
  echo "  [START] Redis 启动中"
fi
wait_port 6379 redis

# ---------- 4. MinIO（API 9002 / Console 9003；避让 ClickHouse native 9000）----------
echo "[4/4] MinIO"
if port_up 9002; then
  echo "  [SKIP] MinIO 已在运行"
else
  mkdir -p "$MINIO_DATA"
  MINIO_ROOT_USER=langfuse MINIO_ROOT_PASSWORD=langfuse_dev \
    nohup minio server --address :9002 --console-address :9003 "$MINIO_DATA" \
    > /tmp/langfuse-minio.log 2>&1 &
  echo "  [START] MinIO 启动中"
fi
wait_port 9002 minio

echo "== 基础设施汇总 =="
for item in "8123:ClickHouse" "5432:PostgreSQL" "6379:Redis" "9002:MinIO"; do
  port="${item%%:*}"
  name="${item##*:}"
  if port_up "$port"; then echo "  [OK]   $name ($port)"; else echo "  [FAIL] $name ($port)"; fi
done
echo "MinIO Console: http://127.0.0.1:9003"
echo "下一步：bash deploy/langfuse/start-langfuse.sh"
