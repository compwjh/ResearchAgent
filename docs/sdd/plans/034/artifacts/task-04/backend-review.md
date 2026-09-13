# Spec034 Task04 后端复审报告

## 固定字段

- spec：034 — 会话式深度研究与真实子 Agent Runtime
- task：Task04 — 计划版本、统一审批命令与前端卡片
- reviewer：backend-reviewer（当前执行 Agent）
- review_base：当前工作树相对 `1879fb3` 的实际后端差异，含新增 `.agents/skills/research-plan-authoring/SKILL.md`
- review_scope：ResearchPlanOutput/语义校验、v2→v3 迁移与回滚、Session owner/plan_version、六类命令 CAS/幂等/竞争、取消收敛、Registry 能力/资源快照、approve Saga/outbox、稳定 activation ID、WorkItem DAG/嵌入 URL/CoT 与 scope allowlist；只读评审
- conclusion：GO
- blocking_levels：P0=0，P1=0，P2=0

## 结论

GO。上一轮 activation/outbox、scope 安全、审批入口和跨端 projection 字段问题均已修复：任务详情通过 owner-scoped Session link 返回计划/审批白名单；前端优先消费 `scope`/`safe_summary` 并兼容旧别名，capability/resource 审批范围可正确提交统一命令。旧 `/feedback` 旁路已移除，unknown kind 与 stale/conflict refresh 已 fail-closed。定向后端/前端测试、编译、Ruff、静态 seam 和 diff-check 全部通过，可进入下一门禁。

## 已通过项

- **v2→v3 迁移与回滚边界**：`backend/app/research/infrastructure/research_store.py:291-296,403-589` 将研究库 schema 提升为 v3，在调用方事务内 additive 创建 Task04 表及 activation anchor；旧 command 表缺列只做 `ALTER TABLE`，异常路径 rollback。`tests/test_spec034_task04_contract.py:114-128` 验证 v2 缺表重开补建及重复初始化。
- **owner/session/task 绑定与取消 CAS**：计划查询通过 Session owner join（`research_store.py:1199-1266`）；`cancel_session_research` 在 `BEGIN IMMEDIATE` 内校验 owner、取消非终态 Task 及 queued/running WorkItem（`1329-1393`）。合同测试确认批准后取消全量收敛、重复命令返回原结果。
- **ResearchPlanOutput 与 WorkItem DAG**：`backend/app/research/application/plan_authoring.py:20-69,85-190` 使用 forbid-extra Schema、有界 section、output hash、稳定唯一 ID、依赖引用/循环/最多三级 DAG、Spec027 task_type/role/参数/预算白名单，并递归拒绝 URL、Prompt/CoT、Shell/Python/exec。重复 ID、四层 DAG、嵌入 URL 测试通过。
- **Registry 能力与资源快照**：`approval_service.py:409-472` 对能力做 Registry 存在/启用/Skill 声明范围/entry 安全校验，持久化 Skill 内容哈希、Tool 参数哈希/entry/副作用与资源上限；`474-484` 限制 approve_plan 仅能批准当前版本/哈希。未知能力、快照和禁用边界测试通过。
- **命令 CAS/幂等/stale/conflict**：`approval_service.py:134-172` 先校验当前 `subject_version`，再按 owner/session/command/version 比对结果；`research_store.py:1665-1688,1720-1784` 采用事务/写锁及不可变命令结果。六命令由 `routes_research.py:118-157` 的 Literal/基础请求 Schema 接入，意外异常统一稳定错误出口（`294-350`）。
- **稳定 activation 与 Task/WorkItem 恢复**：`approval_service.py:176-238,279-329` 先写 activation anchor，Task ID 来自其稳定身份；已有 Task、ResearchPlan、WorkItem 按稳定 ID/缺失项恢复，activation 状态可重试。`research_store.py:1712-1784` 对 owner/session/version/key 做唯一约束。故障探针确认 outbox 首次失败后重试 Task 数量 1、WorkItem 数量 3、Task ID 不变。
- **Memory activity 幂等与跨库边界**：`backend/app/memory/repository.py:760-768,1836-1880` additive 增加 activity key 唯一索引及 deterministic message ID；`approval_service.py:240-277` 用 `(session, version, command key)` 创建/查询并在 outbox/link 失败时返回可重试 `SOURCE_UNAVAILABLE`。模拟 Memory 成功后 outbox 更新失败，重试消息数保持 1。
- **scope URL/CoT/allowlist**：`plan_authoring.py:42-112` 的递归安全策略被 command service 复用；`approval_service.py:486-501` 按六类 command 使用 allowlist，拒绝嵌入 URL、domain-like 值、变体 CoT/Prompt 和越权字段。新增 `test_command_scope_uses_recursive_shared_safety_policy` 通过。
- **Skill 边界与既有实现复用**：`.agents/skills/research-plan-authoring/SKILL.md:1-38` 只做 Intake 到可验证计划编排，不执行搜索、下载、导入、模型运行或审批副作用；Task04 复用 Spec027 的计划校验、ResearchStore、MemoryRepository、Skill/Tool Registry，没有复制目录/Tool 执行实现。

