# Spec022 Task07 后端评审报告

## 评审元数据

- 角色：backend-reviewer
- 范围：仅评审 Task07 后端实现；未修改 `backend/**`、测试或其他业务代码。
- 依据：Spec022、`docs/sdd/plans/022/task-07-capability-memory-proposals.md`、Task07 implementation/test reports、Task04/Task10 报告，以及当前 `models.py`、`repository.py`、`conversation_service.py`、`tests/test_task07_backend.py`。
- 评审日志：`.codebuddy/agent-logs/spec-022/task-07/backend-reviewer/20260911-183411.md`
- 第一轮结论：**NO-GO**（发现 4 项 P1；已由 backend-dev 修复）。
- 第二轮结论：**NO-GO**（原 4 项 P1 的修复通过；发现 2 项 P1 证据真实性/并发状态一致性问题，已由 backend-dev 修复）。
- 最终复审结论：**GO**（P0=0、P1=0、P2=2；限定后端验证全部通过）。

## 评审摘要

Task07 的主体设计方向正确：能力方法复用 `MemoryRecord`，召回按 owner/global/project 隔离并受数量/字符预算限制；失败路径会追加 `tool_failure` 证据、降低 confidence 并改为 `candidate`；proposal 生成没有文件系统写入口，且 `applied` 需要外部确认及 hash 相等。Task07 + memory + Task10 定向回归为 37 passed，语法与空白检查通过。

第一轮发现的状态机、schema、无证据入口和并发重复问题已按修复报告落地并通过定向回归；最终复审仍发现 worker 对 `method_explicit`/`method_repeated` 的原始证据真实性未做服务端校验，以及 proposal 状态更新缺少并发 CAS，仍不能放行。

## P0/P1/P2 清单

### P0：0

未发现运行时写入 `.agents/skills`、`AGENTS.md`、Prompt 模板、项目代码或用户配置的路径；worker 没有文件系统写 API，也没有读取 Langfuse、agent logs 或隐藏思维链的 import/路径。

### 第一轮 P1：4（历史记录，已修复）

#### P1-1：proposal 状态机允许 `proposed → applied`

- 证据：`backend/app/memory/repository.py:809-817` 的 `allowed` 明确只给 `proposed` 配置 `accepted/rejected`，但随后例外条件 `status == "applied" and current.status == "proposed"` 放行了直接应用。
- 复现：新建 `proposed` proposal 后直接调用 `update_skill_improvement_proposal(..., status="applied", external_confirmation=True, protected_hash_after=protected)`，实际返回 `applied`。
- 影响：绕过用户/外部 SDD 流程的 accepted 门禁，违反 Task07 冻结的 `proposed -> accepted/rejected -> applied`，也使审查状态不能表达“尚未接受但已经应用”。
- 修复要求：删除该例外；仅允许 `accepted -> applied`，并补测 proposed 直接 applied 必须抛 `ValueError`。保留 rejected/applied 终态不可回退。

#### P1-2：Task07 schema 完整性校验不 fail-closed

- 证据：`backend/app/memory/repository.py:520-536` 的 `_is_task07_schema()` 只校验表存在、列名集合和两个索引名称；没有校验列类型、`NOT NULL`、默认值、主键、三组 CHECK、`project_id/source_memory_id` 外键及 `ON DELETE`、索引所属列/唯一性/排序。
- 复现：将 `skill_improvement_proposals` 替换为同名但无 NOT NULL/CHECK/FK 的表，创建同名但只索引 `owner_id` 的两个索引；重新 `MemoryRepository(path)` 返回成功，未触发预期的 fail-closed。
- 影响：损坏或降级 schema 可以启动，随后接受非法 scope/status/owner 关系；与 Task07 要求的 v6 兼容扩展“列/索引校验和损坏 fail-closed”不符，属于数据完整性风险。
- 修复要求：像 Task10 的 v6 校验一样逐列检查 type/notnull/pk/default，检查 sqlite table SQL 中的 CHECK，检查 `PRAGMA foreign_key_list`，并用 `PRAGMA index_list/index_info` 验证每个索引的表、列、顺序和 unique 属性；补充缺列、错类型、可空约束、错误 CHECK/FK、错误索引列的启动拒绝和事务回滚测试。

