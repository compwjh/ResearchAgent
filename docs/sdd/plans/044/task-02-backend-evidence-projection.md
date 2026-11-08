> 关联：[spec-044](../../specs/044-conversation-answer-display-and-provenance.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`

# Task02 后端 detail_json 证据投影

## 1. 状态与一句话目标
- 状态：`已完成`。
- 一句话目标：在后端 4 类步骤创建处，将**真实召回/应用过**的结果投影为 `step-evidence-v1` 并写入 `detail_json`，复用既有脱敏裁剪；不落库 URL、不编造 ID/分数/来源，交付一个可独立验收的投影结果。

## 2. 背景与前置条件
- 依赖 task-01：spec-044 已落地（状态 `待确认`），数据模型与边界已冻结。
- 设计依据：spec「数据模型」「边界」「明确不做」章节；`decision-baseline.md` D1/D8 与 C1–C7。
- 真实文件事实：
  - `backend/app/memory/repository.py:1729` 是**生效** `create_processing_step` 签名（含 `detail_json`）；旧 `:1623` 已被覆盖（C3），不得引用。
  - `backend/app/api/routes_conversations.py` 的 4 类步骤调用点：memory_recall（记忆召回）/ system_rule（系统规则）/ rag_retrieval（知识库检索）/ generation（回答生成）。
  - RAG 字段口径以 `citation_payloads()` 为准（`prompts.py:54-74`，C5）。
  - 记忆命中仅 6 字段、无 `score`（`session_search.py:69-85`，C4）。

## 3. 数据、配置与接口
- 增量：在 4 类步骤调用点按 `detail_json=` 关键字投影 `step-evidence-v1`（`records[]` 元素：`kind/title/snippet/score/occurred_at/source_kind/ref_id/document_id/chunk_id/conversation_id/target`，**扁平化，不嵌套 `source_ref`**）。
- 来源字段（扁平）口径：记忆 `source_kind=message/memory`、`ref_id=message_id` 或 MD 相对路径（C4）；RAG `document_id=hit.paper_id`、`chunk_id=point_id(...)`、`conversation_id`/`target` 按 spec（C1、C5）；全部字段位于 `record` 顶层（不嵌套 `source_ref`）。
- 投影后每个字段处于脱敏 depth ≤3，服务端须自检 `source_kind` / `document_id` / `chunk_id` / `conversation_id` / `ref_id` / `target` 未被 `_sanitize_processing_detail_json()` 裁掉（P1-1 修订、对应 spec S1-1 / decision-baseline C14）。
- 脱敏：统一经 `_sanitize_processing_detail_json()` 裁剪（C2、D8）；总长 >4000 整体降级 `{"truncated":true}`；控制 records 条数与 snippet 长度避免整体 truncated。
- 约束：遵守 C1（不落库 `url`/`source_url`）、C2（控制长度）、C4（不造 score）、C5（RAG 字段口径）；不涉及时写「不适用」。
- 接口：复用既有 `GET /api/messages/{message_id}/processing-steps`，不新增端点（D1）。

## 4. 实施步骤与文件边界
1. 定位 `routes_conversations.py` 中 4 类 `create_processing_step` 调用点。
2. 每处按 `detail_json=` 传入 `step-evidence-v1`（命中 `repository.py:1729` 生效签名，C3）。
3. RAG 投影取 `citation_payloads()` 输出的 `document_id`/`chunk_id`（C5）；记忆投影取 `SessionSearchHit.to_dict()` 的 `ref_id/content/conversation_id`，`score` 省略或 null（C4）。
4. 统一经 `_sanitize_processing_detail_json()` 裁剪（C2、D8）。
5. 目标文件：仅 `backend/**`（不改 `frontend/**`、不改 `processing_steps` 表结构）。
- 可观察结果：既有 `processing-steps` 历史水合返回的步骤 `detail_json` 含符合 schema 的真实投影（或 `null`/空 `records`），无 `url` 键、无编造 score。

## 5. 子代理分派
- 角色：backend-dev。模型：`Deepseek-V4.1-Flash`。
- 最小上下文：本 task + spec 数据模型章节 + `decision-baseline.md` D1/D8 与 C1–C7。
- 单次文件范围：仅 `backend/app/api/routes_conversations.py`（4 类调用点投影）与 `backend/app/memory/repository.py`（脱敏/写入两处）；不跨前端。
- 回传后架构师读回校验：`detail_json=` 命中 `:1729` 生效签名、经 `_sanitize_processing_detail_json()`、无 `url` 键、记忆无 `score`、RAG 用 `citation_payloads()` 口径。

## 6. 边界与明确不做
- 不落库 `url`/`source_url`（C1）。
- 不造 ID、不造分数（记忆类 `score` 省略/null，C4）、不造来源。
- 不新增 HTTP 端点、不新增表/迁移/字段（D1）。
- 不复制第二套脱敏逻辑，复用 `_sanitize_processing_detail_json()`（D8）。
- 不改 `repository.py` 任何代码、不抬高全局脱敏 `depth` 上限（靠扁平化 schema 保证来源字段处于 depth ≤3，D8 / P1-1）。
- 不引用旧 `:1623` 签名（C3）。
- 不控制前端（`frontend/**` 由 task-03/04 负责）。

## 7. 验收、风险与回滚
- 验收：① 4 类步骤均用 `detail_json=` 经 `:1729` 生效签名写入；② `detail_json` 解析为 `step-evidence-v1`，缺失字段省略/null；③ 无 `url` 键、记忆无 `score`、RAG 用 `citation_payloads()` 口径；④ `_sanitize_processing_detail_json()` 生效；⑤ 既有 `processing-steps` 接口返回结构与 spec 一致。
- 风险：误引用旧签名（C3）、误落库 url（C1）、编造 score（C4）。回滚到 task-01 与 spec，重做投影。

## 8. 产出物、执行结果与变更日志

- 产出文件：仅 `backend/app/api/routes_conversations.py`（+116 行）。新增模块级 `_step_evidence_payload(records)`（扁平投影 + `snippet` ≤120 / `title` ≤80 / 总数 ≤32 / 丢弃含 `url` 键 / 异常降级 `None`）；5 处完成态调用点写入 `detail_json=`：memory_recall done、system_rule completed、rag_retrieval completed、generation completed（技能+工具路径、普通路径各一处）。
- 真实命令与结果（退出码均为 0）：
  - `.venv/bin/python -m py_compile backend/app/api/routes_conversations.py` → 通过
  - `.venv/bin/python -m pytest tests/research/test_processing_tree_backend_contract.py -q` → `9 passed in 3.33s`
  - `.venv/bin/python -m ruff check backend/app/api/routes_conversations.py` → `All checks passed!`
  - 脱敏验证（构造含 `source_kind` / `document_id` / `chunk_id` / `conversation_id` / `ref_id` / `score` 与 `source_url` 的示例 payload，送入 `_sanitize_processing_detail_json`）→ `schema=step-evidence-v1 count=3`、`r0 keys=[chunk_id,document_id,kind,score,snippet,source_kind,title]`、`r1 keys=[conversation_id,kind,ref_id,snippet,source_kind]`、`SANITIZE_FLAT_OK`。断言：扁平字段全部保留、`snippet` 截 120、无 `source_url` / `source_ref` / 任何 `url` 残留、记忆类无 `score`。
- 架构师读回校验：主会话已 `sed`/`grep` 读回辅助函数与 5 处调用点，`import json/contextlib/time` 齐备，`ConversationSummary` 为 dataclass（属性访问正确），未改 `repository.py` / SSE 帧体 / `summary` / `citation_payloads` 既有调用。
- 风险与后续：running / failed / interrupted 分支不写明细（保持空态、不编造）；投影失败降级 `None` 不中断 SSE。task-05 需补 `detail_json` 契约与脱敏回归断言。
- 变更日志：2026-11-08 backend-dev 完成实现；2026-11-08 架构师读回校验与定向验证通过。
