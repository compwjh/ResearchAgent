# Spec 027 技术评审（含需求评审维度）

> 评审对象：`docs/sdd/specs/027-research-task-dynamic-orchestration-mvp.md`
> 关联任务：`docs/sdd/plans/027/`（README + task-02..06）
> 评审角色：architect ｜ **最终结论：通过（复审，2026-09-12）**
> 注：复审曾判「打回」，唯一阻塞为 `plans/027/task-04-frontend-research-workspace.md:15` 残留「暂停/取消」；架构师已按复审指定的修复路径把该句改为「取消（不实现暂停/恢复）」，P0-1 闭环，结论转为通过。

## 结论

**通过（复审，2026-09-12）**。Spec 文本层面的 2 项 P0 与 8 项 P1 均已落实（P0-2 与全部 P1 已解决；P0-1 在 Spec 内部已移除 `paused`、移动端改「只取消」、暂停/恢复 defer 到 Spec028 并写入「明确不做」）。但**复审包包含 plans/027**，其中 `task-04-frontend-research-workspace.md:15` 仍保留「手机端可查看、**暂停/取消**和阅读报告」，与 Spec 第 192/211 行「移动端只取消 / 暂停恢复不在 Spec027」直接冲突。该句正是上一轮 P0-1 的触发点（移动端「暂停/取消」），只是从 Spec 移到了 UI 实现任务；前端 dev 据此仍会实现暂停按钮，故 P0-1 在评审包内**未解决（残留）**。未引入新增 P0。结论：**打回**，阻塞项唯一——清理 task-04:15 的「暂停/取消」措辞，使其与 Spec「移动端只取消」一致后，P0-1 即可闭环。

> 历史首轮结论见下方「历史评审（2026-09-12 首轮）」；本轮裁定见「复审记录（2026-09-12）」。

## 复审记录（2026-09-12 re-review）

复审范围：Spec027 第 47-53、71、124-140、159、192、200、211 行修订 + plans/027（README + task-02..06）+ 代码事实核对。

### 复审裁定（逐项）

| 项 | 判定 | 依据 / 落点 |
|---|---|---|
| P0-1 暂停矛盾 | **未解决（残留）** | Spec 内部已修：status 无 `paused`（spec:71）、移动端「只取消」（spec:192）、暂停/恢复 defer 到 Spec028 并写入「明确不做」（spec:211）。但 `plans/027/task-04-frontend-research-workspace.md:15` 仍写「手机端可查看、**暂停/取消**和阅读报告」，与 Spec 直接冲突，会让前端 dev 实现暂停按钮；全局 grep 仅此一处。P0-1 矛盾 relocate 未消。 |
| P0-2 复用接缝 | 已解决 | 「复用接缝（强制）」spec:47-53 钉死 `CatalogSearchGraph`(:235)、`CatalogRagAdapter`(:79)、DBLP 默认关闭用 `_dblp_enabled`(:388-398)；禁止 research 命名空间重建采集/索引/缓存/目录/RAG/下载/导入；模型调用仅 `platform/ollama.py`。代码引用一致。 |
| P1-1 显式状态机 | 已解决 | spec:124-128 给出 ResearchTask/ResearchWorkItem 转移表、终态集合、终态不得回 running，服务层单一函数校验 + 稳定错误码。 |
| P1-2 稳定错误码词表 | 已解决 | spec:130-132 列出 13 个稳定 code，前端按 code 映射文案。 |
| P1-3 event_seq 原子领号 | 已解决 | spec:138 每任务计数器，同事务内 `UPDATE…SET last_seq=last_seq+1`，不冲突/不重用/无洞。 |
| P1-4 崩溃启动审计 | 已解决 | spec:139 自有审计 running→interrupted，明确区别于 `reset_running_jobs`(:843) 的 running→queued；代码确认位置一致。 |
| P1-5 DB 放置与级联 | 已解决 | spec:136-137 独立库 `data/research/research.sqlite3` + schema_meta + 幂等迁移；级联走应用层，不用 FK CASCADE（RESTRICT）。 |
| P1-6 ResourceProbe 冻结 | 已解决 | spec:159、220 冻结接口：只走 `platform/ollama.py`、20% 余量、探针失败单 Worker + `RESOURCE_PROBE_FAILED`、单进程全局公平轮转、Task02 门禁冻结 Fake 数据源。注：`platform/ollama.py` 现有 `get_available_models()` 仅读 `/api/tags`（:25-32），`/api/ps` 读取器与 `ResourceProbe` 属待新增实现，须落在 `ollama.py`（不新增第二套客户端），方向合规。 |
| P1-7 论文不可信断言 | 已解决 | spec:200 注入恶意论文文本样本测试，断言计划/权限/工具集/白名单不变；spec:196 配合拒绝非法 Planner 输出。 |
| P1-8 owner 隔离 | 已解决 | spec:140 沿用单 `OWNER_ID`（`memory/repository.py:43`），不引入新鉴权；代码确认。 |
| 新增 P0 | 否 | 未发现与修订引入的新 P0；唯一阻塞为 P0-1 在 plans 内的残留。 |

### 复审结论

**打回**。10 项历史问题中 9 项已解决（P0-2 + P1-1~P1-8），P0-1 在 Spec 文本已修复，但**评审包（含 plans/027）内** `task-04:15` 仍保留移动端「暂停/取消」措辞，与 Spec「移动端只取消」矛盾，构成 P0-1 残留。该残留一旦被前端 dev 执行即复现暂停功能，故维持打回。修复动作（仅改 plans 文案，不动 Spec/业务代码）：将 `task-04-frontend-research-workspace.md:15` 的「暂停/取消」改为「只取消」，与 spec:192/211 对齐；改后 P0-1 闭环，可判通过。

