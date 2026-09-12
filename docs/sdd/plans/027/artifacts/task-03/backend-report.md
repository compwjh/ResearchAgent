# Spec027 Task03 后端交付报告 — 持久化 Research Task 纵向切片

> 关联：[Spec027](../../../specs/027-research-task-dynamic-orchestration-mvp.md) ｜ [Task03 计划](../../task-03-backend-research-task-slice.md) ｜ [后端评审报告](./backend-review.md)
> 分支：`feature/spec-027-research-task-mvp`
> 状态：**实现完成；首轮评审打回 → P0/P1/P2 批量修复 → 复审通过（附意见）→ 复审新增 P2-A/P2-C 已修复；P2-4/P2-9 登记延期**
> 本报告由主会话（架构师）汇总落盘：**主模型代行（原因：Task03 计划要求本报告为交接物，属纯文档产出、不含代码文件；素材来自 16 次 `backend-dev` 分派日志与 1 次 `backend-reviewer` 评审报告）**

---

## 1. 一句话结论

从创建 Research Task 到固定样本双 Worker 检索、评估、覆盖度判定与初步报告的最小持久化后端闭环已跑通：独立库 + 5 张业务表 + 状态机 + 原子事件流 + 9 个端点骨架，`search_catalog` 严格复用 Spec015 `CatalogSearchGraph` / `CatalogRagAdapter`，**未在 research 命名空间重建第二套采集/索引/缓存/目录/RAG/下载/导入或模型客户端**。

## 2. 交付物

### 2.1 新增代码（限界上下文 `backend/app/research/**`）

| 文件 | 行数 | 职责 |
|---|---|---|
| `domain/contracts.py` | 181 | 冻结常量：任务类型/角色白名单、13 错误码、状态集合与转移表、WorkItem Schema、预算上限、质量档位 |
| `domain/models.py` | 299 | ResearchTask / ResearchPlan / ResearchWorkItem / ResearchEvent / PaperSelection / PreliminaryReport 领域模型 |
| `domain/state_machine.py` | 68 | 纯 Python 转移校验（非法转移抛 `INVALID_STATE_TRANSITION`，未知状态不放行） |
| `domain/plan_validator.py` | 156 | Planner 输出校验：JSON Schema、类型白名单、依赖无环、预算、参数允许列表 |
| `application/planner.py` | 222 | 受控 Planner：goal → facets → 计划草稿，失败重试一次 |
| `application/orchestrator.py` | 618 | 稳定 LangGraph 骨架 `plan → fan-out search → fan-in evaluate → check_coverage → replan\|synthesize` |
| `application/research_service.py` | 476 | 服务层：创建/查询/取消/反馈/报告/启动审计，单一状态转移出口 |
| `application/model_router.py` | 158 | fast/strong 路由，模型清单唯一来源 `platform.ollama.get_available_models` |
| `application/search_catalog_adapter.py` | 188 | **复用接缝唯一出口**：只经 Spec015 `CatalogSearchGraph` / `CatalogRagAdapter` |
| `application/entry.py` | 88 | 组合装配工厂（`build_research_service` / `build_research_store`） |
| `infrastructure/research_store.py` | 1073 | 独立库 + 幂等迁移 + 原子事件领号 + 应用层级联删除 |

### 2.2 新增接口与装配

- `backend/app/api/routes_research.py`（492 行）：9 个端点。
- `backend/app/api/common.py`：`recover_research_tasks()` + `research_service` / `research_store` provider 注册。
- `backend/app/api/routes.py`：挂载 `routes_research.router`。
- `backend/app/main.py`：lifespan 增加 027 自有启动收敛。
- `backend/app/api/routes_conversations.py`：`remove_project` 接入 Research Task 应用层级联。
- `backend/app/platform/ollama.py`：`ResourceProbe` / `_GlobalWorkerScheduler` / `read_loaded_models` / `system_available_memory_bytes`。
- `backend/app/research/domain/state_machine.py` 等（见上表）。

### 2.3 测试

- `tests/test_spec027_backend_research_slice.py`（1706 行，**50 passed**）
- `tests/test_spec027_runtime_contract.py`（792 行，Task02 门禁，**38 passed**，本 Task 加强 2 处断言）

