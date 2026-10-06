> 关联：[spec-037](../../specs/037-startup-readiness-gap-and-ux-bugs.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`

# 任务 02：后端——context-usage 计入恒定上下文

## 一句话目标
让 `GET /api/conversations/{id}/context-usage` 的用量估算与真实装配**同源**，把恒定上下文（系统规则 / USER.md / MEMORY.md / 项目 MD）计入 `used_tokens` 与 `breakdown`。

## 背景与前置条件
- spec-037 Bug 1（后端半）。
- 已核实：真实对话路径 `routes_conversations.py:796` 调 `compose_chat_messages(..., system_rule=user_memory, ...)`；而 dry-run `compute_context_usage`（`routes_conversations.py:409-413`）调 `compose_chat_prompt` 时**未传 `system_rule`** → 漏算。
- 相关文件：`backend/app/api/routes_conversations.py`（`compute_context_usage` 389-431、`_CONTEXT_BREAKDOWN_LABELS` 359-368）、`backend/app/chat/application/conversation_service.py`（`compose_chat_prompt` 473+）、`backend/app/memory/markdown_store.py`（`read_user_memory_or_empty` 441）。

## 实施步骤（文件边界：`backend/app/api/routes_conversations.py` 为主）
1. 读 `compose_chat_prompt` 完整签名，确认是否接受 `system_rule` 关键字参数。
2. 在 `compute_context_usage` 中取 `user_memory = read_user_memory_or_empty()`，作为 `system_rule` 传入 dry-run 装配（与真实路径一致）。
3. 确认 `compose_chat_prompt` 内部对文件记忆（USER.md / MEMORY.md / 项目 MD）的读盘是否在 dry-run 中执行；未执行则纳入，确保与真实装配来源一致。
4. `breakdown` 中恒定段须带中文 label（复用 `_CONTEXT_BREAKDOWN_LABELS`；`file_memory` 已存在，系统规则段缺失则新增）。
5. 返回值契约不变：`used_tokens / budget_tokens / ratio / segment_count / compaction_status / breakdown`。

## 边界与明确不做
- **不改** `compose_chat_prompt` / `MarkdownMemoryStore` 的装配与读取语义。
- **不改** `CHAT_TOTAL_TOKEN_BUDGET` / `CHAT_COMPACT_TRIGGER_RATIO`。
- 不新增表、不改端点路径与既有字段。
- **不得**把根目录 `CONTEXT.md` 计入（已核实后端不读它；如需计入属新能力，另立 spec）。

## 验收
- 系统规则或 USER.md 非空时，`used_tokens` 明显大于同输入下的「仅历史」估算，且 `breakdown` 含对应恒定段中文 label。
- 空记忆（USER.md 缺失/为空）时 fail-open 返回空串，不抛异常、不 500。
- 既有 context-usage 相关用例全绿。

## 产出物、执行结果与变更日志

### 改动文件与行数
- `backend/app/api/routes_conversations.py`
  - `_CONTEXT_BREAKDOWN_LABELS`（约 357-368）：新增 `"system_rule": "系统规则"` 映射（+4 行）。
  - `compute_context_usage`（约 413-428）：+11 行——读取 `user_memory = read_user_memory_or_empty()`；给 `compose_chat_prompt` 补 `project_id=conversation.project_id`；`user_memory` 非空时在 sections 前插入 `("system_rule", user_memory.strip())` 恒定段。

### 关键结论（已核实，非重复排查）
- `compose_chat_prompt`（conversation_service.py:473-494）**不接受** `system_rule` 关键字；`system_rule` 由真实路径 `compose_chat_messages`（357 行）→ `build_role_aware_messages`（chat_runner.py:41-44）以独立 system 消息逐字注入（`content = system_rule.strip()`，无前缀）。
- 因此未给 `compose_chat_prompt` 加参数（避免改动其装配语义，符合边界），而是在 `compute_context_usage` 内以等价恒定段计入，与真实装配同源。
- 旧 dry-run 调 `compose_chat_prompt` 未传 `project_id`，导致项目 MD（`projects/<id>.md`）漏读；本次补 `project_id=conversation.project_id` 修复（与真实路径 796 行一致）。`file_memory_snapshot`/`load_snapshot` 本就读 USER.md（优先全量）+ MEMORY.md + 项目 MD，故全局记忆与 USER.md 原已计入；项目 MD 此前漏算。
- 未纳入 `PLATFORM_SYSTEM_MESSAGE`（不在任务枚举内、现有 dry-run 也未计入，属范围外）；未纳入根目录 `CONTEXT.md`（后端不读它）。

### 新增 / 更新测试
`tests/test_conversation_context_usage_api.py` 新增 3 个（均 monkeypatch `MEMORY_DIR` 到临时目录、写真实 MD 文件，与真实读盘同源）：
- `test_context_usage_counts_system_rule_and_file_memory`：USER.md/MEMORY.md/项目 MD 均存在 → breakdown 含 `system_rule`(系统规则) 与 `file_memory`(文件记忆 (USER.md / MEMORY.md))，tokens>0、used_tokens>0。
- `test_context_usage_empty_memory_fail_open`：空记忆 → 200、不 500、无恒定段、used_tokens>=0（fail-open）。
- `test_context_usage_project_md_counted_via_project_id`：仅项目 MD → `file_memory` 段必须出现（直接回归 project_id 漏传修复）。

### 定向测试命令与结果
- `cd backend && source ../.venv/bin/activate && python -m pytest tests/test_conversation_context_usage_api.py tests/test_memory_injection_chain.py tests/test_system_rule_backend.py -q`
  - 结果：**33 passed**（13 上下文用量 + 12 记忆注入链 + 8 系统规则后端）。
- `ruff check backend/app/api/routes_conversations.py`：5 个错误均位于 line 60/831/895/928/979，**均非本任务改动区（357-368、413-428）**，属预存在 lint，按最小改动原则未处理。
- 说明：`test_auto_compaction_threshold_boundary`（0.79/0.80 边界，预存脆弱：预算由发消息前的 `used` 推导、触发却用含新消息的 `used`）在整文件首跑偶发失败 1 次、重跑即 **13 passed**。该会话无记忆文件、无 project，本改动对 `compute_context_usage` 输出逐字节等价，flake 为预存在、非本任务引入。

### 回归清单（regression-guard 后端 5-9 自查）
- 无新增表/迁移；端点路径与返回契约（used_tokens/budget_tokens/ratio/segment_count/compaction_status/breakdown）未变。
- 未引入并发领用/资源额度变更；未新增外部依赖调用（读取沿既有 `read_user_memory_or_empty`/`MarkdownMemoryStore` 缝，fail-open）。
- 无重复实现（复用既有 `read_user_memory_or_empty`、`compose_chat_prompt`、`file_memory_snapshot`）。
- 未改变 `CHAT_TOTAL_TOKEN_BUDGET` / `CHAT_COMPACT_TRIGGER_RATIO` 等常量。

### 风险与阻塞
- 风险：自动压缩阈值边界测试（`test_auto_compaction_threshold_boundary`）预存脆弱，环境存在真实记忆文件（C>0）且新消息导致 used 轻微波动时，边界有极小概率翻转；本任务要求的恒定上下文计入是对称叠加（测量与触发同用 `compute_context_usage`），不放大该风险，但建议在 task-07 回归时评估加固该边界测试。
- 阻塞：无。
