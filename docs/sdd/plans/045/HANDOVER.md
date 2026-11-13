# SPEC-045 交接文档

> 创建时间：2026-11-08
> 交接原因：本机（macOS x86_64）因环境搭建与子 agent 限流原因暂停，
> 转交**另一台机器**继续完成剩余 task（02 / 04 / 06 / 07 / 08）。
> 本分支已 `git push` 到 `origin/main`，另一台机器 `git pull` 即可获取全部改动。

## 1. 分支与远程

- 分支：`main`
- 远程：`git@github.com:compwjh/ResearchAgent.git`
- 本次待提交改动共 53 个文件（29 modified + 24 untracked），全部属于 spec-045 工作，
  已在本 push 中提交。另一台机器直接 `git pull` 即可，无需补做任何本地改动。

## 2. 改动内容概览

| 类别 | 文件 | 说明 |
|---|---|---|
| spec 文档 | `docs/sdd/specs/045-*.md`、`docs/sdd/notes/045-*.md`、`docs/adr/0002-*.md`、`docs/sdd/plans/045/*`、`docs/sdd/reviews/045-*`、`docs/sdd/spec-status-changelog.md` | spec-045 全套（状态 `已确认`） |
| 子 agent 配置 | `.codebuddy/agents/*.md` | model 字段 `hy3 → hy4`（因 hy3 限流临时决策，见第 6 节） |
| 评测后端 | `backend/eval_042/runner.py`、`judge_client.py`、`langfuse_export.py`、`report.py`、`config.py` | Task 03 实现 + Task 04 半完成（见第 3 节） |
| 观测后端 | `backend/app/platform/observability/client.py`、`config.py`、`trace.py`、`spans.py`、`__init__.py` + 新增 `redaction.py`、`request_id.py`、`sdk_compat.py` | Task 05 实现 + Task 06 骨架 |
| 部署脚本 | `deploy/langfuse/start-infra.sh`、`start-langfuse.sh` | 适配本机 x86_64（PGBIN/`NODE_BIN` 自动探测、ClickHouse x86_64 URL） |
| 种子/测试 | `scripts/seed_demo_literature_maps.py`、`scripts/seed_demo_research_reports.py`、`tests/evaluation/test_task03_*.py`、`tests/evaluation/test_task04_*.py`、`tests/observability/test_task05_*.py`、`tests/platform/test_task06_*.py` | Task 03/05 测试 + Task 04/06 测试骨架 |
| 其他业务修改 | `backend/app/api/routes_*.py`、`backend/app/memory/repository.py` | 由 Task 05/06 顺带改动的调用点 |

## 3. Task 完成状态（spec-045）

| Task | 状态 | 说明 |
|---|---|---|
| 01 编写 spec | 完成 | 文档齐全，状态 `已确认` |
| 02 验收前置（部署 Langfuse） | **待执行** | 另一台机器**必须先做**：按 `deploy/langfuse/README.md` 部署 v4.27.0 栈、造可复现样本、跑通真实 E2E |
| 03 评测可信度 | 基本完成 | `runner.py` 三 judge fallback 生效、`JUDGE_SEED=42`、`stably_sort_items`、数据集 SHA256、`report.py` metadata 指纹；`test_task03_reproducibility.py` 通过 |
| 04 score 幂等 + 报告文件锁 | **半完成** | `report.py` 已用 `fcntl.flock` 包裹 `checkpoint`（完整）；`langfuse_export.post_score_idempotent()`（`:173`）已定义但**未接入 runner**；`test_task04_idempotency.py` 已写，需先红后绿 |
| 05 观测解耦 | 基本完成 | `client.py` 后台队列 `enqueue_flush()`、`config.py`/`trace.py` ContextVar 采样、`sdk_compat.py` 私有符号兼容层；`test_task05_decoupling.py` 通过 |
| 06 trace/脱敏/thinking | **待执行（骨架在）** | 已建 `redaction.py`、`request_id.py`、`test_task06_identity_redaction.py`，但未接入调用链 |
| 07 retention / 基准卡片 | **待执行** | — |
| 08 集成测试与验收 | **待执行** | 依赖 02–07 完成 |

> 结论：**代码未破坏**，可在另一台机器直接继续；剩余硬骨头是 Task 02（环境）与 Task 04 收尾、06/07/08。

## 4. 关键代码位置（接手速查）

- 幂等函数定义：`backend/eval_042/langfuse_export.py:173` `post_score_idempotent()`
- 报告文件锁：`backend/eval_042/report.py`（`fcntl.flock` 包裹 `checkpoint`）
- 后台队列 flush：`backend/app/platform/observability/client.py`（`queue.Queue` + 工作线程 + `enqueue_flush()`）
- 私有 SDK 兼容层：`backend/app/platform/observability/sdk_compat.py`（显式降级 + 告警）
- 采样 ContextVar：`backend/app/platform/observability/trace.py` / `config.py`
- 脱敏 / request_id 骨架：`backend/app/platform/observability/redaction.py`、`request_id.py`

## 5. 单测基线（本机最后一次验证）

- 全仓 pytest 基线：**212 通过**（代码结构未破坏）
- `eval_042` 相关：**149 通过**
- 观测 Task 05：**67 + 48 通过**

## 6. 环境注意（本机 ≠ 另一台机器）