## 历史评审（2026-09-12 首轮 · P0/P1 清单）

## P0 清单（阻塞，必须修）

- **P0-1 暂停功能矛盾（状态机/端点/UI 不一致）**：数据模型 `status` 含 `paused`（spec:63），UI 要求移动端"暂停/取消"（spec:163），但 8 个端点无 pause/resume 端点；"显式 cancel 停止新节点"（spec:154）与 `明确不做`（spec:180）、Spec028 范围均未承接 pause/resume。开发无法一致实现。→ 二选一：补 pause 端点并定义 `paused` 状态机与转移；或将 `paused` 与移动端"暂停"移出 MVP、明确 defer 到 Spec028，并确认 Spec028 范围承接。
- **P0-2 search_catalog 复用接缝未钉死**：spec 仅在高层声明"复用 paper_discovery、不复制目录/RAG"（spec:14、182），但未指定 `search_catalog` WorkItem 具体调用 Spec015 的哪个实现（如 `CatalogSearchGraph` 或 `POST /api/papers/searches` + 冻结结果、`CatalogRagAdapter` 检索）。DBLP 默认关闭（catalog_search_graph.py:388-398）时只走 USENIX 缓存的策略也需显式对齐。不钉死则 dev 易在 research 命名空间重造采集/索引/RAG。须在 spec 或 Task02 门禁冻结接缝与禁止项。

## P1 清单（澄清，不阻塞）

1. **显式状态机**：为 `ResearchTask`（10 态）与 `ResearchWorkItem`（6 态）定义允许转移与终态（completed/failed/cancelled/interrupted），把"终态不得回到 running"（spec:171）落到数据模型/服务层。
2. **稳定错误码词表**：参照 Spec015 `EVENT_ERROR_CODES`/`message_code` 的 frozenset，定义 027 各端点稳定 `code`（如 PLAN_VALIDATION_FAILED、BUDGET_EXCEEDED、SOURCE_DEGRADED），前端按 code 映射文案而非仅靠 HTTP 状态。
3. **event_seq 生成器**：明确 `(research_task_id, event_seq)` 单调来源（每任务计数器/序列表，原子领号），保证并发 Worker 不冲突、不重用、无洞；Task03 验收已要求"并发 event_seq"，须在 store 层定稿。
4. **崩溃收敛启动审计**：明确 027 自有审计把 running→interrupted，区别于 Spec015 `reset_running_jobs` 的 running→queued 重试（catalog_search_graph.py:820-850）；与单 SQLite 迁移边界一致。
5. **DB 放置与级联删除**：澄清"新库路径"（spec:21 回滚段）与 Task03"SQLite 迁移幂等"的关系（并入现有单一 SQLite 加表 vs 独立 DB）；迁移单事务、幂等、可回滚；项目→Research Task 级联走应用层显式删除，不用 DB FK CASCADE（与 regression-guard 一致）。
6. **资源探针与跨任务公平**：Task02 门禁冻结 `ResourceProbe` 接口与真实数据源（Ollama `/api/ps` 已加载模型/内存），写清 20% 余量、探针失败→单 Worker、单进程全局调度公平轮转；确认不新增第二套模型客户端（复用 `platform/ollama.py`）。
7. **"论文内容不可信"可执行约束**：补一条可测断言——evaluator/critic 接收的论文文本不得改变计划/权限/工具集；结构性已由"Planner 白名单 + 固定角色"保证，但需落成注入样本测试，避免口头约束。
8. **owner 隔离**：确认沿用现有单 `OWNER_ID` 模型（MemoryRepository），027 所有端点/store 复用同一隔离范式，不引入新鉴权。

## 逐项核对表

| # | 核对项 | 结论 | 依据 |
|---|---|---|---|
| 1 | 可复用 vs 重造轮子 | 基本 PASS（P0-2 待钉） | catalog_search_graph.py:46-63,235-280；platform/ollama.py:25-55；spec:14,42,182 |
| 2 | 数据模型自洽/缺失 | P1 | spec:49-112（缺 event_seq 生成器、状态机、级联机制）；regression-guard:508-512 |
| 3 | 端点与事件/SSE | 基本 PASS（P1-2/3/4） | spec:138-153；routes_conversations.py:239-446（persist-before-push）|
| 4 | Planner/Critic 停止合同 | PASS（P1-7） | spec:114-121（首轮+2、12/100/20 上限可测）|
| 5 | 动态路由与 Worker | P1（探针冻结） | spec:123-130；task-02:18-22（Fake Adapter）|
| 6 | 上下文/记忆/级联/隔离 | PASS 意图（P1-5/8） | spec:132-136；022:185-206 |
| 7 | Task02-06 依赖无环/覆盖验收 | PASS | plans/027 README:8-14；task-02..06 |

## 依据索引

- Spec027：`docs/sdd/specs/027-research-task-dynamic-orchestration-mvp.md`（:14,42,63,114-136,138-153,171,180-182）
- Spec015 背景/端点：`docs/sdd/specs/015-security-paper-discovery.md`（:108-174,331-418）
- Spec022 上下文优先级：`docs/sdd/specs/022-project-conversation-memory.md`（:185-206）
- 既有实现：`backend/app/paper_discovery/application/catalog_search_graph.py`（:46-63,235-280,388-398,820-850）、`backend/app/platform/ollama.py`（:25-55）、`backend/app/chat/application/context_compaction.py`（:169-324）、`backend/app/api/routes_conversations.py`（:239-446）
- 回归纪律：`backend/.codebuddy/skills/regression-guard/SKILL.md`（:508-512 并发领用/外键 RESTRICT/禁止第二套）