## 追加复审发现（已关闭）

### 已关闭：Task detail approval projection 与统一 command scope DTO 不兼容

- `backend/app/api/routes_research.py:296-321` 的 `_approval_payload()` 已按 kind allowlist 裁剪，但将请求范围命名为 `scope`；`frontend/research-tasks.js:399-405` 的 `sessionCommandScope()` 仅读取 `requested_scope_json`。
- 实际临时数据库 probe 得到 capability approval：`{"scope":{"skill":"s","tools":["t"]}}`。因此 Tab 在第一次渲染或 Session detail 请求失败的回退路径中会发送空 Skill/Tool（或空资源增量），无法完成批准。
- 最小修复：冻结 task-detail 与 session-detail 相同的 DTO；推荐统一为 `requested_scope_json` 的解析对象，或让前端显式读取白名单后的 `scope`，并补 capability/resource approval payload 测试。

### 已关闭：Task detail plan projection 的安全摘要字段名与契约不一致

- `backend/app/api/routes_research.py:275-293` 输出 `safe_summary`；前端计划字段固定为 `safety_summary`，且 `research-tasks.js:370-396` 不读取 `safe_summary`。
- Session detail 成功后原始 `safety_summary_json` 可能恢复，但任务详情首次响应/降级响应会丢失“降级策略”展示。
- 最小修复：后端输出 `safety_summary`（或前端兼容 `safe_summary`），并在 task detail 合同中断言字段名和值一致。

## P0/P1/P2 汇总

- P0：无。
- P1：无。本轮确认 task-detail approval scope 已被前端兼容消费。
- P2：无。本轮确认 safe summary 已被前端兼容展示。
- 当前结论：GO；Task04 backend 可进入下一门禁。后续真实 AgentRunner/执行编排不在本 Task 范围。

## 验证命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task04_contract.py` | 0 | 14 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task04_contract.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py` | 0 | 38 passed |
| `.venv/bin/python -m py_compile backend/app/research/application/plan_authoring.py backend/app/research/application/approval_service.py backend/app/research/domain/models.py backend/app/research/domain/contracts.py backend/app/research/domain/state_machine.py backend/app/research/infrastructure/research_store.py backend/app/memory/repository.py backend/app/api/routes_research.py backend/app/api/routes.py tests/test_spec034_task04_contract.py` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/research/application/plan_authoring.py backend/app/research/application/approval_service.py backend/app/research/domain/models.py backend/app/research/domain/contracts.py backend/app/research/domain/state_machine.py backend/app/research/infrastructure/research_store.py backend/app/api/routes_research.py backend/app/api/routes.py tests/test_spec034_task04_contract.py --output-format concise` | 0 | All checks passed |
| `.venv/bin/ruff check ... backend/app/memory/repository.py ...` | 1 | 14 条既有基线告警；与 `1879fb3` 基线同类同数，未新增 Task04 告警 |
| `git diff --check 1879fb3 --` | 0 | 通过 |

## 复审边界

- 本轮只读复审并更新本报告；未修改业务代码、Spec 或状态，未执行 commit/push/merge/reset/stash/clean。
- 故障探针使用临时目录与 monkeypatch，不写入仓库业务数据；结果已在“已通过项”中记录。
- 未运行全量 pytest，符合 Task 级定向回归边界。
- **此前追加复审证据仍有效**：activation/outbox、Memory activity 幂等和递归 scope 安全故障探针通过；outbox 故障恢复后 `queued`、Task 数量 1、WorkItem 数量 3；消息写入后 outbox 更新故障重试后专用 activity 数量 1；嵌套 CoT、`www` URL、domain-like 值均稳定拒绝。本轮仅因跨端 task-detail DTO 错位改为 REVISE。
- **追加复审验证退出码**：`.venv/bin/python -m pytest -q tests/test_spec034_task04_contract.py`=0（14 passed）；Task04+Task02/03 定向回归=0（38 passed）；目标后端 py_compile=0；聚焦 Task04 Ruff=0；`git diff --check 1879fb3 --`=0。前端对应合同=0（28 passed）、Node 语法=0、静态 seam=0。
- 进展日志：`.codebuddy/agent-logs/spec-034/task-04/backend-reviewer/20260913-000000.md`。