## 3. 端点清单（9 个）

| 动作 | 端点 | 成功 | 失败 |
|---|---|---|---|
| 创建 | `POST /api/research-tasks` | 202 + 任务摘要 | 400 输入；404 会话/项目；503 调度不可用 |
| 列表 | `GET /api/research-tasks` | 稳定 keyset 分页 | 400 cursor；404 project |
| 详情 | `GET /api/research-tasks/{id}` | 任务 + 当前计划 + 状态 | 404 |
| 事件流 | `GET /api/research-tasks/{id}/events` | `text/event-stream`，支持 `Last-Event-ID` | 404；410 已删除 |
| 报告 | `GET /api/research-tasks/{id}/report` | 正式/阶段报告 + 证据 + 限制 | 404；409 未生成 |
| 反馈 | `POST /api/research-tasks/{id}/feedback` | 新 plan_version 或继续运行 | 400；409 |
| 取消 | `POST /api/research-tasks/{id}/cancel` | cancelled | 404；409 已终态 |
| 改归属 | `PATCH /api/research-tasks/{id}/project` | 更新归属 | 404；409 running 禁止移动 |
| 删除 | `DELETE /api/research-tasks/{id}` | 删除私有数据 | 404；409 running |

**无 pause/resume 端点**（Spec027「明确不做」：暂停/恢复 defer 到 Spec028）。

## 4. 关键契约落实

- **复用接缝（P0-2）**：`search_catalog` 唯一出口为 `search_catalog_adapter.py`，函数体内延迟 import `CatalogSearchGraph`(`catalog_search_graph.py:235`) 与 `CatalogRagAdapter`(`:79`)；research 各表只存 `catalog_paper_id`，**不复制论文元数据**。
- **独立库**：`data/research/research.sqlite3`，`schema_meta` 单例版本表，单事务幂等迁移；整体删除即回滚，不动 Spec015/022 数据。
- **级联删除走应用层**：外键全 `ON DELETE RESTRICT`，无 DB CASCADE；`delete_task` / `delete_tasks_by_project` 在同一 `BEGIN IMMEDIATE` 事务内按子表→主表显式删除。
- **`event_seq` 原子领号**：同事务内 `UPDATE research_tasks SET last_event_seq = last_event_seq + 1` → `SELECT` → `INSERT`，8 线程并发测试断言无重复、无洞。
- **崩溃收敛**：027 自有审计把遗留 `running` 的 Task/WorkItem 置 `interrupted`，**明确区别于** Spec015 `reset_running_jobs`(`catalog_search_graph.py:843`) 的 running→queued 重试语义。
- **owner 隔离**：沿用单 `OWNER_ID` 范式，非 owner 一律 `TASK_NOT_FOUND`（不泄露存在性）。
- **ResourceProbe 冻结**：只从 `get_available_models()` 与 `/api/ps` 读，保留 ≥20% 余量；探针失败降单 Worker 并发 `RESOURCE_PROBE_FAILED`；单进程全局公平轮转（`_GlobalWorkerScheduler` 模块级单例），两 Task 同时运行不各自估算内存。

## 5. 验证结果

| 命令 | 退出码 | 结果 |
|---|---|---|
| `.venv/bin/python -m pytest tests/test_spec027_backend_research_slice.py -q` | 0 | **50 passed**, 5 subtests passed |
| `.venv/bin/python -m pytest tests/test_spec027_runtime_contract.py -q` | 0 | **38 passed** |
| 两者合并 | 0 | **88 passed**, 5 subtests passed |
| `.venv/bin/ruff check backend/app/research backend/app/api tests/test_spec027_backend_research_slice.py` | 0 | `All checks passed!` |
| `git diff --check` | 0 | 无输出 |
| `git status --short -- frontend` | 0 | 空（未碰前端） |
| 跑测后 `data/research` mtime | — | 未创建/未改写（无真实路径副作用） |

## 6. 评审闭环记录

### 6.1 首轮评审（`backend-reviewer`，2026-09-12 15:32）— 结论：**打回**

