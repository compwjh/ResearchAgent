# Spec018 Task02A-C SourceProvenanceBundle backend review

日期：2026-09-09

角色：Task02A-C backend-reviewer

模型：gpt-5.6-luna xhigh（仅本轮）

范围：只读评审 `backend/app/knowledge_base/infrastructure/provenance.py`、`chunkers.py`、`tests/test_kb_source_provenance_bundle.py`、`source-provenance-bundle.schema.json`、`chunker-integration-report.md`，并对照 Spec018、Task02A/02B、首轮 expected/schema、正式 `parse.py`/`markdown.py` 与现有 `index.py`/`retrieve.py`/`prompts.py` 消费者。本轮未修改业务代码、fixtures、expected 或首轮报告。

进展日志：[20260909-014338.md](../../../../../.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260909-014338.md)

## 验证命令

- `./.venv/bin/python -m pytest -q tests/test_kb_source_provenance_bundle.py tests/test_kb_chunkers.py tests/test_kb_pdf_provenance.py tests/test_kb_markdown_provenance.py`：`81 passed`，5 个既有 PyMuPDF warnings。
- 直接用正式 parser + `build_source_provenance_bundle()` 重放四个正常样本；结果显示 block/chunk/anchor identity、locator、primary、v2 跨页、Markdown null page/line locator 对齐，但 two-column coverage 存在冻结契约差异。
- 直接消费者复现：`Chunk(page=None)` 的 `detect_citation` 在有 `ref_start_page` 时抛 `TypeError`；null Qdrant payload 经 `_to_hit`/prompt/citation 输出页码 0。

## 已通过的边界

### 复用与范围

- `provenance.py:16-24,205-254` 复用既有 v1/v2 chunker 和正式 normalize/parser DTO；未发现第三套切片器、manifest 持久化、embedding、Qdrant 或新的 index pipeline。
- `chunkers.py:89-105` 保留既有 PDF page/page_end 行为，并使 Markdown `page=None` 时 `page_end=None`；`provenance.py:257-265` 不把 null 转成 0。
- 正常样本的 block/chunk/anchor identity、locator、primary 集合，PDF v2 跨页 `page=1/page_end=2`，Markdown block-preserving chunks 与一对一 line locator 均能由正式入口生成。

### Bundle 结构基础

- `SourceProvenanceBundleV1.to_dict()`（`provenance.py:82-114`）固定 `source-provenance-bundle-v1`/`source-anchor-v1`，并包含 source hash、parser/normalize version、chunker config fingerprint、payload schema、状态、blocks/chunks/anchors、mapping counts 和 v2 diagnostics。
- Schema 顶层 required、source SHA-256 pattern、chunker config/index fingerprint pattern、`llm_used`/degradation diagnostics 约束存在；schema hash 为 `ee20377089d58213a90118aa742e4096d113d48e8dfe0e593cd2cd4ae358d2a3`。
- 四个正常 fixture、expected 与首轮证据未被本轮修改；two-column expected SHA-256 为 `418a558b78e24cb2bf8e400b868cbdea34bbfe4aa3236c9bdc21ddb2575322c0`，PDF SHA-256 为 `33726da69e2c79bd5b3d4fe10dc14a2b64760802151b4af97b97f4bb84e99e7d`。

## 阻塞问题

### P0：two-column frozen coverage 被测试主动剥离，违反 Spec/Task02B 全集合硬门

**证据**