#### P1-3：能力方法证据门可被直接绕过，重复/显式证据未做真实性校验

- 证据一：`backend/app/memory/repository.py:630-633` 将 `manual` 作为 capability method 来源，且 `evidence is None` 时允许继续；默认 `status="active"`（625）。因此可以无 evidence 直接创建 active `capability_method`，不经过明确用户要求、跨会话重复或“失败后验证成功”门禁。
- 证据二：`backend/app/chat/application/conversation_service.py:384-395` 对 repeated 只检查 payload 的 `repeated_sessions/distinct_conversations >= 2`，未核验 distinct conversation IDs 或持久化 evidence 数量；`method_explicit` 主要信任 event kind 与 `explicit` 字段（默认 True），没有验证关联消息为用户原话/明确方法要求。
- 影响：伪造或误标事件可把一次成功/任意文本变成方法卡，污染后续召回；这直接违反“明确/重复/验证成功”证据门及“不把一次成功升格为通用能力”。
- 修复要求：方法卡创建 seam 只接受 `explicit/repeated/verified_failure`，或明确把 manual 限定为已有 candidate 的人工确认且仍要求 evidence；repeated 必须由 repository 根据至少两个不同 conversation/message 证据计算，explicit 必须校验关联 message 的 owner/conversation/`role='user'` 并保留原文证据；补伪造 event、单会话 repeated、assistant message、manual 无证据的拒绝测试。验证成功也应使用结构化布尔信号，避免任意非空字符串充当成功。

#### P1-4：同名能力方法并发创建不原子，重复合并失效

- 证据：`backend/app/memory/repository.py:634-647` 先在独立只读连接查询 active/candidate，再调用 `create_memory()` 开启另一事务；数据库没有 capability method 的规范化唯一约束或 fingerprint。
- 复现：8 个线程同时调用同一 owner/project/statement 的 `create_capability_method`，返回 8 个不同 memory ID，数据库中实际存有 8 条同名方法卡（默认 recall limit=5 只是隐藏部分重复，不能修复数据污染）。
- 影响：跨会话 worker 并发时会污染记忆库、消耗 recall budget，并违背“重复合并”契约；进程内 session lock 只保护同一 conversation，不能解决不同 conversation 的并发。
- 修复要求：把规范化 statement 的 duplicate check 与 insert 放进同一写事务并在事务内二次检查；最好新增稳定 fingerprint/唯一索引（owner、scope、project、category、normalized statement），或在全局写锁下完成；补多线程并发重复创建测试。

### P2：2

#### P2-1：验证信号和哈希值的输入校验偏宽

`bool(payload.get("verification"))` 会把字符串 `"false"` 当作成功，`_canonical_hashes()` 只要求 digest 是非空字符串而不校验算法/格式。当前没有直接造成文件写入，但会削弱“验证成功”和 protected hash 门禁的可审计性。建议使用结构化 `verification_succeeded is True` 和明确 hash 格式校验，并覆盖错误类型/空对象场景。

#### P2-2：负向污染与零写权限测试仍不完整

静态检查确认 Task07 代码没有 `.agents/skills`、`AGENTS.md`、Prompt、Langfuse、agent logs 或文件写 API；现有 `test_proposal_generation_does_not_write_protected_file` 只验证一个普通 `AGENTS.md` 路径 hash 未改变，尚未覆盖带完整工具输出/隐藏链字段、恶意目标路径、worker 事件负载和 proposal malformed hash 的负向矩阵。建议复审时补行为探针。

## 逐项契约核对

