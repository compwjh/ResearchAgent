# Spec034 Task02 后端复修复审报告

## 固定字段

- spec：034 — 会话式深度研究与真实子 Agent Runtime
- task：Task02 — 数据模型、状态机、迁移与兼容门禁
- reviewer：backend-reviewer（当前执行 Agent）
- review_base：提交 `1879fb3`
- review_scope：当前工作树相对 `1879fb3` 的实际 Task02 diff；只读复审，未修改业务代码、Spec 或状态
- conclusion：GO
- blocking_levels：P0=0，P1=0，P2=1

## 结论

本轮复核确认上一版剩余四项 P1 已修复，结论 **GO**。Session、AgentRun、Notification 的 owner/session/task/work-item 绑定现为 fail-closed；Session 初始 Task 引用在同一事务内校验；Notification 在 event_seq 检查前按完整业务身份幂等；ResearchStore 与 MemoryRepository replay 均拒绝非 canonical `source_event_id`，并保留乱序父链投影与失败重试 seam。

唯一遗留为 P2：目标文件集的 ruff 仍因 `memory/repository.py` 既有行报错；本次新增 hunk 无新增诊断，不阻塞本 Task02 后端复审。

## 本轮重点复核

### 1. AgentRun 未绑定会话限制：通过

- 位置：`backend/app/research/infrastructure/research_store.py:1433-1472`
- 未绑定 `research_task_id` 的 Session 只允许无 Task/WorkItem 的 Planner Run；带 Task/WorkItem 的 Run 直接抛 `AgentRunBindingError`，非 Planner 无绑定也拒绝。
- 已绑定 Session 必须使用同一 Task；执行角色必须同时绑定 Task 与 WorkItem；Task 还须匹配 owner/conversation，WorkItem 须属于该 Task。
- 新增合同测试 `tests/test_spec034_task02_contract.py:152-179` 覆盖未批准 Session 的 worker、绑定 worker 和未知 continued-from parent。

### 2. Session 初始 Task 关联：通过

- 位置：`backend/app/research/infrastructure/research_store.py:1082-1107`
- `create_session` 强制要求既有 `MemoryRepository`，先校验跨库 conversation/trigger message，再在 `BEGIN IMMEDIATE` 事务中校验非空 `research_task_id` 存在且 owner/conversation 与 Session 一致；错误引用抛 `TASK_NOT_FOUND`，不会插入 Session/Draft。
- 新增合同测试 `tests/test_spec034_task02_contract.py:74-95` 覆盖缺失 Task 与跨 conversation Task。
- Draft 的两个 ID 仍要求与 Session 一致（同文件 `:1087-1091`）。

### 3. Notification session-task 关系与完整幂等身份：通过

- 位置：`backend/app/research/infrastructure/research_store.py:230-248,1662-1701`
- 若同时提供 Session 与 Task，事务内要求该 owner 的 Session 已绑定该 Task；两个各自存在但互不相关的目标会拒绝。
- `(owner_id,idempotency_key)` 命中后，在 event_seq 单调性校验前比较 `notification_kind/status/subject_version/research_session_id/research_task_id/payload`；完全相同业务请求返回原记录，任一身份字段或 payload 不同抛 `NOTIFICATION_IDEMPOTENCY_CONFLICT`。生成的 notification ID/event_seq 不参与重放身份比较。
- 新增合同测试 `tests/test_spec034_task02_contract.py:129-149` 覆盖 payload、kind、Task/Session 关系及 event_seq 乱序重放。

### 4. ResearchStore/Memory replay canonical source_event_id：通过

- ResearchStore：`backend/app/research/infrastructure/research_store.py:1892-1939` 按 `(research_task_id,event_seq)` 生成并校验 `research-event:{task}:{seq}`，拒绝 custom/cross-task identity；父节点优先、同深度按 event_seq 排序，projector 成功清理 retry、失败递增 retry 并保留事件。
- MemoryRepository：`backend/app/memory/repository.py:2784-2816,2830-2908` 的 projector 校验 canonical 格式，replay 输入校验顶层及 `safe_payload_json` 中的 source ID、单 Task、父链顺序与 parent-first 投影。
- 新增合同测试 `tests/test_spec034_task02_contract.py:196-246` 覆盖乱序父链、custom ID、safe payload custom ID、跨 Task 和 ResearchStore retry seam。

## 既有 Task02 契约复核

- Schema v2 初始化/幂等、事务失败回滚、六实体字段与 owner-scoped 唯一索引通过；旧 v1 ProcessingStep 行按默认 v1 字段可读，v2 additive migration 不重写旧行。
- ProcessingStep v2 的 `(message_id,node_key)`、非空 `source_event_id` 唯一索引及同 kind sibling 分配通过；父链同 message、无循环、最多三级由 projector 校验。
- 终态状态机拒绝 rewind，Task/WorkItem/AgentRun 的状态更新保留 CAS/幂等语义；命令使用固定 `Literal`，scope 仅做边界限制，能力授权仍留在 service/Registry 层。
- 未发现对 Spec027/022/023 的第二套实现、跨库外键替代或既有接口破坏；相关既有测试均通过。

## P2

### P2-01：目标文件集 ruff 仍有既有诊断

- `.venv/bin/ruff` 可用，目标文件集退出码 1，共 14 个问题，位置为 `backend/app/memory/repository.py:661,676,696,710,1044-1048`。
- 这些行不在本次 Task02 新增 diff hunk；本轮未发现新增代码引入的 ruff 诊断。
- 最小建议：后续 lint 清理单独修复既有问题；不因该既有问题阻塞本 Task02 评审结论。

## 验证命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task02_contract.py tests/test_memory_repositories.py tests/test_memory_analysis_repair.py tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py` | 0 | 146 passed，5 subtests passed |
| `.venv/bin/python -m py_compile backend/app/research/domain/contracts.py backend/app/research/domain/models.py backend/app/research/domain/state_machine.py backend/app/research/infrastructure/research_store.py backend/app/memory/models.py backend/app/memory/repository.py backend/app/api/routes_research.py tests/test_spec034_task02_contract.py` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/research/domain/contracts.py backend/app/research/domain/models.py backend/app/research/domain/state_machine.py backend/app/research/infrastructure/research_store.py backend/app/memory/models.py backend/app/memory/repository.py backend/app/api/routes_research.py tests/test_spec034_task02_contract.py` | 1 | 14 个既有 lint 问题；ruff 可用，新增 hunk 无新增诊断 |
| `git diff --check 1879fb3 --` | 0 | 通过 |

## 复审结论

**GO**。四项 P1 修复已由实现检查、增量合同测试和定向回归共同验证；P2-01 为既有 lint 技术债，不阻塞 Task02 后端进入下一门禁。后续若变更 replay 投影协议或通知身份字段，应补充跨库集成测试并重新评审。