- Spec018 要求每个 expected 至少断言完整 anchor 对、`coverage`、`is_primary`，正常 PDF/Markdown 的 expected block/chunk/anchor 集合必须 100% 匹配（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:338-343`）。Task02B 对正常 PDF 同样规定 block/chunk/anchor 集合 100% 匹配（`docs/sdd/plans/018/task-02b-revalidate-source-anchor-feasibility.md:70-74`）。
- Formal mapper 在 `backend/app/knowledge_base/infrastructure/provenance.py:137-143,297-317` 以 NFKC/换行/水平空白归一化后的 `SequenceMatcher` overlap 计算 coverage。
- `pdf-two-column-v1-overlap` 正式重放差异：`b2/chunk0` 实际 `0.024515` vs frozen expected `0.018386`（`docs/sdd/fixtures/spec-018/pdf-two-column-v1-overlap.expected.json:5691`）；`b1/chunk1` 实际 `0.707824` vs frozen expected `0.710269`（`:5733`）。anchor identity/locator/primary 相同，但 coverage 数值不相同。
- 测试 helper `tests/test_kb_source_provenance_bundle.py:52-61` 明确从 anchor 中删除 `coverage` 再比较，只检查 `0.0 <= coverage <= 1.0`。因此 `8 passed` 不能证明 frozen coverage 契约通过。
- 开发报告 `docs/sdd/plans/018/artifacts/task-02a/chunker-integration-report.md:60-63` 将差异称为历史 incidental-match，但未有 Spec 重新冻结或 Tech Lead 批准证据；不能单方面降级为非契约字段。

**影响**

Task02B 的严格 Go/No-Go 无法由当前测试证明。coverage 是用户联动的 primary 排序和映射率证据；双栏样本是专门用于重叠与多对多映射的冻结样本，忽略数值会掩盖算法漂移，属于来源锚点硬门失败。

**修改建议**

1. 优先修正 mapper/规范化/coverage 算法，使 two-column 的所有 coverage 与冻结 expected 完全一致，并将测试恢复为完整 anchor dict exact。
2. 若确认冻结数值是旧算法错误，必须保留首轮证据只读，按 SDD 更新 Spec/Task02B、生成新的正式 expected/schema/hash 并重新完成需求/技术评审；不得只在测试中排除 `coverage`。
3. 补充显式 coverage mismatch 回归用例，包含多对多、重复文本 tie-break、primary 唯一性和 unmapped reason。

### P1：`Chunk.page=None` 未被所有既有消费者安全消费，存在 TypeError 和伪造第 0 页

**证据**

- `chunkers.py:89-100` 允许并保留 `Chunk.page=None/page_end=None`。
- `normalize.py:139-149` 的 `detect_citation` 将 page 与 `ref_start_page` 比较；`index.py:133-140` 在 `ref_start_page` 存在时直接传入 `chunk.page`。实测 Markdown 形状触发：`TypeError: '<' not supported between instances of 'NoneType' and 'int'`。
- `retrieve.py:89-102` 将 null payload 转成 `page=0/page_end=0`；`prompts.py:6-19,35-47` 随后输出“第 0 页”和 page 0 citation。Spec018 明确禁止把 Markdown null page 猜成页码 0（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:196,204`）。

**修改建议**

让 citation 检测对 null page fail-safe（不判 citation 或使用 Markdown 行范围），让 Hit/prompt/citation DTO 保留 `Optional[int]` 并在无页码时输出行 locator/受控“无页码”状态；补从 Markdown bundle 到 retrieve/RRF/reranker/prompt/citation 的 null-page contract test。若这些消费者属于 Task04，必须在 Task02B handoff 标记为阻塞而不是宣称当前 null-page contract 已闭合。

### P1：v2 `llm_used` 对成功的空边界响应不真实，降级诊断会伪报

**证据**

- `chunkers.py:289-321` 的 `_judge_by_llm` 只有解析出至少一个边界才将 `used=True`；LLM 成功返回合法 `[]` 时返回 false。
- `provenance.py:244-253` 将 false 统一转成 `V2_RULES_ONLY_LLM_NOT_USED`。因此“LLM 已调用但没有新增边界”与“LLM 不可用/解析失败”被混为一谈。
- 现有 `tests/test_kb_chunkers.py:168-179` 对 `[]`/不可解析只断言仍有 chunks，没有断言 llm_used 或 degradation diagnostics；bundle test 仅覆盖无 LLM 的规则路径（`tests/test_kb_source_provenance_bundle.py:100-105`）。

**修改建议**

区分 `llm_called_successfully` 与 `boundaries_added`：合法 `[]` 应保留 `llm_used=true` 且不产生“未使用/降级”诊断；异常、超时、非空但不可解析的回复才返回 `llm_used=false` 和稳定 fallback diagnostic。若产品坚持“used”只代表产生新边界，则需改名/新增字段并同步 schema、Spec、报告和测试，不能继续使用当前含义。

### P1：fingerprint 与 expected metadata 的语义未冻结/测试未覆盖

**证据**