| 契约 | 结论 | 证据 |
|---|---|---|
| `MemoryRecord` 复用与 category 限定 | 部分通过 | `create_capability_method()` 委托 `create_memory(..., category='capability_method')`；但 manual 无证据入口见 P1-3。 |
| 明确/重复/验证成功证据门 | 不通过 | 显式/重复主要信任事件 payload；manual 可无证据，见 P1-3。 |
| 失败追加 evidence、降权、candidate、不覆盖历史 | 通过 | `record_capability_failure()` 在同一事务追加 `tool_failure` 并更新 confidence/status；现有测试确认 evidence 数量从 1 到 2。 |
| owner/global/project scope 隔离 | 通过（方法召回） | `list_capability_methods()` 按 owner、global 或当前 project 查询；proposal create/list 也检查 owner/scope。仍需补跨 owner/project proposal 负向测试。 |
| 方法数量/字符预算 | 通过 | recall limit capped at 20（默认 5），按 statement 字符累计；`list_recall_context()` 使用剩余 memory budget。 |
| v6 兼容扩展原子初始化 | 通过（正常/缺表路径） | 初始化在既有 `BEGIN IMMEDIATE` 中执行扩展表与索引；缺表时正常建表。结构损坏 fail-closed 不通过，见 P1-2。 |
| proposal 列/索引损坏 fail-closed | 不通过 | 只检查列/索引名称，见 P1-2。 |
| 状态 proposed→accepted/rejected→applied | 不通过 | `proposed→applied` 例外放行，见 P1-1。 |
| applied 外部确认与 protected hashes 不变 | 部分通过 | accepted→applied 要求 `external_confirmation` 且 after==before；但输入校验宽，且 proposed 旁路存在。 |
| worker 不学习隐藏链/Langfuse/logs | 通过（静态） | 未发现相关读取/import；运行时只处理 durable event payload。需补负向行为测试，见 P2-2。 |
| worker 不写 skills/AGENTS/Prompt/代码 | 通过（静态+已有探针） | 无文件写入口；proposal 仅入库，现有保护文件 hash 测试通过。 |
| 并发/事务/重复合并 | 不通过 | failure evidence 更新是原子事务；但 capability duplicate check 与 insert 分离，重复竞态见 P1-4。 |
| Task04/Task10 行为无回归 | 通过（定向） | memory/Task10 组合 37 passed；额外 worker timing smoke 1 passed。Task04 已知时序性 P2 仍需收口观察。 |

## 定向验证

