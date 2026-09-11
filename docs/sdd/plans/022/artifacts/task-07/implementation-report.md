# Spec022 Task07 后端实现报告

## 状态摘要

已完成（backend-dev）。本报告先于业务代码变更创建；实现范围限定为能力方法记忆与只读 Skill 改进建议，复用既有 `MemoryRepository`、SQLite WAL/事务、owner/project scope、UTC 时间和 recall budget。

## 已确认范围与设计决策

- 方法卡继续使用 `memories` 中 `category='capability_method'` 的 `MemoryRecord`，不建立第二套记忆存储。
- 方法卡只有在明确用户要求、跨会话重复，或工具失败后有验证成功信号时创建；失败信号只会降低 confidence/进入候选复审，不覆盖既有证据。
- 方法卡 recall 复用 owner + global/project scope 隔离和字符预算，按当前任务关键词返回少量结果，并通过 `last_used_at` 记录使用。
- Skill 改进建议使用同一 SQLite repository 管理独立队列，字段包括目标文件、问题证据、diff 摘要、验证方式、风险、状态和 protected-file hash；状态限定为 `proposed / accepted / rejected / applied`。
- 运行时仅可生成、读取和更新审查状态；不读写 `.agents/skills/`、`AGENTS.md`、Prompt 或业务代码。`applied` 只能由显式外部 SDD 流程写入，并要求调用方提供前后保护文件 hash，后端只校验/记录，不执行文件写入。
- 不新增 Task07 公开 API 端点；后端提供 service/repository seam，后续 API/UI 若需要只能在已确认范围内复用这些方法。

## 预期改动文件

- `backend/app/memory/models.py`
- `backend/app/memory/repository.py`
- `backend/app/chat/application/conversation_service.py`（仅在既有演化 worker 中接入方法卡/建议生成 seam，如确有必要）
- `tests/test_task07_backend.py`

## 数据与接口契约（实现前冻结）

### Capability method

复用 `MemoryRecord` 字段：`scope`、`project_id`、`statement`、`source_kind`、`status`、`confidence`、`supersedes_id`、evidence。新增 repository 方法只接受 `category='capability_method'`，校验 owner/project scope；recall 默认最多 5 条并受独立字符预算限制。

### Skill improvement proposal

新增 `skill_improvement_proposals` 表：`proposal_id`、`owner_id`、`scope`、`project_id`、`target_file`、`problem_evidence`、`diff_summary`、`verification_plan`、`risk_summary`、`status`、`protected_hash_before`、`protected_hash_after`、`source_memory_id`、`created_at`、`updated_at`、`decided_at`。目标文件必须为审查建议文本，禁止任何运行时文件写入；状态迁移按 `proposed -> accepted/rejected -> applied`，`applied` 需外部明确写入且 hash 前后相等。

## 明确不做

- 不修改 `.agents/skills/`、`AGENTS.md`、Prompt 模板、代码文件或用户级配置。
- 不从隐藏思维链、Langfuse、Agent logs、完整工具输出或论文/知识库读取学习信号。
- 不自动把单次成功升格为通用方法，不自动 scope 转换，不自动覆盖或删除已有记忆/证据。
- 不运行全量回归、不修改前端、不触碰 Task02–06/09/10 契约。

## 验证计划

- 先新增 Task07 定向 pytest（预期先 RED，再实现后 GREEN）：方法卡来源门禁、owner/project 隔离、失败降权/候选复审、预算与少量召回、建议状态机、`applied` 外部 hash 校验、受保护文件 hash 不变。
- 使用 `.venv` 执行 Task07 定向 pytest；对改动 Python 文件执行 `py_compile`；执行 `git diff --check`。
- 不执行全量 pytest；Task08 负责最终全量回归、验收和部署。

## 风险与阻塞

- Task07 计划未冻结公开 API URL；本轮不自行新增端点，若隐藏验收要求公开 API，需要主 Agent 更新 spec 后重新确认。
- 方法卡与建议均采用 repository 内事务；schema 迁移失败继续 fail-closed，不允许启动时半迁移。

## 主 Agent 后续动作

1. 复核本报告中的 v7 schema 与状态机契约。
2. 分派 backend-reviewer 检查 owner/scope、迁移原子性、建议 hash 门禁和运行时零写权限。
3. 分派 backend-tester 按 test-report 复跑定向验收；Task08 再做全量回归与部署。

## 实际实现结果

- `backend/app/memory/models.py` 新增只读 `SkillImprovementProposal` DTO。
- `backend/app/memory/repository.py` 在既有 v6 事务迁移中原子创建并校验 `skill_improvement_proposals` 扩展表；保持 schema version=6 以兼容 Task10，现有 v6 数据库启动时补齐 Task07 表，结构损坏 fail-closed。
- `MemoryRepository` 新增 evidence-backed capability method 创建、owner/project scope 召回、预算/数量限制、重复合并、失败降权转 candidate、proposal CRUD/状态机与 applied hash 门禁。
- `backend/app/chat/application/conversation_service.py` 在既有演化 worker 中接入 `method_explicit`、`method_repeated`、验证成功的 `tool_failure` 信号；未验证失败追加失败证据并降权；事件提供完整建议字段时仅生成 proposed 队列项。
- 运行时没有文件系统写入入口；`.agents/skills/`、`AGENTS.md`、Prompt、代码文件和用户配置未被读取或修改。

## Reviewer P1 修复

- 删除 `proposed -> applied` 与 `rejected -> applied` 直达路径；只有 `accepted -> applied`，且继续要求外部确认及 protected hash 前后一致。
- `_is_task07_schema` 现在逐列校验顺序、类型、NOT NULL、默认值、PK，逐项校验 scope/status CHECK、FK 的列与 RESTRICT/CASCADE 语义、索引唯一性与列顺序；损坏表启动 fail-closed，schema version 仍为 6。
- 所有 `capability_method` source（含 manual）必须携带完整 evidence（来源引用、合法 evidence_type、非空脱敏摘录）；空 evidence 直接拒绝。
- 方法卡去重检查移动到同一 SQLite `BEGIN IMMEDIATE` 事务内，避免并发读后写竞态；不在锁内调用外部函数。

修复验证：新增 4 个 P1 定向探针（非法状态迁移、损坏列/索引 schema、manual 无 evidence、8 线程并发合并）均通过；Task07 总计 9 passed。

## Reviewer 第二轮 P1 修复

- `method_explicit` 在记录入口校验 `message_id` 属于同 owner/conversation 且 `role='user'`；assistant 消息不能触发方法卡。
- `method_repeated` 不再读取 `repeated_sessions`/`distinct_conversations` payload 计数；repository 从持久化 raw event 与 user message join 中计算不同真实 conversation 数，少于 2 个时拒绝生成。
- proposal 决策更新在同一事务中读取 expected status，并使用 `UPDATE ... WHERE owner_id=? AND status=?` CAS；rowcount 非 1 返回稳定冲突，终态不可被旧状态覆盖。
- 新增 assistant 伪造、单会话伪计数、两会话真实证据和 reject/apply 并发探针。
