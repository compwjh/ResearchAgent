# SPEC-045 技术评审（Tech Review）

> 评审角色：架构师（architect，需求/技术评审总控，AGENTS.md:88/117）
> 评审对象：`docs/sdd/specs/045-evaluation-observability-hardening.md`（状态：待确认）+ `docs/sdd/plans/045/`（README + task-02..08）
> 评审依据：AGENTS.md:117（数据模型 / 接口 / 模块拆分 / 模型与上下文预算合理）
> 关联输入：ADR 0002、`deploy/langfuse/start-langfuse.sh`、两份 045-*.md 调研 notes、spec-status-changelog.md
> 评审日期：2026-11-08

---

## 结论

**通过（附 1 项 P0 前置条件，不属本 spec 11 项加固范围，但须在转「实施中」/Task 02 启动前消解）。**

技术设计层面（数据模型增量、接口契约、模块拆分、文件边界、子代理分派、Q7 封装边界、三处「不」约束）均合理、可执行、与 ADR 0002 一致；三处代行留痕齐备。唯一需在执行前闭合的是 **风险裁决 1**（`start-langfuse.sh:15` 硬编码路径错误，导致验收硬前置无法启动），属环境修复，须在 Task 02 前消解。

---

## 逐项结论

### 1. 数据模型增量 — 通过
- spec:149-163 明确标注「文档阶段不建表/不改 schema」，并列出实施期预期增量边界与约束：报告 metadata 加指纹（不存 trace/prompt/completion/凭据）、judge 加固定 seed、score 加幂等键、报告目录文件锁、采样 ContextVar、retention（不迁移历史数据）、processing-steps 游标分页（不改默认行为）、兼容层（不新增公开依赖）。
- 约束与 spec-042:236（不保存凭据/原文）及 AGENTS.md:68（涉及数据模型变更须回 spec 修订）一致，边界清晰。

### 2. 接口契约 — 通过
- spec:165-174 明确「不新增业务 HTTP 端点」（沿用 spec-042 边界），仅列受影响既有接口：① `GET /api/messages/{id}/processing-steps` 加可选 `cursor/limit`、默认行为不变；② `benchmark_summary` 有真实值或前端卡片移除；③ Langfuse scores 加幂等键头/字段、重复写入被识别而非静默产生第二条。契约明确、失败情况可判定（400 / 不被静默）。

### 3. 模块拆分 — 通过
- 11 项 → 7 份 task，映射清晰（01→spec本体；02 验收硬前置；03 评测可信度；04 score 幂等；05 采样/flush/兼容层；06 链路标识/脱敏；07 retention/面板；08 集成验收）。
- DAG 自洽：02 → (03∥04∥05∥06∥07) → 08；03-07 相互独立、仅依赖 02、可并行；08 汇总。无环、无职责重叠。

### 4. 文件边界 — 通过
- 各 task 明确文件边界：03/04 限 `backend/eval_042/**`；05 限 `backend/app/platform/observability/**` + 新增兼容层 + `routes_{chat,kb,article}.py`；06 跨 `observability/**` + `routes_*` + `repository.py` + `research_store.py`；07 跨 `repository.py`/`routes_conversations.py`/`research_store.py`/`config.py` + 前端 `index.html`/`research-tasks.js`/`styles.css`。
- 前后端分派符合 AGENTS.md:71-75（单端改单端 agent；跨端拆两次分派）。task-06/07 已规划分别 `Task(backend-dev)`/`Task(frontend-dev)`，且不碰 `backend/app/**` 之外的越界文件。

### 5. 子代理分派安排（AGENTS.md:127/128 代行与分派前置）— 通过
- Task 02 为运行态/文档动作、不含代码 → 主会话代行（AGENTS.md:127）；若需改任何 `.py` 脚本须先 `Task(backend-dev)`（task-02:52-57），正确。
- Task 03-08 含 `.py`/`.js`/`.html`/`.css` → 必须先 `Task(backend-dev)`/`Task(frontend-dev)` 再落地（AGENTS.md:128 分派前置），各 task 文档均已声明，符合「失败先诊断、禁止以代行绕过代码分派」。

