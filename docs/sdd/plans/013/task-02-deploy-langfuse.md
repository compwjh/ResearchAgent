# 任务 02 — 非 Docker 部署基础设施与 Langfuse v4（Go/No-Go 关卡）
>
> 当前状态：`完成`

> 关联：[spec-013](../../specs/013-llm-observability-platform.md) ｜ 索引：[README](./README.md)
> **本任务是整体可行性闸门**：ClickHouse 若装不起来，后续全部工作作废，必须在此止损。
## 目标

在**不使用 Docker** 的前提下，把 Langfuse v4 依赖的四个基础设施（PostgreSQL / Redis / MinIO / ClickHouse）用命令行装好并常驻，再拉起 Langfuse v4 的 web 与 worker，最终能在浏览器打开并创建项目拿到 API Key。

## 思维链

### 阶段 A：验证最高风险项（ClickHouse）

**为什么先做这个**：其他三个组件 brew 直接可装，确定性高；ClickHouse 是唯一可能让方案整体不成立的点（brew 条目报错，且 Langfuse v4 要求 ≥25.12）。先验证它，能最早止损。

1. 下载 ClickHouse 官方单文件二进制（macOS ARM）
2. 校验版本 ≥ 25.12（不满足则记录实际版本并评估）
3. 以本地数据目录启动 server，确认端口 8123 可连通
4. **判定**：版本达标且可跑 → 继续；否则 → 停在本阶段，回需求评审重新选型

### 阶段 B：安装其余基础设施

5. `brew install postgresql@17 redis minio`
6. 初始化 Postgres 数据目录并启动，创建 Langfuse 专用库与用户
7. 启动 Redis，确认端口 6379 连通
8. 启动 MinIO，创建 Langfuse 用的 bucket
9. **授予 ClickHouse 用户 v4 所需的额外权限**（官方清单，见 spec「关键调研结论」）——漏了会导致 schema 迁移报 `Not enough privileges`

### 阶段 C：准备 Langfuse 运行时

10. 装 Node 24（当前 v26，与 `.nvmrc` 不一致）与 pnpm 11.22（corepack）
11. 拉 Langfuse v4 稳定 tag 源码
12. `pnpm install` 装依赖（耗时较长，需后台跑并轮询日志）
13. 写 `.env`（含 PG / ClickHouse / Redis / MinIO 连接串与密钥）
14. 跑 Prisma 迁移（Postgres）与 ClickHouse 迁移

### 阶段 D：启动与验证

15. 启动 web（:3000）与 worker（:3030）
16. 打开 Web UI，注册首个用户、创建项目、拿到 `pk-lf-*` / `sk-lf-*` Key
17. 记录 Key 到项目配置（供任务 04/05 埋点使用）

## 子代理分派计划

> 背景：近期 `junior-dev`（27B）在长流程任务中两次零产出且超时后仍在后台写文件覆盖他人代码（见 `docs/sdd/retro/2026-09-01-subagent-model-naming.md`）。因此本任务**只把「写启停脚本」这一单文件、无副作用的窄任务**分派出去，安装与启动等有系统副作用的动作全部由主会话执行。

### 分派 1：`junior-dev` — 编写启停脚本（窄任务）

**分派时机**：阶段 B 完成后（此时已确认路径与端口，脚本内容才准确）。

**Prompt 要点**（分派时必须写明的部分）：

- **输出文件**（必须原样写明路径，要求 agent 只写这几个文件）：
  - `deploy/langfuse/start-infra.sh`
  - `deploy/langfuse/stop-infra.sh`
  - `deploy/langfuse/start-langfuse.sh`
  - `deploy/langfuse/env.example`
- **明确禁止**：不要执行任何安装/启动命令，不要修改项目内其他任何文件，不要创建其他文件。
- **输出格式**：输出每个文件的**完整内容**（不是 diff），由架构师 apply。
- **上下文**：给出实测得到的路径与端口（Postgres/Redis/MinIO/ClickHouse 数据目录、brew prefix、监听端口）。
- **硬性要求**：脚本 `set -euo pipefail`；幂等（重复执行不报错）；每个服务启动后做端口健康检查并打印结果；日志统一落到 `/tmp/langfuse-*.log`。

**子代理返回后，主会话必须做**：

1. 逐文件核对：只落盘约定的 4 个文件，`git status` 确认无越界改动
2. `bash -n` 语法检查每个脚本
3. 实际执行 `start-infra.sh`，验证四个服务都能起来
4. 执行 `stop-infra.sh` 再 `start-infra.sh`，验证幂等
5. 若脚本有缺陷，主会话直接修正，**不再回退给子代理**（避免来回耗时）

