# deploy/langfuse 部署说明

存放 Langfuse v4.27.0 的基础设施与启动脚本。

## 环境依赖
- Langfuse 源码：仓库内 `vendor/langfuse`（版本 v4.27.0，为项目内规范副本）
- Node：必须使用 nvm 的 **v24.20.0**
- 基础设施：ClickHouse(8123)、PostgreSQL(5432)、Redis(6379)、MinIO(9002)

## 文件说明
- **start-infra.sh**：启动四个基础设施（ClickHouse 8123 / PostgreSQL 5432 /
  Redis 6379 / MinIO 9002），幂等可重复执行，日志写入 `/tmp/langfuse-*.log`。
- **stop-infra.sh**：停止基础设施，按逆序执行。
- **start-langfuse.sh**：启动 web(:3000) 与 worker(:3030)；加 `--migrate`
  参数会先执行数据库迁移。
- **env.example**：环境变量模板。
- **clickhouse-grants.sql**：ClickHouse 权限脚本，新环境首次部署前执行。

## 常用命令

### 首次部署完整顺序
```bash
# 1. 执行 ClickHouse 授权
#    必须用 client 的 --multiquery：脚本是多语句，ClickHouse 的 HTTP 接口(8123)
#    默认拒绝多语句（报 Multi-statements are not allowed）
~/opt/clickhouse/clickhouse client --host 127.0.0.1 --port 9000 --user default \
  --multiquery < deploy/langfuse/clickhouse-grants.sql
# 2. 启动基础设施
deploy/langfuse/start-infra.sh
# 3. 配置环境变量
cp deploy/langfuse/env.example vendor/langfuse/.env
# 4. 启动 Langfuse（首次带迁移）
deploy/langfuse/start-langfuse.sh --migrate
```

### 日常启停
```bash
deploy/langfuse/start-infra.sh      # 起基础设施
deploy/langfuse/start-langfuse.sh   # 起 web/worker
deploy/langfuse/stop-infra.sh       # 停基础设施
```

## 常见问题
1. **MinIO 为何用 9002 而非默认 9000**：9000 被 ClickHouse
   native protocol 占用，故 MinIO 改用 9002。
2. **PostgreSQL 报 "postmaster became multithreaded during startup"**：
   locale 为空导致，需设 `LC_ALL=C`（脚本中已处理）。
3. **迁移报 "Not enough privileges ... grant TABLE ENGINE ON ..."**：
   表引擎权限不含在库级 `ALL` 内，需执行 `clickhouse-grants.sql`。