### 6. Q7 私有 SDK 封装边界 — 通过
- spec:62、spec:114-115、ADR 0002 后果段、task-05:38-41/68-73 一致：收拢私有符号（`_otel_tracer`/`_otel_span._start_time`/`_client.attributes`）到单一兼容层 + 缺失时显式降级告警；**不重构 SDK 接入方式**、**不改变上报字段与瀑布图语义**；并更正「从根上不会坏」为「不保证不退化，只保证退化可发现（显式降级+告警）与修复点唯一」。边界清晰、可执行（task-05 第 5 步补真 SDK 升版冒烟锁 `langfuse==4.15.1` 形状）。

### 7. 「不改上报字段 / 不改 SSE 协议 / 不迁移历史数据」是否可执行 — 可执行
- 不改上报字段：task-05:37「不改变上报字段、metadata 与 7 个 numeric score 名称」；task-06「不改 research_events 白名单契约（safe_payload 形状被契约测试锁定）」——有契约测试兜底，可执行。
- 不改 SSE 协议：task-07「不新增业务端点、不改 SSE 事件协议」；spec 明确不做「不改 SSE 事件协议」——可执行。
- 不迁移历史数据：task-07「不迁移/删除历史数据」；spec「不迁移历史数据」；F15 实测数据量小，清理策略只作用于未来增长——可执行。

---

## 三处代行留痕齐备性（风险裁决 3）— 齐备

按 AGENTS.md:127，纯 `.md` 代行须三处留痕。只读核实：

| 留痕位 | 位置 | 核实结果 |
|---|---|---|
| 留痕一：notes 头部「代行留痕」段 | `045-evaluation-module-survey.md:5-6`、`045-observability-module-survey.md:5-6` | ✓ 两份均写明三处留痕位置 |
| 留痕二：spec「代行记录」 | spec:208-216 | ✓ 留痕一/二/三与 notes、changelog 对应 |
| 留痕三：changelog 045 条目 | `spec-status-changelog.md:3` | ✓ 明确「三处留痕：两份 notes 头部、spec-045 代行记录、本条目」 |

三处表述一致，满足代行留痕要求。**齐备**。

---

## 必须裁决的三个风险

### 风险裁决 1：Task 02 真实阻塞（端口未监听 + 硬编码路径错误）— P0 实现前必修，不属本 spec 11 项范围

**核实事实**（只读）：
- `deploy/langfuse/start-langfuse.sh:15` 硬编码 `LANG_FUSE_DIR="/Users/wjh/ResearchAgent/vendor/langfuse"`，该路径**不存在**；实际源码在 `/Users/wjh/work/ResearchAgent-2/ResearchAgent/vendor/langfuse`（存在）。
- 6 个端口 3000/3030/8123/5432/6379/9002 **全部未监听**（当前状态，Task 02 本就要启动它们，属预期）。

**是否「实现前必修 P0」**：
- 是。脚本环境检查 `if [ ! -d "$LANG_FUSE_DIR" ]; then echo "[FAIL] 未找到 Langfuse 源码目录"；exit 1; fi`（start-langfuse.sh:23-26）会因路径不存在直接 `exit 1`，**Task 02 第 1 步「起自托管 Langfuse 栈」在启动前即失败**。由于 Task 02 是 spec 的**验收硬前置**（Q9/ADR 0002），其失败将导致 03-07 全部阻塞、spec 无法收口。故为 **P0 实现前必修**。
- 6 端口未监听是 Task 02 要改变的目标态，非独立阻塞；但**路径错误是启动的前置死锁**，必须先解。

