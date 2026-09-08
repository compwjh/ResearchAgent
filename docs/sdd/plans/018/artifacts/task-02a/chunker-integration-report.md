# Spec018 Task02A-C SourceProvenanceBundle / chunker integration report

日期：2026-09-09
角色：Task02A-C backend-dev
模型：gpt-5.6-luna xhigh（临时，仅本轮）
结论：**READY FOR RE-REVIEW**

## 范围与边界

- 新增 `backend/app/knowledge_base/infrastructure/provenance.py`，只做正式
  `PdfSourceProvenanceV1` / `MarkdownSourceProvenanceV1` 到
  `SourceProvenanceBundleV1` 的组装和来源映射。
- 只复用 `chunkers.py` 的 `build_chunks_v1` / `build_chunks_v2`；未新增第三套
  切片器，未调用 embedding、Qdrant、index 或 API。
- `SourceProvenanceBundleV1` 的 schema version 固定为
  `source-provenance-bundle-v1`；它不是 `InspectionManifest`，本任务没有定义或持久化
  manifest。
- `chunkers.py` 仅将 `Chunk.page/page_end` 类型扩展为可空，并在 Markdown 输入时保留
  JSON `null`；PDF v1/v2 的既有整数页码和 `page_end` 默认行为不变。

## Bundle 契约

Bundle 固定包含：

- `document_id`、`media_type`、当前原件小写 `source_sha256`、`source_hash_state`；
- `source_parser_version`、`normalize_version`、`chunker`、规范化
  `chunker_config_fingerprint`、`payload_schema_version`；
- parser 原生 `pages` / `blocks`，复用 chunker 产生的 `chunks`，以及稳定排序的
  `anchors`、`mapped_count`、`unmapped_count`、`unmapped_reasons`；
- `chunk_snapshot_fingerprint`（仅代表 Task02A 本地 chunk payload 快照，不冒充 Qdrant
  `index_fingerprint`）、状态/进度/错误，以及 v2 的 `llm_used` 和
  `degradation_diagnostics`。

没有 `manifest`、embedding、Qdrant 或临时第二套 parser 字段。

PDF chunk 输入从同一 provenance DTO 的 `raw_text` 按 display insertion order 重建页文本，
再调用既有 `normalize_text`；没有再次打开 PDF 或做第二遍文本提取。Markdown
`markdown-block-v1` 按 parser blocks 调用既有 v1，chunk 与所属 block 保持一对多来源关系；
其余 v1/v2 按既有参数化算法运行。映射比较统一使用 NFKC、CRLF/LF、行尾空白和水平空白
规范化，coverage 为以 chunk 为左操作数、source block 为右操作数的 SequenceMatcher
规范字符重叠数除以 chunk 规范字符数（重复文本的方向性 tie-break 与冻结 oracle 一致）；排序按
coverage 降序、block ordinal、chunker、chunk_index，primary 唯一。无匹配时记录
`NO_SOURCE_BLOCK_OVERLAP`，不伪造 anchor。

v2 不注入默认网络/模型调用；未传 LLM 时保留 `llm_used=false` 与
`V2_RULES_ONLY_LLM_NOT_USED`。LLM 成功解析合法 `[]` 也记录 `llm_used=true` 且不产生
降级诊断；异常、超时或不可解析回复才走稳定降级状态。

## 固定样本机械对照

正式 parser 重放以下四个正常样本：

| 样本 | chunker | block/chunk 集合 | anchor 对/locator | bbox/行号 |
|---|---|---|---|---|
| `pdf-single-column-v1` | v1 | expected-defined 字段 exact | block_id/chunk_index/is_primary/locator exact | parser bbox 继承，误差门由 02B 验证 |
| `pdf-two-column-v1-overlap` | v1 | exact，含 200 字符 overlap | 完整 anchor dict（coverage/is_primary/locator）exact | parser bbox 继承 |
| `pdf-v2-cross-page` | v2 | exact，`page=1,page_end=2` | 两个跨页 anchor 对/locator exact | parser bbox 继承 |
| `markdown-blocks` | markdown-block-v1 | exact，5 个 block-preserving chunks | 5 个一对一 anchor/line locator exact | 1-based line exact |

首轮 expected 是 bundle-era `provenance-dto-v1`，而本轮正式产物分层为
`source-provenance-bundle-v1`；测试对仍适用的 block/chunk/anchor 全字段（含 coverage、
is_primary、locator）逐项 exact，对当前 bundle 的 document/chunker/progress/hash/parser/
normalize/config/payload 字段另行显式断言。重放双栏样本证明 matcher 参数顺序修复了
`b2/chunk0=0.018386` 与 `b1/chunk1=0.710269` 的冻结数值；未修改 fixtures/expected。
Task02A 不读取或写入 Qdrant，bundle 只输出 `chunk_snapshot_fingerprint`；真实
`index_fingerprint` 延后由后续索引任务计算。

`pdf-no-text-layer` 保留 `failed/PDF_NO_TEXT`，不产生伪 chunks/anchors；
`markdown-hostile` 保留 `partial/HOSTILE_MARKDOWN_REQUIRES_SANITIZER_PROBE`，其 blocks、
resources、diagnostics 来自正式 Markdown DTO。浏览器 PDF.js 零网络门继续留给 Task05。

## 产物与验证

- Schema：`docs/sdd/plans/018/artifacts/task-02a/source-provenance-bundle.schema.json`
- 测试：`tests/test_kb_source_provenance_bundle.py`
- 生产组装层：`backend/app/knowledge_base/infrastructure/provenance.py`
- 最小兼容层：`backend/app/knowledge_base/infrastructure/chunkers.py`
- 日志：`.codebuddy/agent-logs/spec-018/task-02a/backend-dev/20260909-012838+0800.md`（首轮），
  `.codebuddy/agent-logs/spec-018/task-02a/backend-dev/20260909-015133+0800.md`（本轮修订）