- 本机架构 **x86_64**，brew 在 `/usr/local`；为本地部署下载的 ClickHouse/Node24 二进制（原在 `~/opt`）已在本机删除，不影响仓库。
- **Langfuse 栈在本机未实际跑起来**，端口全灭。另一台机器须自行按 `deploy/langfuse/README.md` 部署（仓库内 `vendor/langfuse` 为 v4.27.0 规范副本，已随本分支提交）。
- 子 agent `.codebuddy/agents/{backend-dev,frontend-dev}.md` 的 `model: hy4` 是限流时的临时决策，**不影响代码逻辑**。若另一台机器 hy3 不限流，可按需改回 `hy3`；是否还原以接收方指示为准。
- 本机 `start-infra.sh`/`start-langfuse.sh` 已针对 x86_64 改过（PGBIN/NODE_BIN 自动探测、ClickHouse `macos` 二进制）。若另一台机器是 Apple Silicon，需把 ClickHouse URL 换回 `macos-aarch64` 并确认 `brew --prefix`。

## 7. 另一台机器继续清单

1. `git pull origin main`（获取本 push 的全部改动）。
2. 按 `deploy/langfuse/README.md` 部署 Langfuse v4.27.0 栈：
   - 先执行 `clickhouse-grants.sql`（`--multiquery`，见 README）；
   - `deploy/langfuse/start-infra.sh`；
   - `cp deploy/langfuse/env.example vendor/langfuse/.env` 后填凭据；
   - `deploy/langfuse/start-langfuse.sh --migrate`。
3. 启动服务并确认 6 端口通（8123 / 5432 / 6379 / 9002 / 3000 / 3030）。
4. 完成 **Task 02** 验收前置：启用 Langfuse + 造可复现样本 + 跑通一次真实 E2E。
5. 续做 **Task 04**（把 `post_score_idempotent` 接入 `runner` + 跑红绿测试）、**06**、**07**、**08**。
6. 按 spec-045「验收」四类证据集（红绿测试 / 评测产物 / 可查 trace / 瀑布图）归档并签字。

## 8. 接手机器执行结果（2026-11-08，Apple M3 Max / arm64）

> 接收方已 `git pull origin main` 获取 `1b26c76c`。本机与发送方环境不同：
> arm64、brew `/opt/homebrew`、磁盘可用 297Gi；发送方的两大阻塞
> （`events_only` 404、Next `.next` 撑爆磁盘）在本机**均不成立**。

### 已消解：Task 02 验收硬前置

| 项 | 真实结果 |
|---|---|
| 基础设施 | `start-infra.sh` → 8123/5432/6379/9002 全 [OK] |
| Langfuse | `start-langfuse.sh` → Node 24.19.0，web 3000 + worker 3030 LISTEN，`/api/public/health` 200 |
| **dual 模式** | `/api/public/traces`、`/api/public/scores` 均 **200**（发送方 404 阻塞解除） |
| 主服务 | `launchctl` 重启 `com.researchagent.recovery8000`，PID 37370，`/` 与 `/api/health` 200 |
| 可复现样本 | `generate_observability_fixtures.py --send` → 20 条 sent，Langfuse 可查 |
| 真实 E2E | 真实 SSE `status=completed` + trace `98b91aa3…` 含 **四段 phase span** |
| 真实评测 | `eval_042` CLI → `report.json`/`report.md`，**五类指纹齐全**，score 真实回写 |
| score 幂等 | 重跑后 `totalItems 979 → 979`，**delta=0**，无新 `eval042-*` score |

证据与命令全文：`runs/task-02/evidence.md`，产物同目录。

### 口径更正（本文档第 3 节已过时，以此为准）

只读核实 + 定向测试 `214 passed` 证明：

- **Task 04 已收口**，非「半完成」：`backend/eval_042/runner.py:563` 已调用
  `post_score_idempotent`，`tests/evaluation/test_task04_idempotency.py` 存在且通过；
  上面真实重跑的 `delta=0` 是运行时证据。
- **Task 06 已完成**，非「待执行（骨架在）」：`spans.py` 已接入 `redaction`、
  `ensure_request_id`、thinking 正文与 payload 上限，观测侧测试通过。
- **Task 07 已完成**（2026-11-08 接手方收口，非「未落地」）：retention + `cursor`/`limit` 分页 +
  `benchmark_summary` A 裁决打通均落地；真实 API 分页、真实 Chromium 四项指标截图、
  后端评审通过，证据见 `runs/task-07/`。本节上方第 3 节表格为设计阶段历史记录。
- **Task 08 已完成**（2026-11-08 接手方收口，非「未执行」）：Q10 四类证据 4/4 齐全
  （索引 `runs/task-08/q10-evidence-index.md`）、最终全量回归 `4112 passed / EXIT=0`、
  三份评审通过且架构师签字、准备度 9/10、当前部署版本真实 E2E 成功。
  期间还修复了真 SDK 冒烟暴露的 kb-ask trace 归属分裂（单条 trace 9 observations）。

因此 spec **已于 2026-11-08 收口转 `已完成`**；本节第 3 节表格保留作设计阶段历史记录。
`spec-status-changelog.md` 末条记录了 `实施中 → 已完成`。

### 接手方模型档位

10 个 `.codebuddy/agents/*.md` 的 `model: hy4` 为用户临时决策（台账有记录），
本文档第 6 节称「是否还原以接收方指示为准」；**用户未指示，故保持不动**，
未写回 `AGENTS.md` 或任何流程文档，不作为正式配置固化。

## 9. 范围红线（不可越界）

- **P2 三项不做**：人工 gold 集、`quality_score` 与 Langfuse score 口径统一、在线实时评测。
- 不改根 `CONTEXT.md`、不改 `docs/sdd/context/CONTEXT.md`、不新建 `CONTEXT-MAP.md`。
- 私有 SDK 封装只收拢访问点 + 显式降级告警，**不重构** SDK 接入方式、不改上报字段与瀑布图语义。
- 详见 spec-045 第 109–120 行「明确不做」。