**修它是否属于本 spec 范围**：
- 不属于 11 项加固范围。`start-langfuse.sh` 是 deploy 包装脚本，既非业务代码（spec 明确不做针对 `.py/.js/.html/.css` 与 `.env`），也非 11 项加固项；其绝对路径过期源于仓库迁移（`/Users/wjh/ResearchAgent` → `/Users/wjh/work/ResearchAgent-2/ResearchAgent`）。属**环境/infra 前置修复**。
- 但它是 Task 02 可执行的硬前提，不能回避。

**裁决与处置**：
1. **通过技术评审**，但附 **P0 前置**：在转「实施中」、Task 02 启动前，**必须**消解该路径错误。
2. 范围处理（二选一，推荐方案 A）：
   - **方案 A（推荐）**：作为 Task 02 的前置子步骤纳入，限定**仅修正该行绝对路径**（改为相对路径或参数化 `LANG_FUSE_DIR`），不构成 spec 加固内容、不扩大 11 项；并补充 `deploy/langfuse/start-langfuse.sh` 到 task-02 文件边界，标注「仅修路径，不重构脚本」。
   - **方案 B**：作为独立 infra 修复，在 spec-045 实施前于受控环境完成（不进 spec 任务流）。
3. **分派纪律**：因改动 `.sh`，不属 AGENTS.md:127 代行免分派清单（仅免 `.py/.js/.html/.css`），须遵守分派前置（AGENTS.md:128）——由 `backend-dev` 或运维动作在受控环境修改，不在纯文档代行范围。
4. 该 P0 不影响本技术评审「通过」结论（spec/计划设计本身无缺陷），但**未消解前不得转「实施中」、不得启动 Task 02**。

### 风险裁决 2：Q9「验收前置由验收执行者完成」与 Task 03–07 依赖 Task 02 的排序 — 可执行

- Q9 裁决（spec:64）与 ADR 0002 决策 1 一致：Task 02 列为硬前置，「由验收执行者完成，不由开发任务代劳」。
- DAG 排序：`02（验收执行者）→（03∥04∥05∥06∥07 开发任务，相互独立、可并行）→ 08（汇总验收）`。
- 各 task 前置声明自洽：03-07 均声明「task 02 已完成（真实 trace/CLI 可跑/真实 Langfuse 可用）」；08 声明「03-07 均已完成」。
- 输入契约闭合：Task 02 第 6 步产物（运行态 Langfuse + 可复现样本 + `trace_id` + CLI `report` 路径，落 `runs/task-02/`）正是 03-07 的输入（03/04 需真实 trace 与 CLI；05 需真实 Langfuse 观察瀑布图；06/07 需 Task 02 完成）。
- **结论：排序可执行**，无独立 P0/P1。唯一耦合风险即风险裁决 1（Task 02 失败则 03-07 全阻塞），已单列。

### 风险裁决 3：三处代行留痕 — 齐备（见上表）

---

## P0 / P1 问题清单

| 编号 | 级别 | 问题 | 是否阻塞本门禁 | 处置 |
|---|---|---|---|---|
| P0-1 | P0 | `deploy/langfuse/start-langfuse.sh:15` 硬编码绝对路径指向不存在的旧仓库位置，Task 02 环境检查会 `exit 1`，验收硬前置无法启动 | 否（不属 spec 设计缺陷，属环境前置） | 转「实施中」/Task 02 启动前必修；方案 A：纳入 Task 02 前置子步骤仅修路径并补文件边界；或方案 B：独立 infra 修复。改动 `.sh` 须依 AGENTS.md:128 分派前置 |
| （需求评审 P1-1 同步关注） | P1 | 06/10 未列入 Q10 四类证据编号表 | 否 | 见 045-requirement-review.md，建议显式声明验收归属 |

> 技术设计层面无阻断性问题，可进入「待用户确认」流程。

---

## 转「已确认」前置提醒（非本评审阻塞项）
1. **P0-1 环境前置**须在转「实施中」、Task 02 启动前消解（见风险裁决 1）。
2. 需求评审附带的**产品使用步骤**须在用户确认后由产品经理补齐（Q8）。
