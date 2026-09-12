# Task 03：实现持久化 Research Task 后端纵向切片

> 关联：[Spec 027](../../specs/027-research-task-dynamic-orchestration-mvp.md) ｜ 索引：[README](./README.md)
> 依赖：Task02 GO；被依赖：Task04–06；当前状态：`已完成`（评审：打回 → 修订 → 复审通过）

## 一句话目标

实现从创建 Research Task 到固定样本双 Worker 搜索、评估和简短报告的最小持久化后端闭环。

## 前置门禁与范围

- 只认 Task02 runtime gate 报告和冻结 Schema。
- 复用 `paper_discovery`、项目/会话 repository、Ollama adapter；不下载 PDF。
- 新增 `backend/app/research/**` 限界上下文和单一 `routes_research.py` 接口，SQLite 迁移必须幂等。
- 本地模型分派时每次最多修改两个代码文件；由多个顺序分派完成本 Task。

## 子任务

1. domain/schema + SQLite repository。
2. Planner 校验 + 稳定 LangGraph 骨架。
3. API 创建/查询/事件/报告接口与后台运行入口。
4. 定向测试覆盖原子创建、事件顺序、项目隔离和单源降级。

## 完整分派 Prompt

```text
角色：backend-dev，模型按 Spec027 执行配置；本地模型单次最多改两个代码文件。
读取：Spec027、本 Task、Task02 报告、backend/app/paper_discovery/application/catalog_search_graph.py、会话/项目 repository 接口、backend/app/api 装配入口。
允许修改：backend/app/research/**、backend/app/api/routes_research.py、必要的 api 装配/迁移文件、tests/test_spec027_backend*.py；每次分派按两文件拆分。
禁止：复制论文目录/RAG/下载/导入；改前端；访问真实外网；修改用户数据；push/merge/reset/stash/clean。
完成状态：固定样本能创建任务，持久化 plan/work items/events，双搜索 fan-out 后生成可读初步报告。
验证：Task03 定向 pytest、迁移幂等/回滚、并发 event_seq、项目归属、git diff --check。
结果写入：docs/sdd/plans/027/artifacts/task-03/backend-report.md。
固定返回：状态摘要、文件、测试/退出码、产物、依据、风险、后续动作、时间与可用统计。
```

## 主 Agent 校验与验收

- 读回所有新增代码，确认依赖方向和 Spec015 复用成立。
- 重跑 Task03 定向测试，不运行全量回归。
- 创建后立即 202；事件先持久化再可读取；未绑定任务不读取项目记忆。
- 服务崩溃遗留 running 状态能在启动审计后变为 interrupted。

## 风险、回滚与产出

- 若必须改写 Spec015 数据模型，停止并回到 Spec。
- 新表和路由可独立移除，不触碰既有数据。
- 产出：后端代码、定向测试、`artifacts/task-03/backend-report.md`；执行结果见上文「结果」段（已完成，复审通过）。

## 结果

- **状态**：已完成（定向测试全绿；未跑全量回归，按 spec「Task 开发只跑定向测试」）。
- **交付报告**：`artifacts/task-03/backend-report.md`
- **评审**：`artifacts/task-03/backend-review.md`（首轮**打回**：P0×1 / P1×3 / P2×9）→ `artifacts/task-03/backend-review-r2.md`（**复审通过，附意见**；上轮 P0/P1 全部关闭，新增 P2-A/P2-B/P2-C 亦已关闭）
- **验证**：`tests/test_spec027_backend_research_slice.py` 50 passed；`tests/test_spec027_runtime_contract.py` 38 passed（合计 88 passed）；`ruff check` 干净；`git diff --check` 无输出；未碰 `frontend/**`；测试无真实路径副作用。
- **分派记录**：`.codebuddy/agent-logs/spec-027/task-03/backend-dev/`（16 批次）、`.../backend-reviewer/`（2 次评审）。
- **延期项**（交 Task05/Task06）：P2-2 新增错误码登记（`TASK_DELETED`/`RESEARCH_CASCADE_FAILED`/`INTERNAL_ERROR`）；P2-4 `update_plan_status` 死代码（计划状态恒 `proposed`）；P2-9 + 环境延期（真实 1–4 个 9B 并发吞吐未实测）；`search_catalog_adapter` 真实数据源分支零测试覆盖。

## 变更日志

- 2026-09-12：创建后端纵向切片 Task。
- 2026-09-12：实现完成（domain/schema + repository + planner + 稳定编排骨架 + 9 端点 + 定向测试）；补齐 spec 明文的项目删除应用层级联。
- 2026-09-12：Task 级评审首轮**打回**（P0-1 Worker 额度泄漏、P1-1 会话/项目 404 校验缺失、P1-2 `.gitignore`、P1-3 交付报告缺失、P2×9）。
- 2026-09-12：P0/P1 批量修复 + P2 清理；复审**通过（附意见）**；复审新增 P2-A（依赖故障裸 500）与 P2-C（断言可静默失效）已修复。Task 收口。
