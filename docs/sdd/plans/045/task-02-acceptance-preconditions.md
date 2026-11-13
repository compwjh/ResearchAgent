> 关联：[spec-045](../../specs/045-evaluation-observability-hardening.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`（2026-11-08 接手机器真实取证）

# Task 02 — 验收前置：启用 Langfuse + 可复现样本 + 真实 E2E

## 状态与一句话目标

`已完成`。在受控环境里让 Langfuse 与真实 Ollama 都处于可用状态，产出一批可复现样本，
并跑通一次非 mock 的端到端，作为 spec-045 全部后续任务的**验收硬前置**。
本任务由验收执行者完成，**不由开发任务代劳**（Q9 裁决）。

## 背景与前置条件

- 必读：[spec-045](../../specs/045-evaluation-observability-hardening.md) 的 F6/F10/F17、
  Q8/Q9/Q10 与「验收」章节；[ADR 0002](../../../adr/0002-langfuse-precondition-and-offline-evaluation-scope.md)。
- 现状：Langfuse 默认关闭（`backend/app/platform/config.py:122`，根 `.env` 无 `LANGFUSE_*`）；
  评测与观测测试全为 mock（`docs/sdd/plans/042/task-04-offline-evaluation-delivery.md:92`）。
- 自托管栈：`deploy/langfuse/start-langfuse.sh:15-17,42-51,67-85`，
  依赖 ClickHouse 8123 / PostgreSQL 5432 / Redis 6379 / MinIO 9002，Node 24。
- 远程 Ollama：`OLLAMA_BASE_URL=http://192.168.31.180:11434`（根 `.env` 已配置，2026-11-08 实测可达）。
- **前置要求**：用户已明确「确认 spec-045」且需求/技术评审通过、状态转 `已确认`
  （`AGENTS.md:35,118`）；在此之前本任务不启动。

## 数据、配置与接口

- 只读：Langfuse `GET /api/public/traces`、`GET /api/public/scores/{id}`（Basic Auth）。
- 配置：`LANGFUSE_ENABLED=true`、`LANGFUSE_HOST`、`LANGFUSE_PUBLIC_KEY/SECRET_KEY`、
  `OBSERVABILITY_MODE=dual`（`spec-041:17-30,50-56` 说明 `events_only` 下 observations 为空、
  瀑布图不可用；改 `dual` 后历史 trace 不回填）。
- 造样本脚本：`scripts/generate_observability_fixtures.py`（默认 dry-run，`--send` 才写 SDK，
  `:191-242` 固定 20 条矩阵）；`scripts/setup_langfuse_dashboards.py`（幂等建 6 组看板）。
- `scripts/gen_observability_samples.py` 会真实卸载模型制造冷启动且自述勿用 27B，
  **本任务优先用 fixtures 脚本**，避免影响共享 Ollama。
- 不新增业务端点、不改业务表结构、不写业务库（spec-042 边界 8）。

## 实施步骤与文件边界

1. 起自托管 Langfuse 栈并确认 web/worker 健康；记录版本与端口。
2. 在**受控副本**（不直接改仓库根 `.env` 的已提交内容，除非用户授权）注入配置并重启 8000 服务；
   确认 `LANGFUSE_ENABLED=true` 生效。
3. `scripts/generate_observability_fixtures.py --send` 造 20 条可复现样本；
   用 `setup_langfuse_dashboards.py` 幂等建看板。
4. 跑一次真实对话（chat 与 kb-ask 各一），在 Langfuse 得到含四段 phase span 的完整 trace，
   记录 `trace_id`。
5. 跑一次真实 `eval_042` CLI（`--export` 或冻结数据集），产出 `report.json` + `report.md`。
6. 产物路径写入 `docs/sdd/plans/045/runs/task-02/`（执行后创建），
   包含：配置快照（脱敏）、trace ID、CLI 命令与退出码、报告路径、瀑布图截图。

**文件边界**：仅 `deploy/langfuse/` 运行态产物、`docs/sdd/plans/045/runs/task-02/`、
以及用户明确授权的 `.env` 配置行；**不改** `backend/**`、`frontend/**`、`tests/**`。

## 子代理分派

- 本任务为运行态与文档动作，不含代码文件改动 → 主会话代行
  （`AGENTS.md:127`），三处留痕见 README「前置与范围」。
- 若后续需要修改任何 `.py` 脚本（例如修 `--send` 缺陷），必须先 `Task(backend-dev)` 分派，
  禁止主会话代写（`AGENTS.md:127,128`）。

## 边界与明确不做

- **不做** P2 三项：人工标注 gold 集、分数口径统一、在线实时评测。
- **不做** 11 项加固中的任何代码改动；本任务只搭环境与取证。
- **不改** `LANGFUSE_SAMPLE_RATE` 默认语义、不改上报字段、不改瀑布图语义。
- 不 push、不合 main（`AGENTS.md:138`）。
- 环境未就绪时**不宣称完成**，spec 保持 `实施中` 并记录阻塞原因。

## 验收、风险与回滚

| 验收点 | 可观察结果 |
|---|---|
| Langfuse 可用 | web/worker 健康，public API 返回 200 |
| 样本可复现 | 20 条 fixtures 矩阵产物落盘，trace 名/时间/score 可查 |
| 真实 E2E | 一条含四段 phase span 的 trace + CLI `report.json/md`，均非 mock |
| 配置可回退 | 记录关闭步骤；关闭后主服务功能不受影响（`HANDOFF-2026-09-21:30-31,144`） |

风险：自托管栈依赖四个外部服务；共享 Ollama 被 `keep_alive:0` 卸载会影响其他会话；
`dual` 模式不回填历史 trace。失败时回滚到 `LANGFUSE_ENABLED=false` 并回到任务 01 状态，
不进入 task 03–07。

## 产出物、执行结果与变更日志

初始写「待执行后填写」。执行后回填：真实命令、HTTP 状态码、trace ID、报告路径、
截图路径、退出码、配置脱敏快照，以及 `spec-status-changelog.md` 对应条目。

## 环境阻塞记录（2026-11-08，主会话只读核实）

**P0-1 已消解**：`deploy/langfuse/start-langfuse.sh:15` 的失效硬编码路径已由
`backend-dev` 改为基于 `SCRIPT_DIR` 的相对解析（保留 `LANG_FUSE_DIR` env 覆盖），
`bash -n` 通过、绝对路径/相对路径/env 覆盖三种调用均解析到真实
`vendor/langfuse`（含 `package.json`）。日志：
`.codebuddy/agent-logs/spec-045/task-02/backend-dev/20261108-014522.md`。

**新发现的上游阻塞（未消解，需用户决策）**：本机 Langfuse 自托管栈的**运行前置全部缺失**：

| 前置 | 期望 | 实测 |
|---|---|---|
| Node 24 | `/Users/wjh/.nvm/versions/node/v24.20.0/bin` | 缺失 |
| PostgreSQL 17 | `/opt/homebrew/opt/postgresql@17/bin` | 缺失 |
| PG/ClickHouse/MinIO 数据目录 | `$HOME/opt/{pgdata,clickhouse,minio-data}` | 全部缺失 |
| 二进制 | `clickhouse` / `redis-server` / `minio` / `psql` | 全部缺失 |
| Langfuse `.env` | `vendor/langfuse/.env` 或 `deploy/langfuse/.env` | 缺失 |
| 依赖 | `vendor/langfuse/node_modules` | 缺失 |
| 端口 | 3000 / 3030 / 8123 / 5432 / 6379 / 9002 | 全部未监听 |

这属于**系统级软件安装与初始化**（超出 spec 11 项加固范围，也超出
「本期不改配置」的 Q8 边界），主会话**未擅自安装**。因此：

- Task 02 的「启用 Langfuse + 造真实样本 + 真实 E2E」**暂不可执行**；
- 按 Q9/Q10，缺此硬前置则 Q10 证据 ②③④ 无法产出，
  spec **不得判 `已完成`**，状态保持 `已确认`/`实施中` 并记录阻塞；
- **执行顺序调整（不改 DAG 语义）**：Task 03–07 中「纯代码 + mock/契约测试」部分
  不依赖真实 Langfuse，先行推进并各自补红绿测试；
  真实取证统一留到 Task 08，待环境就绪后一次性完成。
  此调整不改变 spec 的目标、数据模型、公开接口与用户行为，
  不触发 `AGENTS.md:68,112` 的退回重新确认。

**解除阻塞所需的用户决策**（三选一，尚未执行）：
1. 授权按 `deploy/langfuse/start-infra.sh` 安装并初始化四个基础设施 + Node 24 + 依赖；
2. 提供一台已部署 Langfuse 的地址与凭据，改走远端；
3. 明确接受「仅交付代码与契约测试，真实 E2E 长期挂起」，
   并在验收结论中声明 Q10 证据 ②③④ 缺失。

## 部署执行结果（2026-11-08，用户授权「按 README 部署」）

用户澄清「原始文件指 `vendor/langfuse` 源码」，授权主会话自行安装。
**P0-1 与基础设施已消解**，但 **Q10 真实取证仍未完成**，见下。

### 已完成（真实命令与输出均已核实）
| 步骤 | 结果 |
|---|---|
| 路径适配 | `hy4` 子代理把 `start-infra.sh` / `start-langfuse.sh` 的 PGBIN、ClickHouse 下载 URL、NODE_BIN 改为自动探测（本机 x86_64 / brew `/usr/local` / Node `~/opt/node24`）；`bash -n` 通过。日志 `.codebuddy/agent-logs/spec-045/task-02/backend-dev/20261108-040435.md` |
| ClickHouse | 下载官方 **26.4.6.6 Mach-O x86_64** 到 `~/opt/clickhouse/clickhouse`（脚本原 `macos-aarch64` 不适用；x86_64 正确地址为 `26.4/macos`） |
| PostgreSQL / Redis | brew 编译链损坏（CMake bootstrap 失败 / `cstdint` 缺失 / docker cli-plugins 权限），改用 **conda 预编译**装出 PG 17.4 + Redis 到 `~/opt/langfuse-infra`；`initdb`、建 `langfuse` role/db 完成 |
| MinIO | brew bottle 安装成功 |
| Node / pnpm | Node v24.20.0 官方 x64 包到 `~/opt/node24`；corepack shim 修复后 `pnpm install --frozen-lockfile` **完整通过**（`Done in 47.1s`，postinstall 0 失败） |
| 迁移 | ClickHouse 授权 `--multiquery` 成功；**Prisma 迁移完成**；补装 `golang-migrate 4.18.3` 后 **ClickHouse 46 个迁移全部应用**；`prisma generate` 生成 v6.19.3 Client |
| 启动 | 四端口 8123 / 5432 / 6379 / 9002 全部 LISTEN；Langfuse web **HTTP 200**、worker 3030 曾监听 |

### 遗留阻塞（本轮未消解，spec 不判已完成）
1. **public API 被 `events_only` 模式硬阻断**：`/api/public/traces`、`/api/public/scores` 返回 404
   「not available on deployments running in Langfuse v4 events_only mode」。已按 `spec-041:48-52`
   在 `vendor/langfuse/.env` 追加 `LANGFUSE_MIGRATION_V4_WRITE_MODE="dual"`，**重启验证未成功**
   （见下条磁盘问题），因此评测 `--export` 与 score 回写仍不可用。
2. **磁盘硬约束（真实根因）**：本机数据卷 233Gi、已用 195Gi，
   Next.js 16 Turbopack 的 `web/.next` 在 dev/build 下**数分钟内涨到 831MB 并持续增长**，
   期间 `/System/Volumes/Data` 可用空间从 8.5Gi 降至 108Mi，多次触发
   `no space left on device`、Next.js `PoisonError` panic、PostgreSQL WAL 写失败。
   生产构建 `next build` 亦卡死（4 分钟 CPU 0%、无进展）。
   主会话已停止所有 dev/watch 进程、清除 `.next` 与本轮临时文件，
   数据卷恢复 **2.1Gi 可用**，四个基础设施保留运行。
   **8.1Gi 的 `~/Library/Logs/JetBrains` 属用户 IDE 数据，未删除。**
3. 因此 **Q10 证据 ②（真实 CLI report）/ ③（可查 trace）/ ④（瀑布图截图）仍未产出**，
   真实 E2E 未跑通，Task 08 不能收口。

### 下一步所需决策（未执行）
1. 用户清理磁盘（如 JetBrains 日志）或提供 ≥10Gi 可用空间后，重启 web/worker 验证 `dual`；
2. 或改用已部署的远端 Langfuse；
3. 或明确接受真实 E2E 长期挂起，在验收结论声明证据 ②③④ 缺失。

## 接手机器执行结果（2026-11-08，Apple M3 Max / arm64）

**状态：已完成。** 发送方记录的三大阻塞（events_only 404、磁盘不足、基础设施缺失）在本机均不成立。

| 验收点 | 真实结果 |
|---|---|
| Langfuse 可用 | 8123/5432/6379/9002 全 OK；web 3000 + worker 3030 LISTEN；`/api/public/health`、`/traces`、`/scores` 均 200（**dual 生效**） |
| 样本可复现 | `--send` 20 条，`fixture_id=spec013-task06-20261108T060158Z`，Langfuse 可查 |
| 真实 E2E | `POST /api/conversations/messages` HTTP 200、`status=completed`；trace `98b91aa39d22b54a50f6dba1364eccdd` 含 `phase:prefill/load/overhead/decode` 四段 span + GENERATION |
| 配置可回退 | 根 `.env` 本为 gitignored 运行态文件，未改已提交内容；关闭只需 `LANGFUSE_ENABLED=false` 并重启 |
| CLI 评测 | `eval_042` 真实 `--export` → `report.json`/`report.md` 五类指纹齐全，score 真实回写 |
| score 幂等 | 重跑前后 `totalItems 979 → 979`，零新增 |

主服务已重启（`com.researchagent.recovery8000`，PID 37370），`/` 与 `/api/health` 均 200。
首次用 `qwen3.5:9b` 因能力缓存不含 `off` 报 `REASONING_EFFORT_UNSUPPORTED`（调用参数问题，非缺陷），
改用 `qwen3.8:27b` 成功。

**命令全文、实体 ID、产物路径与未完成项**：[`runs/task-02/evidence.md`](./runs/task-02/evidence.md)。

> 仍有 Q10 证据 ①（红绿汇总）与 ④（瀑布图浏览器截图）留待 Task 08；
> Task 07 未落地、Task 08 未执行，故 spec **不判 `已完成`**。
