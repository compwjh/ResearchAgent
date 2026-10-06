# 后端评审报告 — spec-041 T-B（埋点 input 全量）

- 评审角色：backend-reviewer
- 分支：`feature/spec-041-langfuse-trace-detail`（未切分支、未 commit/push）
- Spec：`docs/sdd/specs/041-langfuse-trace-detail-and-waterfall.md`
- 改动范围：T-B「redact_prompt_messages 保留原文 content，input 全量可见」
- 评审日期：2026-09（按进度日志）

## 结论：通过（附 1 条可选建议）

改动精准、fail-open 语义保持、单测锁定到位。有 1 处命名建议（非阻塞），无必改项。

---

## 逐条核对

### 1. 修复点是否落在函数本体，5 个调用点无绕过 ✅
- 全部 5 处 `redact_prompt_messages(` 调用点（grep 实证）：
  - `backend/app/platform/observability/spans.py:177`（在 `record_ollama_generation` 的 `_report` 内）
  - `backend/app/api/routes_article.py:133`
  - `backend/app/api/routes_chat.py:107`
  - `backend/app/api/routes_kb.py:1058`
  - `backend/app/api/routes_conversations.py:933`
- 关键事实：真正落到 Langfuse `input` 的格式化由 `spans.py:177` 的
  `_format_messages(redact_prompt_messages(prompt_messages))` 完成，是**唯一 choke point**。
  4 个 route 入口即使各自先 redact 一次，仍会在进入 `record_ollama_generation` 时被再次
  redact（幂等），因此不存在「某条路径绕过 redact 而仍被清零」的情况。
- routes_kb / routes_conversations 均已确认经由该函数，无遗漏调用点。

### 2. 单测是否真能锁定行为 ✅（满足 regression-guard 边界 12）
- 新增文件 `tests/test_observability_prompt_input.py`，共 6 个用例，直接 `import` 被测函数
  （模块被整目录删除时 import 即失败，非静默跳过；无「缺文件就 return 通过」守卫）。
- 非恒真断言：
  - `test_preserves_role_and_original_content_per_message`：`assertEqual(observed["content"], original["content"])`（逐字期望原文）
  - `test_route_entry_reports_full_prompt_content`：`assertIn("请总结这篇论文的核心贡献与实验设置", reported_input)`（逐字原文）
- 覆盖 ≥2 入口：函数本体（`redact_prompt_messages`）+ route 级同款调用（`record_ollama_generation`）。
- 另三处修改测试同步改为断言原文 content：
  - `tests/test_chat_route.py`：`content == "hi"` / `content == "secret-token"`（精确相等，非 `all(...)==""`）
  - `tests/test_kb_ask_trace.py`：`all(message["content"] for ...)`（仅判非空，较弱，但由新文件精确断言补足）
  - `tests/test_system_rule_backend.py`：`redact_prompt_messages(...) == [{"role":"system","content":"secret rule"}, {"role":"user","content":"secret question"}]`（精确相等）

### 3. fail-open 是否保持 ✅
- `git diff` 显示：原在 `safe_call` 之外的
  `formatted_input = _format_messages(redact_prompt_messages(prompt_messages))` 已移入 `_report`
  闭包内（spans.py:171-188），并由 `safe_call(_report)`（spans.py:213）包裹。
- `_report` 仅含观测代码（格式化 + `langfuse.start_as_current_observation` + metadata 构建），
  不含任何业务逻辑，因此本次移动**只吞观测异常，不吞业务异常**。
- 验收测试 `test_formatting_exception_is_swallowed`：monkeypatch `redact_prompt_messages` 抛
  `RuntimeError`，断言 `record_ollama_generation` 不冒泡——直接锁死该回归。

### 4. 隐私改动范围是否越界 ✅
- `backend/app/platform/observability/config.py` **不在 diff**，故 `OBS_MAX_INPUT_CHARS`(20000)
  截断上限未放宽；`max_input_chars()` 仍于 spans.py:196 经 `_truncate(...)` 生效。
- `should_sample()` 采样率语义未改。
- OTel 上报路径 / Langfuse SDK 版本未改（diff 仅触及 spans.py 与测试）。
- 业务对话逻辑（构建 prompt、流式输出、repos 写入）未被改动；4 个 route 仅把
  `observation_messages` 的取值从「清零」变为「原文」，调用位置与参数不变。

### 5. 删改是否留下死代码 / 不一致注释 ✅（少量可选建议）
- grep 全文未见残留隐私注释（旧注释 "observability must never persist user/system prompt text"
  已在 diff 中删除）。函数 docstring（spans.py:228-238）与行内注释（spans.py:174-176）均与新行为一致。
- **可选建议**：函数名 `redact_prompt_messages` 现已名不副实（不再 redact）。建议重命名为
  `normalize_prompt_messages` 或 `format_observation_input`（仅归一化 role / 兜底 content），
  降低后续维护者误读。**不要求本次修改，亦不影响合入。**

### 6. 命令核实（真实执行）
- pytest（4 文件，含新增测试）：
  - 首次因 broker 沙箱拦截 `/tmp` 创建报 `PermissionError`（环境限制，非代码问题）；
    改用 `TMPDIR`+`--basetemp` 指向仓库内临时目录后执行。
  - 结果：**33 passed, 1 warning**（新增 `test_observability_prompt_input.py` 6 例全过，
    `test_chat_route.py` / `test_kb_ask_trace.py` / `test_system_rule_backend.py` 修改用例全过）。
- ruff：
  - 改动文件 `backend/app/platform/observability/spans.py`、`.../safe.py`、`tests/test_observability_prompt_input.py`
    → **All checks passed!**
  - 全仓 `ruff check backend tests` 报 105 errors，均为改动前既有问题，**不在本 diff 内、非本次引入**。

---

## 必改项清单
（无必改项）

| 级别 | 位置 | 说明 |
|------|------|------|
| — | — | 无 |

## 可选建议
1. 【LOW】`redact_prompt_messages` 重命名为 `normalize_prompt_messages`（语义对齐，非阻塞）。
2. 【LOW】4 个 route 入口的 `observation_messages = redact_prompt_messages(prompt_messages)` 现与
   `record_ollama_generation` 内部二次 redact 重复（幂等无害）。若后续重命名，可顺手评估是否
   在 route 层移除冗余调用以减歧义（保持现状亦不影响正确性）。

## 签字
- 评审人：backend-reviewer（只读评审，未改代码 / 未 commit / 未 push）
- 日志：`.codebuddy/agent-logs/spec-041/task-04/backend-reviewer/progress.md`