### 不分派的部分

安装、权限授予、迁移、启动、UI 验证——全部主会话执行。理由：这些动作有系统副作用且需要实时判断输出，子代理失败成本高。

## 实时监控命令（供你另开终端查看）

```bash
# ClickHouse 启动日志
tail -f /tmp/langfuse-clickhouse.log

# PostgreSQL / Redis / MinIO
tail -f /tmp/langfuse-postgres.log
tail -f /tmp/langfuse-redis.log
tail -f /tmp/langfuse-minio.log

# Langfuse 依赖安装（耗时最长，重点看这个）
tail -f /tmp/langfuse-install.log

# Langfuse web / worker 运行日志
tail -f /tmp/langfuse-web.log
tail -f /tmp/langfuse-worker.log

# 一次性检查四个基础设施端口
lsof -nP -iTCP:5432,6379,9000,8123 -sTCP:LISTEN | grep LISTEN

# 检查 Langfuse 是否在跑
lsof -nP -iTCP:3000,3030 -sTCP:LISTEN | grep LISTEN
curl -s -o /dev/null -w "langfuse-web:%{http_code}\n" http://127.0.0.1:3000
```

子代理产出落盘后，可用这个命令盯文件出现：

```bash
ls -la deploy/langfuse/ 2>/dev/null || echo "尚未产出"
```

## 验收标准

| 项 | 标准 |
|---|---|
| ClickHouse | 版本 ≥ 25.12，端口 8123 连通，v4 所需 GRANT 已授予 |
| PostgreSQL | 端口 5432 连通，Langfuse 库与用户可登录 |
| Redis | 端口 6379 连通 |
| MinIO | 端口 9000 连通，bucket 已创建 |
| Langfuse web | `http://127.0.0.1:3000` 返回 200，UI 可注册 |
| Langfuse worker | 端口 3030 健康 |
| API Key | 已拿到 `pk-lf-*` 与 `sk-lf-*` |
| 脚本 | 4 个脚本可幂等启停，`bash -n` 通过 |

## 风险与 Go/No-Go

| 风险 | 触发后的处置 |
|---|---|
| ClickHouse 二进制下载失败或版本 < 25.12 | **立即止损**，停在本任务，回需求评审重新选型（Cloud / 自建轻量方案），不投入后续任务 |
| ClickHouse 在 macOS 上启动异常（端口占用、权限） | 尝试换端口/换数据目录；两次修复仍失败则按上一条止损 |
| Node 版本冲突（现 v26 需降 24） | 用 nvm/volta 装 24 并局部使用，不改系统默认 |
| `pnpm install` 超时或依赖冲突 | 看日志定位；可重跑（pnpm 有缓存）；两次失败则记录阻塞 |
| schema 迁移报 `Not enough privileges` | 补 GRANT 后重跑迁移 |
| Langfuse 启动后长时间不 Ready | 查 web 日志；常见是 ClickHouse/Redis 连接串错误 |

## 产出物

- `deploy/langfuse/start-infra.sh`、`stop-infra.sh`、`start-langfuse.sh`、`env.example`
- `deploy/langfuse/clickhouse-grants.sql`（v4 权限脚本）
- 本文档「验收标准」逐项打勾的结果，回写到下方「执行结果」段

## 执行结果（2026-09-02 完成，Go/No-Go：通过）

| 验收项 | 标准 | 实测结果 | 结论 |
|---|---|---|---|
| ClickHouse | ≥25.12 | **26.9.1**（官方单文件二进制，macOS arm64） | 通过 |
| PostgreSQL | ≥15 | **17.11**（brew），库 `langfuse` | 通过 |
| Redis | ≥7.0 | **8.10.1**（brew），PONG | 通过 |
| MinIO | S3 兼容 | RELEASE.2025-10-15，bucket `langfuse` 已建 | 通过 |
| Langfuse web | 3000 返回 200 | **HTTP 200**，`/api/public/health` → `{"status":"OK","version":"4.27.0"}` | 通过 |
| Langfuse worker | 3030 健康 | 已监听，后台迁移跑完（"No background migrations to run"） | 通过 |
| API Key | 拿到 pk/sk | `pk-lf-local-dev-0001` / `sk-lf-local-dev-0001` | 通过 |
| 脚本 | 4 个可幂等启停 | `bash -n` 全通过；重跑 `start-infra.sh` 全部 [SKIP] | 通过 |

**部署版本**：Langfuse **v4.27.0**（源码自托管，dev 模式 `pnpm run dev`）｜源码目录 `~/opt/langfuse-src/langfuse`｜Node 24.20.0（nvm）｜pnpm 11.22.0

### 实际落盘产物