- Spec018 定义 `index_fingerprint` 为从 Qdrant 实际 payload 全部切片快照按 `(chunker,chunk_index)` canonical 后计算（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:126,343`）。当前 `provenance.py:372` 只对本地 `chunk_payloads` 计算，未包含实际 Qdrant payload 或其验证结果；Task02A 又明确禁止 Qdrant 写入/访问（`chunker-integration-report.md:10-17,94-96`）。
- `_assert_expected_projection`（`tests/test_kb_source_provenance_bundle.py:38-64`）未比较 expected 的 `document_id`、`chunker`、`progress`、`source_hash_state`、`source_parser_version`、`normalize_version` 等 Spec 列明字段。实际值与首轮 expected 已可见差异：`source_hash_state` 为 `verified` vs `verified_fixture`，PDF parser/normalize version 也不同；测试不会暴露这种交接变化。

**修改建议**

明确 Task02A bundle 的 pre-index fingerprint 字段名称/算法，或把 actual-Qdrant `index_fingerprint` 延后由 Task03/04 生成并在 bundle schema 中删除/标注；对允许继承的首轮字段建立显式 projection，逐字段断言 `document_id/chunker/progress/status/hash/parser/normalize/config/payload/index`，并把任何 intentional re-baseline 写进 Spec/expected hash 变更记录。

### P2：bundle schema 对嵌套 DTO 和容量边界过于宽松

- `source-provenance-bundle.schema.json:58-72,90-103` 对 pages、blocks 和 locator 允许任意对象/额外字段，未冻结 PDF/Markdown locator 的最小结构；chunks/anchors 也没有 Spec 规定的数量与字节上限（Spec018:265）。
- 建议补 `$defs`、media-type conditional locator、`maxItems`/文本字节门禁（或明确 parser 已执行且 schema 使用专用 byte annotation），并为 malformed locator/oversized bundle 增加 fail-closed tests。

## 严格结论

**FAIL。**

当前实现确实复用了正式 parser/v1/v2、保持了 Markdown null page 产物、v2 跨页和多数 anchor identity/primary 关系，也没有新增 manifest/embedding/Qdrant/第三套 chunker；但 two-column frozen coverage 与正式 mapper 不一致，测试主动忽略 coverage，直接违反 Spec018/Task02B 的 anchor 全集合硬门。与此同时，既有消费者对 `page=None` 会 TypeError 或伪造第 0 页，v2 成功空响应的 `llm_used`/降级诊断不真实，fingerprint/metadata 投影也未完全冻结。修复或按 SDD 重新冻结并复审前，Task02A-C 不得进入 Task02B 严格 GO。

## 最终复审（最新修订，2026-09-09）

> 评审角色：Task02A-C backend-reviewer ｜ 模型：gpt-5.6-luna xhigh（仅本轮） ｜ 时间：2026-09-09 02:07 +0800
>
> 进展日志：[20260909-020713.md](../../../../../.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260909-020713.md)

### 已关闭项

| 首轮问题 | 最新结论 | 证据 |
|---|---|---|
| four normal fixture anchor exact | **关闭** | `tests/test_kb_source_provenance_bundle.py:62` 直接比较完整 `actual["anchors"] == expected["anchors"]`，不再剥离 coverage；四样本正式重放通过。 |
| coverage 公式/冻结 oracle | **关闭** | `provenance.py:142-151,358-377` 使用 chunk-first deterministic matcher；two-column coverage `0.018386/0.710269` 与 frozen expected 一致；重复文本 primary 唯一且稳定。 |
| `page=None` 全链路与 PDF 回归 | **关闭** | `chunkers.py:95-105`、`normalize.py:139-154`、`retrieve.py:68-116`、`prompts.py:6-68` 保留 null 并使用 line range；相关消费者和 PDF tests 全部通过。 |
| LLM 合法 `[]`、异常/非法与部分失败 | **关闭** | `chunkers.py:289-324,443-468` 区分合法空列表与失败；bundle/test 在 `tests/test_kb_source_provenance_bundle.py:185-197`、`tests/test_kb_chunkers.py:168-203` 覆盖 used/no-degradation、异常和无部分边界。 |
| Qdrant fingerprint 语义 | **关闭** | bundle 仅输出 `chunk_snapshot_fingerprint`（`provenance.py:81,111,440`），schema/report/test 均移除 `index_fingerprint`；真实 Qdrant fingerprint 延后下游索引任务。 |
| metadata projection | **关闭** | `tests/test_kb_source_provenance_bundle.py:39-65,99-103` 显式断言 document/chunker/status/progress/hash/parser/normalize/config/payload/snapshot 等字段。 |
| locator/count/text 基础 schema/容量 | **关闭** | schema `:17-221` 有 PDF/Markdown locator、媒体条件、maxItems、text byte annotations；runtime `provenance.py:299-326` fail-closed 检查 block/chunk/anchor 数量和 block/chunk UTF-8 text bytes。 |

### P1：单 DTO/整体序列化容量仍未 fail-closed

**证据**

- Spec018:265 冻结了单 block DTO ≤2 MiB、单 chunk DTO ≤512 KiB、单 anchor DTO ≤4 KiB、bundle JSON ≤256 MiB；这些是领域对象硬容量，不只是文本/数组数量限制。
- schema 的 `x-max-serialized-bytes` 位于 root/数组/anchor 注解（`source-provenance-bundle.schema.json:6,133,175,181,187`），JSON Schema Draft 2020-12 validator 不会执行这些自定义注解；单 `pdfBlock`/`markdownBlock`/`chunk` `$defs` 没有对应的 serialized-byte assertion，且 block 允许 `additionalProperties:true`（`:63-101`）。
- `provenance.py:299-326` 仅检查 block/chunk 文本 UTF-8 bytes以及数量，没有计算 block/chunk/anchor/canonical bundle 的序列化字节数。
- 可复现 synthetic DTO：text 只有 1 字符、额外 block 字段约 3 MiB；builder 成功、Draft validator 无错误，block JSON 约 3 MiB，超过 Spec 单 block DTO 2 MiB。这证明当前 schema/assembly 仍可接受超限 DTO。

**修改建议**

1. 在 assembly 入口使用与交接一致的 canonical UTF-8 JSON 序列化，对每个 block/chunk/anchor 和最终 bundle 分别执行 2 MiB/512 KiB/4 KiB/256 MiB fail-closed 检查，返回稳定容量错误码并避免先生成超大对象。
2. 将每个 `$defs` 的 allowed fields/serialized limit 明确冻结；若保留扩展字段，至少对其计入对象字节预算并增加超限 committed tests。
3. schema 的 `x-max-serialized-bytes` 可保留作为机器可读声明，但报告必须明确真正硬门由 runtime validator 执行；不能把 Draft validator 通过当作容量通过。

### 验证结果

- `./.venv/bin/python -m pytest -q tests/test_kb_source_provenance_bundle.py tests/test_kb_chunkers.py tests/test_kb_normalize.py tests/test_kb_services.py`：`144 passed`、4 subtests、5 个既有 PyMuPDF warnings。
- `./.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_legacy_kb_integration.py`：`258 passed`、29 subtests、5 个既有 PyMuPDF/OTEL warnings。
- `py_compile`、`git diff --check`、限定 `ruff check provenance.py tests/test_kb_source_provenance_bundle.py`：通过。工作树中其他历史风格诊断不影响本轮功能验证。
- bundle schema SHA-256：`d01098a9709f74472b4c49e4b7af6bb98538f136f4855109cf9ffc22b9438b8e`；四份正常 fixture/expected 原始 hash 未变。

### 严格结论

**FAIL（P1 容量/Schema fail-closed 门禁）。**

本轮已关闭首次 FAIL 的 coverage、anchor、page-null、LLM、fingerprint、metadata 和嵌套 locator/数量/文本容量问题；但 Spec 冻结的单 DTO 与整体序列化字节上限仍只是 annotation，且 assembly 没有对应硬检查。补齐该容量门禁及 committed tests，或按 SDD 显式修订容量契约后，才能升级为 PASS。

## 最终复审（容量门禁修订，2026-09-09）

> 评审角色：Task02A-C backend-reviewer ｜ 模型：gpt-5.6-luna xhigh（仅本轮） ｜ 时间：2026-09-09 02:22 +0800
>
> 进展日志：[20260909-022250.md](../../../../../.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260909-022250.md)

### 已关闭

| 检查项 | 结论 | 证据 |
|---|---|---|
| canonical UTF-8 runtime 计数 | **关闭** | `provenance.py:129-156` 使用 `ensure_ascii=false`、键排序、无空白、`allow_nan=false` 的 JSON，再按 UTF-8 bytes 计数；`provenance.py:355-377,451-467` 在 assembly 前后执行 block/chunk/anchor 门禁，`provenance.py:499-503` 执行 bundle 门禁。 |
| block exact/+1 | **关闭（实现）** | 真实 Markdown block DTO 重放：2,097,152 bytes 接受，2,097,153 bytes 返回 `PROVENANCE_BUNDLE_BLOCK_SERIALIZED_TOO_LARGE`；不是仅 schema validator 结果。 |
| 非 JSON 稳定失败 | **关闭（实现）** | `object()`、NaN、set 等值经 `_serialized_utf8_size` 返回脱敏稳定 `PROVENANCE_BUNDLE_SERIALIZATION_FAILED`（`provenance.py:143-151`），不泄露路径或原始异常。 |
| 此前修订无回归 | **关闭** | 定向测试 `148 passed`；KB 回归 `262 passed, 29 subtests`；py_compile、`git diff --check` 通过；四个 normal fixture/expected 及 anchor exact 仍通过。 |

### P1：schema 注解与 runtime per-item 契约不一致

**证据：**

- runtime 明确冻结 block/chunk/anchor/bundle 四个不同上限（`provenance.py:47-50`）。
- schema 只在 root `:6`、blocks/chunks/anchors 数组 `:175,181,187` 声明 256 MiB，在 `anchor` `$defs` `:133` 声明 4 KiB；`pdfBlock`/`markdownBlock` `$defs` `:63-101` 没有 2 MiB 注解，`chunk` `$defs` `:102-116` 没有 512 KiB 注解。
- `pdfBlock` 与 `markdownBlock` 仍为 `additionalProperties:true`（`:83,100`）。因此 Draft 2020-12 validator 既不会执行 `x-*`，schema 也没有向下游声明单 block/单 chunk 的硬预算；数组 256 MiB 不能替代 per-item 2 MiB/512 KiB。

**修改建议：** 在 `pdfBlock`、`markdownBlock`、`chunk` `$defs` 分别补 `x-max-serialized-bytes: 2097152/524288`，并冻结允许字段或明确扩展字段仍计入 runtime 预算；保留 root 256 MiB 注解并在 schema/report 中说明这些 `x-*` 必须由 runtime validator 执行。

### P1：committed boundary tests 仍不能证明 builder 的真实 DTO/Bundle 路径

**证据：**

- `tests/test_kb_source_provenance_bundle.py:233-248` 直接调用私有 `_validate_serialized_capacity`，输入 `{"kind":..., "extra":...}` toy dict；这些对象不是 schema 中的 block/chunk/anchor DTO，故不能证明 builder 组装的实际 DTO 在 exact/+1 时拒绝。
- `tests/test_kb_source_provenance_bundle.py:251-265` monkeypatch `_serialized_utf8_size`，对 bundle 直接注入 `256 MiB + 1` 返回值。它能证明返回前存在调用，但没有验证真实 canonical serialization 的 exact/+1，也没有真实 bundle 256 MiB 边界。
- 当前 runtime 真实 block exact/+1 与非 JSON 复现均通过，但上述测试证据仍属于合成 helper/size 注入；不能满足本轮要求的“测试不靠伪造绕过生产校验”。

**修改建议：** 提交使用正式 parser DTO 和 `build_source_provenance_bundle` 的 block/chunk/anchor exact/+1 用例；为 bundle 增加真实 canonical UTF-8 boundary fixture，或实现受控的 canonical byte accumulator 并让测试调用同一生产路径，禁止 monkeypatch `_serialized_utf8_size` 代替边界证明。另补非 JSON DTO 的 builder-level committed test。

### 验证结果

- `./.venv/bin/python -m pytest -q tests/test_kb_source_provenance_bundle.py tests/test_kb_chunkers.py tests/test_kb_normalize.py tests/test_kb_services.py`：`148 passed`、4 subtests、5 个既有 PyMuPDF warnings。
- `./.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_legacy_kb_integration.py`：`262 passed`、29 subtests、5 个既有 PyMuPDF/OTEL warnings。
- `py_compile`、`git diff --check`：通过。

### 严格结论

**FAIL（P1 schema/证据门禁）。**

本轮确认 runtime canonical UTF-8 检查、真实 block exact/+1 与非 JSON稳定错误已实现，且此前 coverage、page-null、LLM、fingerprint、metadata 等项无回归；但 SourceProvenanceBundle schema 没有声明 per-item block/chunk serialized limits，测试仍以 toy helper 与 monkeypatch 注入替代真实 builder/bundle boundary。补齐 schema 注解、正式 DTO/bundle boundary tests 后，才能升级为 PASS。

## 最终复审（schema/公开边界证据修订，2026-09-09）

> 评审角色：Task02A-C backend-reviewer ｜ 模型：gpt-5.6-luna xhigh（仅本轮） ｜ 时间：2026-09-09 02:36 +0800
>
> 进展日志：[20260909-023609.md](../../../../../.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260909-023609.md)

### 复核结果

| 门禁 | 结论 | 证据 |
|---|---|---|
| per-item 字节注解 | **通过** | schema `pdfBlock:65`、`markdownBlock:108` 为 `2097152`；`chunk:164` 为 `524288`；`anchor:182` 为 `4096`；均与 runtime `provenance.py:47-50` 一致。root 仍为 `268435456`（256 MiB）。 |
| DTO 字段封闭 | **通过** | `pdfBlock:104`、`markdownBlock:148`、`chunk:152`、`anchor:168` 均为 `additionalProperties:false`；正式 PDF/Markdown parser `to_dict()` 的实际字段逐项与 schema 对齐，真实 normal fixture 由 Draft 2020-12 validator 验证通过。 |
| block/chunk/anchor exact/+1 | **通过** | `tests/test_kb_source_provenance_bundle.py:281-363` 使用真实 `MarkdownBlockProvenanceV1`/`MarkdownSourceProvenanceV1` → 公开 `build_source_provenance_bundle`，不调用生产私有容量 helper、不 monkeypatch；三类均 exact 接受、+1 返回对应稳定错误码。 |
| bundle 256 MiB exact/+1 | **通过** | `tests/test_kb_source_provenance_bundle.py:366-379` 先由公开 builder 生成真实 `SourceProvenanceBundleV1`，再经公开 `validate_source_provenance_bundle` 使用其 documented canonical byte-count 输入验证 exact 接受、+1 返回 `PROVENANCE_BUNDLE_SERIALIZED_TOO_LARGE`；builder 默认路径（`provenance.py:535`）不接受外部 size，直接执行 canonical UTF-8 序列化。 |
| 非 JSON与此前修订 | **通过** | `_serialized_utf8_size`（`provenance.py:144-152`）仍将非 JSON/NaN/set 转为稳定 `PROVENANCE_BUNDLE_SERIALIZATION_FAILED`；coverage、page-null、LLM、fingerprint、metadata、PDF 回归均无变化。 |

### 验证结果

- `./.venv/bin/python -m pytest -q tests/test_kb_source_provenance_bundle.py tests/test_kb_chunkers.py tests/test_kb_normalize.py tests/test_kb_services.py`：`148 passed`、4 subtests、5 个既有 PyMuPDF warnings。
- `./.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_legacy_kb_integration.py`：`262 passed`、29 subtests、5 个既有 PyMuPDF/OTEL warnings。
- `Draft202012Validator.check_schema`：通过；schema SHA-256：`8aa5dfa8a32ef1604a7d505698fd509d5f50994b3faaea1c3ce7919bba78b669`。
- `ruff check provenance.py tests/test_kb_source_provenance_bundle.py`、`py_compile`、`git diff --check`：通过。
- 四份 normal fixture/expected、anchor exact 与首轮原件 hash 未改变。

### 严格结论

**PASS。**

本轮已关闭上一轮唯一 P1：schema 的 per-item serialized-byte 注解和字段封闭与正式 DTO 完全一致，block/chunk/anchor 的 exact/+1 已由真实 DTO 与公开 builder 覆盖，bundle 的 exact/+1 已由真实 `SourceProvenanceBundleV1` 与公开 validator 覆盖；runtime canonical UTF-8 hard gate 与稳定非 JSON 错误保持有效。Task02A-C backend review 可通过，允许交给 Task02B 进行只读 fixture 重放与总 Go/No-Go 裁决。
