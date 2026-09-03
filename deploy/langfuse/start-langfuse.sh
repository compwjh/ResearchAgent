#!/usr/bin/env bash
# 启动 Langfuse v4（web :3000 + worker :3030）
#
# 关联：spec-013 / docs/sdd/plans/013/task-02-deploy-langfuse.md
#
# 用法：
#   bash deploy/langfuse/start-langfuse.sh              # 直接启动（跳过迁移）
#   bash deploy/langfuse/start-langfuse.sh --migrate    # 先跑 Prisma + ClickHouse 迁移再启动
#
# 前置：bash deploy/langfuse/start-infra.sh
# 注意：Langfuse 要求 Node 24，本机系统默认是 v26，必须切到 nvm 的 v24.20.0

set -euo pipefail

LANG_FUSE_DIR="/Users/wjh/ResearchAgent/vendor/langfuse"
NODE_BIN="/Users/wjh/.nvm/versions/node/v24.20.0/bin"
RUN_MIGRATE="false"
[ "${1:-}" = "--migrate" ] && RUN_MIGRATE="true"

echo "== Langfuse v4 启动 =="

# ---------- 0. 环境检查 ----------
if [ ! -d "$LANG_FUSE_DIR" ]; then
  echo "[FAIL] 未找到 Langfuse 源码目录：$LANG_FUSE_DIR"
  exit 1
fi
if [ ! -f "$LANG_FUSE_DIR/.env" ]; then
  echo "[FAIL] 缺少 $LANG_FUSE_DIR/.env，请参考 deploy/langfuse/env.example 创建"
  exit 1
fi
if [ ! -x "$NODE_BIN/node" ]; then
  echo "[FAIL] 未找到 Node 24：$NODE_BIN/node（Langfuse 要求 Node 24，系统默认的 v26 不匹配 .nvmrc）"
  exit 1
fi

export PATH="$NODE_BIN:/opt/homebrew/bin:$PATH"
echo "  [OK]   Node $(node -v) / pnpm $(corepack pnpm -v 2>/dev/null || echo '?')"

# ---------- 1. 基础设施就绪检查 ----------
echo "[1/3] 基础设施检查"
missing=0
for item in "8123:ClickHouse" "5432:PostgreSQL" "6379:Redis" "9002:MinIO"; do
  port="${item%%:*}"
  name="${item##*:}"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "  [OK]   $name ($port)"
  else
    echo "  [FAIL] $name ($port) 未运行"
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  echo ""
  echo "请先启动基础设施：bash deploy/langfuse/start-infra.sh"
  exit 1
fi

# ---------- 2. 迁移（可选）----------
echo "[2/3] 数据库迁移"
if [ "$RUN_MIGRATE" = "true" ]; then
  (cd "$LANG_FUSE_DIR" && pnpm --filter=shared run db:deploy) && echo "  [OK]   Prisma 迁移完成"
  (cd "$LANG_FUSE_DIR" && pnpm --filter=shared run ch:up) && echo "  [OK]   ClickHouse 迁移完成"
else
  echo "  [SKIP] 跳过迁移（需要时加 --migrate 参数）"
fi

# ---------- 3. 启动 web + worker ----------
echo "[3/3] 启动 web(:3000) 与 worker(:3030)"
if lsof -nP -iTCP:3000 -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "  [SKIP] Langfuse web 已在运行"
else
  (cd "$LANG_FUSE_DIR" && nohup sh -c "pnpm run dev" > /tmp/langfuse-web.log 2>&1 &)
  echo "  [START] 启动中（首次编译需数十秒）"
fi

# 等待就绪
ready=0
for _ in $(seq 1 60); do
  if lsof -nP -iTCP:3000 -sTCP:LISTEN -t >/dev/null 2>&1 \
     && lsof -nP -iTCP:3030 -sTCP:LISTEN -t >/dev/null 2>&1; then
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 40 http://127.0.0.1:3000 || echo 000)"
    if [ "$code" = "200" ]; then ready=1; break; fi
  fi
  sleep 2
done

echo ""
if [ "$ready" -eq 1 ]; then
  echo "== Langfuse 已就绪 =="
  echo "  访问地址：http://127.0.0.1:3000"
  echo "  Web 日志：tail -f /tmp/langfuse-web.log"
  echo "  登录账号：见 $LANG_FUSE_DIR/.env 中的 LANGFUSE_INIT_USER_EMAIL / LANGFUSE_INIT_USER_PASSWORD"
else
  echo "== 启动未完成 =="
  echo "  请查看日志：tail -f /tmp/langfuse-web.log"
  echo "  若端口未监听，检查 Node 版本是否为 24、依赖是否已 pnpm install"
fi