- `deploy/langfuse/start-infra.sh` — 四个基础设施启停（幂等 + 端口健康检查）
- `deploy/langfuse/stop-infra.sh` — 逆序停止，单步失败不中断
- `deploy/langfuse/start-langfuse.sh` — 前置检查 + `--migrate` 可选迁移 + 启动 web/worker
- `deploy/langfuse/env.example` — 全量环境变量模板（含两个坑的注释）
- `deploy/langfuse/clickhouse-grants.sql` — v4 所需权限授权脚本

### 执行中遇到的坑（已解决，均写入脚本注释或 env.example）

1. **ClickHouse 不能装 brew**：`brew info clickhouse` 报 `undefined method 'first' for nil`。改走官方单文件二进制 `curl https://clickhouse.com/ | sh`，实测版本 26.9.1 达标。
2. **MinIO 与 ClickHouse 端口冲突**：两者默认都占 9000。把 MinIO 改到 API 9002 / Console 9003。
3. **PostgreSQL 启动报 `postmaster became multithreaded during startup`**：locale 环境变量为空所致。initdb 与 pg_ctl 启动都需显式 `LC_ALL=C LANG=C`。
4. **github.com 主站不通**（curl 返回 000），但 `codeload.github.com` 与 `api.github.com` 可达 → 用 codeload 下载 tag tarball 绕过，用 API 查版本列表拿到最新 tag `v4.27.0`。
5. **ClickHouse 迁移反复报权限不足**：`GRANT ALL ON default.*` 不含表引擎权限，需逐个 `GRANT TABLE ENGINE ON MergeTree/ReplacingMergeTree/...`。
6. **迁移中断留下 dirty 状态**：`Dirty database version 1`。全新部署无历史数据，直接清空 `default` 库重跑解决。
7. **无头初始化没建 API Key**：`.env` 需显式成对配置 `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `LANGFUSE_INIT_PROJECT_SECRET_KEY`；补上后重启即创建（按 publicKey 做 upsert，无需重建项目）。
8. **`ch:up` 要求 `CLICKHOUSE_PASSWORD` 非空**：空字符串被脚本判为未设置，故创建专用用户 `langfuse` 并设口令。

### 子代理分派结果

- `junior-dev` 分派「编写 4 个部署脚本」→ **超时无产出**（idle timeout）。
- 处置：确认无残留文件与越界改动（`git status` 干净）后，由架构师主会话直接编写全部脚本。
- **根因已查明并解决（见任务 03）**：不是命名/配置问题（那类问题会直接报 `model not found`，2026-09-01 已解决），而是 **27B GGUF 模型吞吐仅 13.8 tok/s + 每次 7~9 秒冷启动 + 系统内存压力（swap 86%）** 导致生成耗时超出子代理超时。改用 `qwen3.8:27b-mlx`（24.3 tok/s）后，分派窄任务实测成功。详见 `docs/sdd/retro/2026-09-02-subagent-timeout-mlx.md`。

### 补充：本任务的 README 由 junior-dev 补写（修复后验证）

- 修复模型后分派极窄任务（写 `deploy/langfuse/README.md`，≤60 行）→ **成功**，220.84s。
- 落地校验抓到两处错误并已修正：①把 `mysql -P8123` 改成 ClickHouse 的调用方式（本机无 mysql，8123 是 HTTP 接口）②curl 提交多语句被拒（`Multi-statements are not allowed`），最终改为 `clickhouse client --multiquery`，实测 74 项授权生效。
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-013-task-02",
  "spec_id": "013",
  "title": "# 任务 02 — 非 Docker 部署基础设施与 Langfuse v4（Go/No-Go 关卡）",
  "status": "completed",
  "priority": 100,
  "created_at": "2026-10-19T01:04:27+00:00",
  "depends_on": [],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/013/task-02-deploy-langfuse.md",
    "docs/sdd/plans/016/artifacts/legacy-task-audit.md",
    "docs/sdd/TASK-PROTOCOL.md"
  ],
  "worktree": {
    "path": ".worktrees/spec-013",
    "branch": "feature/spec-013-llm-observability-platform",
    "mode": "per_spec",
    "base_rule": "explicit_commit"
  },
  "max_attempts": 3,
  "prompt_version": 1,
  "return_schema": "sdd-run-result/v1",
  "expected_artifacts": [],
  "validation_commands": [],
  "migration_state": "verified"
}
<!-- sdd-task-meta:v1:end -->
<!-- sdd-task-prompt:v1:begin -->
Role: backend-tester
Read: ["docs/sdd/plans/013/task-02-deploy-langfuse.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/013/task-02-deploy-langfuse.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