已完成：

- `./.venv/bin/python -m pytest -q tests/test_kb_source_provenance_bundle.py`：退出码 0，16 passed，5 个既有 PyMuPDF warning；覆盖完整 anchor exact、重复文本 overlap、合法空 LLM 响应、null page/line locator、schema malformed locator，以及真实 Markdown DTO 经 public builder 的 block/chunk/anchor serialized exact/+1。
- `./.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_legacy_kb_integration.py`：退出码 0，262 passed、29 subtests passed、5 个既有 PyMuPDF/OTEL 相关 warning；新增 bundle/consumer 用例计入总数，既有业务行为未回归。
- `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/provenance.py tests/test_kb_source_provenance_bundle.py`：退出码 0。
- 修改/新增核心文件的 Ruff 检查 `provenance.py` + `test_kb_source_provenance_bundle.py`：退出码 0；全量 Ruff 仍报告既有 normalize/retrieve/tests 风格项，未因本轮功能改动新增业务错误。
- Draft 2020-12 `Draft202012Validator.check_schema`：退出码 0；`x-max-serialized-bytes` 仍仅为注解，runtime canonical UTF-8 检查为真正容量硬门。
- `git diff --check`：退出码 0。
- bundle schema SHA-256：`8aa5dfa8a32ef1604a7d505698fd509d5f50994b3faaea1c3ce7919bba78b669`；首轮 PDF/Markdown fixture 与 expected SHA-256 未变化（见 Task02 fixture-index/report）。本轮复核的 two-column expected/PDF SHA-256 分别为 `418a558b78e24cb2bf8e400b868cbdea34bbfe4aa3236c9bdc21ddb2575322c0` / `33726da69e2c79bd5b3d4fe10dc14a2b64760802151b4af97b97f4bb84e99e7d`。

所有定向、组合、KB 回归、schema/py_compile/diff 门禁及首轮 hash 复核均已完成；全量 Ruff 的既有风格项单独记录，不作为本轮功能阻塞。

## 交接与风险

- 主 Agent 后续应让 backend-reviewer 复核 SourceProvenanceBundle schema、coverage/primary
  算法、旧 expected projection 的分层说明，并由 Task02B 只读重放四个正常样本裁决严格
  `GO|NO-GO`。
- Markdown chunk payload 在有来源 anchor 时聚合 `start_line/end_line`，所有检索/prompt/
  citation 消费保留 page null 并显示 `行 X–Y`；RRF/reranker 仍不按页参与。
- 本轮未修改 parse.py、markdown.py、任何 fixture/expected、首轮 schema/NO-GO、index、
  API、frontend、data/kb、真实 Qdrant 或 Git。
- 未执行 embedding、Qdrant 写入、删除或持久化 manifest。

## 本轮修订日志

- coverage 使用冻结 oracle 的 chunk-first deterministic matcher；测试恢复完整 anchor dict exact。
- `detect_citation` 对 Markdown `page=None` fail-safe；`Hit`/payload/citation 保留可空页码和
  行范围；合法 LLM `[]` 记为成功使用；bundle fingerprint 改名为
  `chunk_snapshot_fingerprint`。
- Schema 增加 PDF/Markdown locator `$defs`、媒体条件、数量上限和 UTF-8 字节注解；生产组装
  在 chunk 前后对 block/chunk/anchor 数量与 block/chunk 字节容量 fail-closed，并使用同一
  canonical、键排序、无空白 JSON 的 UTF-8 序列化对单 block ≤2 MiB、单 chunk ≤512 KiB、
  单 anchor ≤4 KiB、完整 bundle ≤256 MiB 执行 runtime hard gate；schema `x-*` 只作注解。
  本轮进一步将 `pdfBlock`/`markdownBlock` 的正式 `to_dict()` 字段完整列出并设
  `additionalProperties=false`，分别声明 `x-max-serialized-bytes=2097152`；chunk 声明
  `524288`，anchor 保持 `4096`，PDF/Markdown locator 仍由媒体条件严格约束。
  超限稳定码分别为 `PROVENANCE_BUNDLE_BLOCK_SERIALIZED_TOO_LARGE`、
  `PROVENANCE_BUNDLE_CHUNK_SERIALIZED_TOO_LARGE`、
  `PROVENANCE_BUNDLE_ANCHOR_SERIALIZED_TOO_LARGE`、
  `PROVENANCE_BUNDLE_SERIALIZED_TOO_LARGE`，canonical 非 JSON 值为
  `PROVENANCE_BUNDLE_SERIALIZATION_FAILED`。边界等于上限接受，+1 拒绝；per-item 边界测试
  均通过真实 `MarkdownBlockProvenanceV1` / `MarkdownSourceProvenanceV1` → public
  `build_source_provenance_bundle`，未调用私有 helper、未 monkeypatch 容量函数、未注入最终
  bundle。完整 bundle 由真实 `SourceProvenanceBundleV1` 调用公开
  `validate_source_provenance_bundle`，使用纯 canonical size accumulator 覆盖 256 MiB/+1，
  无需分配 256 MiB 测试对象。
- 本轮日志：`.codebuddy/agent-logs/spec-018/task-02a/backend-dev/20260909-015133+0800.md`（前轮），
  `.codebuddy/agent-logs/spec-018/task-02a/backend-dev/20260909-021453+0800.md`（容量修订），
  `.codebuddy/agent-logs/spec-018/task-02a/backend-dev/20260909-022537+0800.md`（本轮 schema 与 public-path 边界修订）。