| 检查 | 命令 | 退出码/结果 |
|---|---|---|
| Task07 + memory + Task10 后端定向测试 | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_task07_backend.py tests/test_memory_repositories.py tests/test_task10_backend.py --tb=line` | **0；37 passed，1 warning** |
| Task04 受影响 worker smoke | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse --tb=line` | **0；1 passed，1 warning** |
| Python 语法 | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/chat/application/conversation_service.py tests/test_task07_backend.py` | **0；通过** |
| 差异空白 | `git diff --check` | **0；通过** |
| 冲突标记 | `rg -n '^<<<<<<<|^=======|^>>>>>>>' ...` | **1；无匹配（通过）** |
| 状态机旁路探针 | 新 proposal 直接 `proposed→applied` | **失败；实际被接受** |
| schema 损坏探针 | 同列名但错误约束/错误索引列的 Task07 表重新初始化 | **失败；实际启动成功** |
| 并发重复探针 | 8 线程同 owner/project/statement 创建方法卡 | **失败；实际 8 个 memory ID/8 条记录** |
| manual 证据探针 | `source_kind='manual'` 且 `evidence=None` 创建方法卡 | **失败；实际创建 active 卡** |

## 后续动作

1. backend-dev 修复 P1-1 至 P1-4，并在 Task07 `test_task07_backend.py` 或新增后端合同测试中补齐上述回归/并发/损坏 schema 负向用例。
2. backend-reviewer 复审同一交接报告和同一工作树；复审至少重跑 37 项组合测试、schema 损坏探针、状态机探针与多线程重复合并探针。
3. backend-tester 在复审 GO 后复跑 Task07 + memory/Task10 定向后端回归；保留 Task04 worker timing 的独立重跑证据。
4. 当前不得把 Task07 标记为已完成，也不得进入 acceptance/deploy；全量回归仍留给 Task08。

## 签字

- backend-reviewer：**NO-GO**
- 评审时间：2026-09-11（Asia/Shanghai）

## 第二轮最终复审（P1 修复后）

### 修复确认

backend-dev 本轮声明的四项 P1 修复均已在当前源码和测试中确认：

1. `update_skill_improvement_proposal()` 现在只允许 `proposed → accepted/rejected`、`accepted → rejected/applied`；`proposed → applied` 和 `rejected → applied` 均拒绝（`repository.py:884-894`）。
2. `_is_task07_schema()` 已逐列校验顺序、类型、NOT NULL、默认值、PK，校验三组 CHECK、两组 FK 的列与删除语义、索引唯一性和列顺序（`repository.py:526-578`）；损坏表启动 fail-closed。
3. capability method 的所有 source（含 `manual`）都要求完整 evidence；无来源引用、非法类型或空 excerpt 拒绝（`repository.py:658-669`）。
4. duplicate check 与 insert 已在同一 `BEGIN IMMEDIATE` 事务内完成（`repository.py:705-722`）；8 线程同名创建只返回一个 memory ID。

### 当前残余 P1：2

#### P1-R1：worker 仍信任伪造的 explicit/repeated 事件证据

- `conversation_service.py:384-395` 对 `method_repeated` 只判断 payload 的 `repeated_sessions/distinct_conversations >= 2`，没有从持久化 evidence 计算至少两个不同 conversation；单一会话伪造 `repeated_sessions=2` 实际可生成方法卡。
- 同一段对 `method_explicit` 默认 `explicit=True`，没有验证 `event.message_id` 对应消息为 `role='user'`，也没有验证原始用户文本确实是明确方法要求；将 assistant message 作为来源的探针实际生成方法卡。
- 影响：攻击/误标事件仍可将一次成功或模型/assistant 文本升格为可召回能力方法，违反 Task07 的“明确用户要求、跨会话重复、失败后验证成功”证据门。
- 修复要求：explicit 必须在同一事务校验 owner/conversation/message 且 message role 为 user，并要求原始文本的明确意图；repeated 必须由 repository 根据至少两个不同 conversation/message evidence 计算，不能信任一个计数；补 assistant-source、single-session-repeated 和伪造 payload 负向测试。

#### P1-R2：proposal 状态更新缺少并发 CAS，终态可被旧决策覆盖

- `repository.py:880-897` 先在事务外读取 `current` 并校验状态，随后 UPDATE 的 WHERE 只有 `proposal_id/owner_id`，没有包含读取到的 `status` 或 protected hash。
- 复现：两个线程同时对同一个 accepted proposal 提交 `rejected` 与 `applied`；两者都可能通过旧状态检查，若 reject 先提交、apply 后提交，最终状态会重新变为 `applied`，覆盖已提交的 reject。
- 影响：并发人工/外部 SDD 决策可绕过终态保护，破坏 proposal 状态机和“applied 只能由当前 accepted 外部确认”契约。
- 修复要求：将读取、允许迁移判断和 UPDATE 合并到同一 `BEGIN IMMEDIATE` 事务；UPDATE 增加 `status=<expected_current>`（并可同时校验 protected_hash_before），rowcount=0 时返回稳定冲突错误，不覆盖已终态。

### 第二轮 P0/P1/P2

- P0：0。仍未发现文件系统写入 `.agents/skills`、`AGENTS.md`、Prompt、代码或用户配置，也未发现 Langfuse/agent logs/隐藏思维链读取。
- P1：2（P1-R1、P1-R2）。
- P2：2（验证字符串/哈希格式输入偏宽；零写/污染负向矩阵仍可扩充）。

### 第二轮验证命令

| 检查 | 命令 | 退出码/结果 |
|---|---|---|
| Task07 + memory + Task10 定向后端 | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_task07_backend.py tests/test_memory_repositories.py tests/test_task10_backend.py --tb=line` | **0；40 passed，1 warning** |
| Task04 worker smoke | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse --tb=short` | **0；1 passed，1 warning** |
| Python 语法 | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/chat/application/conversation_service.py tests/test_task07_backend.py` | **0；通过** |
| 差异空白 | `git diff --check` | **0；通过** |
| assistant explicit 负向探针 | assistant message + `method_explicit` 事件 | **失败；仍生成 1 张方法卡** |
| single-session repeated 负向探针 | 单会话 + `repeated_sessions=2` | **失败；仍生成 1 张方法卡** |
| 修复新增状态/schema/manual/concurrency 测试 | 已包含于 Task07 9 项测试及组合回归 | **通过；组合总计 40 passed** |