| 编号 | 严重度 | 问题 | 处置 |
|---|---|---|---|
| P0-1 | 阻塞 | Worker 额度 `acquire`/`release` 不配对（`arbitrate` 在 `try` 之外），全局额度永久泄漏，后续任务 `granted=0` | **已修复** |
| P1-1 | 阻塞 | POST/GET `/api/research-tasks` 未实现 spec 明文的 404 会话/项目校验与项目继承 | **已修复** |
| P1-2 | 阻塞 | `data/research/` 未加入 `.gitignore`，真实库文件暴露在工作树 | **已修复** |
| P1-3 | 阻塞 | 本报告缺失 | **已修复**（本文件） |
| P2-3 | 警告 | 默认检索路径恒 `SOURCE_DEGRADED`，docstring 与事实不符 | **已修复**（仅注释，行为为正确降级语义） |
| P2-5 | 警告 | 论文不可信测试实为 goal 注入，缺 spec 要求的「论文文本注入」断言 | **已修复** |
| P2-6 | 警告 | 1 条恒真断言；`Last-Event-ID` / `feedback approve` 无覆盖 | **已修复** |
| P2-7 | 警告 | `terminal` 事件泄露内部异常文本（`str(exc)`） | **已修复** |
| P2-8 | 警告 | SSE 合成 `terminal` 帧复用同一 `id`，污染客户端游标 | **已修复** |
| P2-1 | 警告 | Task02 冻结门禁 `test_reuse_seam_no_research_namespace_impl` 被改写 | **追认有效**（见 6.3；复审确认主张成立，另提黑名单强度保留意见 → 见 6.4） |
| P2-2 | 警告 | 新增未登记错误码 | **登记延期**（见 7，清单已按复审意见修正） |
| P2-4 | 警告 | `update_plan_status` 死代码 → 计划状态永不转移（复审实测：恒为 `proposed`，非 `active`） | **登记延期**（见 7） |
| P2-9 | 警告 | 本机 `/api/ps` 无驻留模型 → 探针常态失败 → 真实路径恒单 Worker | **登记延期**（见 7） |

### 6.2 修复细节

- **P0-1**：`orchestrator.py` 阶段 4 把 `arbitrate` 移入 `try` 内，与 `finally: release` 同保护；`release` 无条件执行（`pop` 幂等）。新增 `WorkerQuotaReleaseTests`：让 `arbitrate` 之后的写库 `_emit` 抛异常，断言 `scheduler.in_use() == 0` 且下一任务仍能领到 2 个额度。**RED 证据**：`AssertionError: 1 != 0`。
- **P1-1**：`routes_research.py` 新增 `_resolve_project_id()`，在 API 组合层复用既有 `get_provider("memory_repository")` 查会话/项目归属（**未新建第二套存储，未让 service 层 import memory.repository**）；`payload.project_id` 为空时从会话继承项目。新增 `ResearchTaskContextValidationTests`（9 条）。**RED 证据**：`202 != 404` ×3、`None != 'p-1'`、列表 `200 != 404`。
- **P1-2**：`.gitignore` 增加 `data/research/`（与 `data/memory/`、`data/paper_search/` 同范式）；`git check-ignore` 已命中。
- **P2-7**：`terminal` 事件改为稳定码 `error_code="INTERNAL_ERROR"`，原始异常 + 堆栈只进 `logger.exception`；删除死常量 `_ERROR_EXCERPT_CHARS`。**RED 证据**：修复前落库 payload 实测含 `"/Users/secret/path.db sqlite3.OperationalError token=abc"`。
- **P2-8**：`_sse_frame` 的 `event_seq` 改为可空，合成帧**省略 `id:` 行**（客户端保留上一条真实事件游标），真实事件帧行为不变。**RED 证据**：`(14, 'terminal') != (None, 'terminal')`。
- **P2-5**：新增 `test_malicious_paper_text_never_reaches_research_structures`，以论文**侧**文本（恶意 title/abstract）为注入载体，断言 research 全库文本列不含恶意子串、任务类型/角色仍在白名单内、WorkItem 数量不变、`validate_plan` 仍通过。
- **P2-6**：恒真断言改为逐字期望 message；补 `Last-Event-ID` 断线续传与 `feedback approve` / 终态 approve 409 覆盖。
- **P2-3**：仅修 `search_catalog_adapter.py` docstring/注释，如实说明 Task03 未注入数据源时恒 `SOURCE_DEGRADED`（行为为正确降级语义，零逻辑改动）。

### 6.3 P2-1 追认：Task02 门禁测试改写

Task02 原断言 `test_reuse_seam_no_research_namespace_impl` 要求 `backend/app/research/` **不得存在任何 `.py`**，与已确认 Spec027（明文新增 `backend/app/research/**` 限界上下文）及 Task03 计划**互斥**。Task03 已把它精化为**源码内容扫描**：逐文件禁止出现 Spec015 采集/索引/缓存/目录/RAG/下载/导入符号与第二套模型客户端（`_FORBIDDEN_SECOND_IMPL_TOKENS`），并新增 `test_reuse_seam_research_search_catalog_anchors_to_spec015` 断言 research 命名空间必须有文件引用 `CatalogSearchGraph` / `CatalogRagAdapter`。

**判定**：该改写**口径更强**（从「零文件」变为「有实现但不得含第二套能力」），且是 Spec027 落地的必要条件，**追认有效**（复审亦确认主张成立）；已在 Spec027 变更日志（`spec:271` 新增行）与本报告留痕。

### 6.4 复审（`backend-reviewer` R2，2026-09-12 15:49）— 结论：**通过（附意见）**

报告：`docs/sdd/plans/027/artifacts/task-03/backend-review-r2.md`

上轮 P0×1 / P1×3 **全部关闭**，且每项均由复审**独立实测**（非复述开发侧说明）：P0-1 实测 `in_use after abort: 0`、对照组泄漏态 `in_use=1 → next acquire=0`；P2-7 实测落库 payload 无敏感子串、`_ERROR_EXCERPT_CHARS` 全仓 0 命中；P2-8 实测 15 帧中真实帧全带 `id: N`、合成帧 `event_seq: null` 且无 `id:`，并确认「`Last-Event-ID: 0` 重连已删除任务 → 410」断言**真实可达**（非假通过）。

复审新增 3 项非阻塞发现，**已全部关闭**：

| 编号 | 严重度 | 问题 | 处置 |
|---|---|---|---|
| P2-A | 警告 | P1-1 新增的会话/项目校验位于 `try` 之外，memory 依赖故障冒泡成**裸 500**（无稳定错误体），与本模块「错误出口」契约不符 | **已修复**：校验纳入 `try/except`，复用冻结码 `SOURCE_UNAVAILABLE` 返回 503 稳定错误体；404 原样透传。**RED 证据**：`AssertionError: 500 != 503 : Internal Server Error` |
| P2-B | 警告 | 本交付报告 4 处与事实不符（用例数、计划状态、错误码归属、门禁留痕） | **已修复**（本文件已按复审意见逐条更正） |
| P2-C | 低 | 两处断言可静默失效：① 事件连续性断言按 `event_type != "terminal"` 过滤，而 `"terminal"` 是**真实事件类型**，会连真实终态事件一起排除；② 门禁锚定断言 `if not candidates: return` 在目录被清空时静默通过 | **已修复**：① 改为按「是否合成帧」区分（`event_seq is None` / 无 `id:`），并断言真实帧序列与 `range(1, n+1)` 逐字相等；② 加 `assert scanned > 0` + `assert candidates`，并以「真实移开目录」验证门禁会失败（已复原，15 个 `.py` 完好、无临时备份残留） |

**复审对 P2-1 的保留意见（已接受，登记为 Task05/06 约束）**：黑名单弱于白名单，`urllib` / `aiohttp` / `httpx.post` 等仍可绕过 `_FORBIDDEN_SECOND_IMPL_TOKENS`。建议在 Task06 收口时把门禁扫描升级为**导入白名单**口径。

### 6.5 复审提出的强制约束（已并入交接清单）

1. 门禁扫描升级为导入白名单 + `assert scanned > 0`（Task06）。
2. api 层新增外部依赖一律纳入端点 `try/except`，保持稳定错误体契约（已落到 P2-A 修复与测试）。
3. 补登记 `TASK_DELETED` / `RESEARCH_CASCADE_FAILED` / `INTERNAL_ERROR`（Task04/06）。
4. Task05 修正计划状态交接描述，并驱动 `update_plan_status`。
5. 修正交付报告事实偏差并真正留痕门禁追认（本文件已完成）。