### 第二轮最终签字

- backend-reviewer：**NO-GO**
- 时间：2026-09-11（Asia/Shanghai）
- 业务代码改动：无；仅更新本评审报告与进展日志。

## 第三轮最终复审（第二轮 P1 修复后）

### 修复确认

第二轮发现的两项 P1 已在当前源码和测试中确认修复：

1. `method_explicit` 在 `record_trigger()` 与 worker materialize 路径均校验关联消息属于同一 conversation 且 `role='user'`；assistant message 事件不会生成方法卡。
2. `method_repeated` 不再信任 `repeated_sessions` 计数，而是由 `count_capability_method_evidence()` 联结 durable raw event、conversation 和 user message，按 owner/project/category/statement 统计不同 conversation；单会话伪造计数不会入卡，两个真实会话才可入卡。
3. proposal 决策已在 `BEGIN IMMEDIATE` 内读取、校验迁移并以 `WHERE ... status=?` 做 expected-status CAS；竞争更新返回 `proposal state conflict`，不会覆盖已提交终态。

### 第三轮验证

| 检查 | 命令 | 退出码/结果 |
|---|---|---|
| Task07 + memory + Task10 定向后端 | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_task07_backend.py tests/test_memory_repositories.py tests/test_task10_backend.py --tb=line` | **0；43 passed，1 warning** |
| Task04 worker smoke | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse --tb=short` | **0；1 passed，1 warning** |
| Python 语法 | `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/chat/application/conversation_service.py tests/test_task07_backend.py` | **0；通过** |
| 差异空白 | `git diff --check` | **0；通过** |
| assistant explicit 负向测试 | `test_method_explicit_rejects_assistant_message` | **通过；不生成方法卡** |
| forged repeated count 负向/真实跨会话正向测试 | `test_method_repeated_ignores_forged_count_and_requires_two_conversations` | **通过；单会话拒绝、两真实会话入卡** |
| proposal CAS 并发测试 | `test_proposal_decision_is_compare_and_set_under_concurrency` | **通过；一方成功、一方冲突** |

### 第三轮 P0/P1/P2

- P0：0。未发现运行时写入 `.agents/skills`、`AGENTS.md`、Prompt、代码或用户配置；未发现读取 Langfuse、agent logs 或隐藏思维链。
- P1：0。上一轮四项 schema/状态/evidence/duplicate P1 与本轮两项 evidence/CAS P1 均已关闭。
- P2：2：验证字段/哈希格式仍可进一步收紧；零写权限与污染负向矩阵仍可扩充，但不阻断 Task07 后端评审。

### 第三轮结论与后续动作

**GO（backend-reviewer）**。Task07 后端可进入主 Agent 的跨端验收/收口流程；本评审未运行全量 pytest、前端测试、部署或最终运行时 smoke，这些仍按 Task08/Spec022 收口流程执行。

### 最终签字

- backend-reviewer：**GO**
- 时间：2026-09-11（Asia/Shanghai）
- 业务代码改动：无；仅更新本评审报告与进展日志。