## 7. 延期项与交接

| 项 | 内容 | 交接 |
|---|---|---|
| P2-2 | **Task03 真正新增**的码共 3 个：`TASK_DELETED`(410, `routes_research.py:328/361`)、`RESEARCH_CASCADE_FAILED`(503, `routes_conversations.py:224`)、`INTERNAL_ERROR`(terminal 事件 payload, `research_service.py`)；均未登记进前端文案映射。**注意**：`CONVERSATION_NOT_FOUND` / `PROJECT_NOT_FOUND`(`routes_conversations.py:195/424`) 与 `INVALID_CURSOR`(`routes_conversations.py:184`) 是**既有码复用**，非新增 | Task04（前端文案映射）/ Task06（收口登记） |
| P2-4 | `update_plan_status` 未被调用 → 计划状态**恒为 `proposed`**（复审实测，非 `active`）；`superseded` / `completed` 永不写入。`get_current_plan` 按最大版本取值，故当前无可观测缺陷 | Task05（Re-plan 与计划版本属其范围） |
| P2-9 | 本机 `/api/ps` 无驻留模型 → 探针常态失败 → 真实路径恒单 Worker；属**诚实降级**，非缺陷 | Task05/Task06（环境复验） |
| 环境延期 | 真实 1–4 个 9B 并发吞吐未实测（Task02 已记复验步骤） | Task05 关闭 |
| P2-3 事实 | `entry.build_research_service` 未注入真实数据源 → 真实应用路径**每个任务必然 0 入选、`partial` 收尾**；真实数据源须由后续批次经 `entry.py` 注入 | Task05 |
| Task04 契约 | 合成 `terminal` 帧现在 `event_seq: null` 且无 `id:`，前端必须以 `event: terminal` 判定收尾，**不得**用 id/event_seq 去重或续传 | Task04 |
| Task04 契约 | 新增错误码 `TASK_DELETED` / `RESEARCH_CASCADE_FAILED` / `INTERNAL_ERROR` 需补前端文案映射（未映射时走「未知码 → 通用失败文案」兜底） | Task04 |
| Task06 约束 | 门禁扫描建议升级为**导入白名单**（现行黑名单可被 `urllib`/`aiohttp`/`httpx.post` 绕过） | Task06 |
| 未验证 | 真实 USENIX/DBLP/Ollama 端到端未跑；`search_catalog_adapter.py` 真实数据源分支零测试覆盖（仅静态核对既有接口签名）；多进程 `event_seq` 未验证 | Task05/Task06 |

## 8. 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-12 13:23–15:12 | backend-dev ×14 批次 | 实现 domain/schema + repository + planner + 编排骨架 + 端点 + 定向测试 |
| 2026-09-12 15:27 | backend-dev | 补 spec 明文的项目删除应用层级联（`delete_tasks_by_project` + `remove_project` 接线 + 5 条测试） |
| 2026-09-12 15:32 | backend-reviewer | 首轮评审：**打回**（P0×1 / P1×3 / P2×9） |
| 2026-09-12 15:37 | backend-dev | 修复 P0-1、P1-1（+9 条测试，41 passed） |
| 2026-09-12 15:44 | backend-dev | 修复 P2-3 / P2-5 / P2-6 / P2-7 / P2-8（+6 条测试，47 passed） |
| 2026-09-12 15:50 | 架构师（主会话） | 修复 P1-2（`.gitignore` 加 `data/research/`）；落盘本报告（P1-3） |
| 2026-09-12 15:49 | backend-reviewer | 复审（R2）：**通过（附意见）**；P0×1 / P1×3 全部关闭，新增 P2-A / P2-B / P2-C |
| 2026-09-12 16:01 | backend-dev | 修复复审新增 P2-A（校验纳入 `try/except`，503 稳定错误体）与 P2-C（两处断言加强）；+3 条测试（88 passed） |
| 2026-09-12 16:35 | 架构师（主会话） | 按复审 P2-B 逐条更正本报告事实偏差；追加 Spec027 变更日志门禁追认条目 |
