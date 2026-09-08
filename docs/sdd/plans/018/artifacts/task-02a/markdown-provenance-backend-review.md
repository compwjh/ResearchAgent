# Spec018 Task02A-B Markdown provenance backend review

## 评审元数据

- 角色：Task02A-B backend-reviewer
- 模型：gpt-5.6-luna xhigh（仅本轮）
- 时间：2026-09-08 23:43–23:50 +0800
- 日志：[20260908-234339.md](../../../../../.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260908-234339.md)
- 范围：只读评审 `backend/app/knowledge_base/infrastructure/markdown.py`、`tests/test_kb_markdown_provenance.py`、`docs/sdd/plans/018/artifacts/task-02a/markdown-source-provenance.schema.json`、`markdown-provenance-report.md`，对照 Spec018、Task02A、首轮 Markdown fixtures/expected；未修改业务代码。

## 验证命令

- `./.venv/bin/python -m pytest -q tests/test_kb_markdown_provenance.py`：`11 passed`。
- `./.venv/bin/python -m pytest -q tests/test_kb_markdown_provenance.py tests/test_kb_normalize.py tests/test_kb_chunkers.py`：`64 passed`。
- `./.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_legacy_kb_integration.py`：`234 passed`、`29 subtests passed`；仅既有 PyMuPDF deprecation warnings，OTEL exporter 的本机 3000 连接重试与本 parser 无关。
- `./.venv/bin/ruff check backend/app/knowledge_base/infrastructure/markdown.py tests/test_kb_markdown_provenance.py`：通过。
- `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/markdown.py tests/test_kb_markdown_provenance.py`：通过。
- `git diff --check`：通过。
- 手动实际 block 边界：200,000 blocks accepted；200,001 返回 `MARKDOWN_BLOCK_LIMIT`。该命令只作复核证据，未替代 committed test。

## 已验证通过项

1. **原始字节与编码**：`markdown.py:202-238,476-495` 先对原始 bytes 计算 SHA-256，再剥离 UTF-8 BOM；非法 UTF-8/NUL 返回稳定 `INVALID_ENCODING`。`tests/test_kb_markdown_provenance.py:162-181` 覆盖 BOM、CRLF、CR、hash、非法编码与 NUL。
2. **LF 与定位**：`markdown.py:219-251,493-510` 将 CRLF/CR 统一为 LF，并以规范化文本计算 `start/end`；`locator.start_line/end_line` 为 1-based。fixture 与混合换行测试通过。
3. **块类型/heading path**：heading、连续 paragraph、list 续行/嵌套、GFM table、fenced code、blockquote、horizontal rule、HTML block 有实现与边界测试（`markdown.py:263-473`；`tests/test_kb_markdown_provenance.py:104-159`）。
4. **纯 DTO 边界**：schema `additionalProperties:false`，DTO 只有 parser 字段；`markdown.py:145-191` 未输出 chunks、anchors、indexed hash、bundle 或 manifest；block 的 `page/page_end` 为 JSON `null`（`markdown.py:125-142`）。
5. **图片/hostile 静态安全**：图片仅生成 `loadable=false` 元数据和 placeholder（`markdown.py:357-376`）；无 HTML 渲染、文件图片读取、网络或脚本执行路径。hostile 内容只产生诊断并返回 `partial`（`markdown.py:379-390,516-519`）；浏览器 DOMPurify/网络硬门正确留给 Task05。
6. **错误脱敏**：读取、编码、hash mismatch 错误为稳定 code，未把路径或第三方异常文本带入用户消息（`markdown.py:202-216,219-226,484-491`；测试 `:176-181,222-226`）。

## 阻塞问题

### P0：缺失 Spec/Plan 冻结的流式 50 MiB 与单 block 容量门禁

**证据**

- Spec018 明确要求 Markdown 上传按流累计，超过 50 MiB 立即终止（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:201,205,243`），并要求单 block 规范化 UTF-8 文本不超过 1 MiB（`:265`）。Plan P0-3 也冻结了“流式 50 MiB 上限”（`docs/sdd/plans/018/README.md:39`）。
- 生产 parser 的 `_read_source()` 对 Path 直接调用 `Path.read_bytes()`，bytes/memoryview/str 也整体复制（`backend/app/knowledge_base/infrastructure/markdown.py:202-216`）；不存在 source-byte 上限、流式 sentinel、单 block 字节上限或对应稳定容量错误码。
- 现有唯一数量限制只有 `_MAX_MARKDOWN_BLOCKS=200_000`（`:25,450-451`）。`tests/test_kb_markdown_provenance.py:184-202` 只测 100,000 字符长行和 monkeypatch 后的 block limit，不能证明 50 MiB/1 MiB 契约。

**影响**

任意超大 Path/raw bytes 可在 hash、decode、normalized text、line list 和 block DTO 中同时占用内存；调用 parser 的重建路径可绕过上传层的 50 MiB 检查。单一超长 block 也可超过 Spec 的 1 MiB DTO 预算。不能据此保证容量拒绝、稳定 413/`PAYLOAD_TOO_LARGE` 或不留半截资源。

**修改建议**

统一由 parser/application 共享受控读取器：Path/文件流最多读 `50 MiB + 1` sentinel，超过即停止并返回稳定 `PAYLOAD_TOO_LARGE`（或明确的 parser code 并在 API 映射为 413）；对规范化 block UTF-8 字节数实施 `1 MiB` 上限，返回稳定 `PAYLOAD_TOO_LARGE`/`MARKDOWN_BLOCK_TOO_LARGE`。补 50 MiB、50 MiB+1、单 block 1 MiB、1 MiB+1、raw bytes/path 两种入口的 committed tests，确保 hash/normalize 前即 fail-closed。

### P1：空文档行为与 Spec 冲突，且缺稳定错误码

**证据**

- Spec018 边界条款要求“空文件……拒绝且不留下半截记录”（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:310`）。
- 当前实现对空输入执行 `_decode_and_normalize` 后构造空 blocks，并返回 `status="ready"`（`markdown.py:493-529`）；测试还把该行为固化为通过（`tests/test_kb_markdown_provenance.py:184-188`）。
- 当前常量集合没有 `EMPTY_MARKDOWN`/等价空源错误码（`markdown.py:29-35`）。

**影响**

空 Markdown 可能进入后续索引/manifest 流程并被标为 ready，与上传拒绝和“不得生成虚假清单”契约冲突。

**修改建议**

明确 parser 与 upload/application 的单一边界：若 parser 是生产唯一事实源，则空 bytes/规范化后空文本统一返回稳定 `EMPTY_MARKDOWN`（API 映射 400），并将测试改为拒绝；若空 DTO 确实有意允许，则必须修订 Spec018:310、上传错误契约和 Task02A 报告，不能由测试私自选择相反语义。

### P1：首轮 expected 与正式 DTO 的投影没有冻结，测试存在伪通过

**证据**

- `tests/test_kb_markdown_provenance.py:36-73` 只比较 `markdown-blocks` 的 hash、状态、block type、line range、字符范围和 page null，没有逐字段比较 `text`、`heading_path`、diagnostics、resource、block_id 或 normalized text 与 expected。
- `tests/test_kb_markdown_provenance.py:76-101` 对 hostile 只断言行号、状态、图片不可加载和一条诊断，同样没有比较 block type/text/heading path。
- 直接将当前纯 DTO 与首轮 `docs/sdd/fixtures/spec-018/markdown-hostile.expected.json` 对照时，前两个实际 `block_type` 为 `html`，首轮 expected 为 `paragraph`；当前测试不会失败。首轮 expected 还包含 `provenance-dto-v1` 的 bundle/chunk/anchor 字段，而 Task02A 新 schema 是纯 `markdown-source-provenance-v1`，两者不能静默视为同一 DTO。

**影响**

测试全绿并不证明正式 parser 对首轮 expected 的 block 集合/类型/文本完全兼容；下游 Task02B 可能在未决的 hostile HTML 分类或旧 bundle→纯 DTO 投影上产生契约冲突。

**修改建议**

保留首轮 expected/NO-GO 只读不改写，并新增独立的 Task02A pure-parser expected/projection fixture，明确哪些字段继承、哪些 bundle 字段留给 02A-C；测试逐块 exact 比较 `text/block_type/heading_path/start/end/start_line/end_line/page/page_end/resources/diagnostics`。若 hostile `<script>/<div>` 必须保持 `paragraph`，修正 parser；若按 CommonMark 归类为 `html`，将该投影决策和 Task02B oracle 明确落盘。

## 非阻塞测试覆盖缺口

- `tests/test_kb_markdown_provenance.py:197-202` 将 `_MAX_MARKDOWN_BLOCKS` 临时改为 2，未提交真实 200,000 accepted / 200,001 rejected 用例；本轮手动复现通过，但应加入 committed boundary test。
- 长行只覆盖 100,000 字符（`:190-194`），没有 Spec 要求的单 block 1 MiB boundary；该缺口与 P0 容量门禁共同修复。
- 未覆盖 `source_sha256` 非字符串参数的稳定错误边界（`:487-491` 直接调用 `.lower()`）；若该函数直接暴露给 API，应补 `SOURCE_HASH_INVALID`，避免 `AttributeError`。

## 首轮证据与报告一致性

- 当前四个 Markdown fixture/expected 与 Task02A schema SHA-256 与 `markdown-provenance-report.md:36-42` 一致：
  - `markdown-blocks.md`: `0b19f1dc1a3bd687b2b9f369ce6c93998648d4f7b6c976d1ed87a78b41325e97`
  - `markdown-blocks.expected.json`: `d7847f4089d88f4c5f989073eac2a3a048471a05986c3531deb694e782b2b22c`
  - `markdown-hostile.md`: `8adfb117879523e8858d9346307cfcfce94eb8b71d144c7453802b2973cf9f32`
  - `markdown-hostile.expected.json`: `caae72931d25d856453ece2134c9af6ae41da3a7dd076b553b9ad0b87293a059`
  - `markdown-source-provenance.schema.json`: `ec6a2bc48c4d964807842500828d078e0c644925dee0bb6302b7276d5bbc0bd3`
- 未修改首轮 fixture、expected、fixture index、NO-GO 报告或业务代码。

## 严格结论

**FAIL。**

UTF-8/BOM/NUL/hash、换行归一化、行号/offset、heading/block 覆盖、`page/page_end=null`、纯 DTO 边界及静态 hostile 不执行证据基本成立；但缺失冻结的流式 50 MiB/单 block 容量门禁、空文件拒绝契约冲突，以及首轮 expected 投影的测试伪通过，均需修订后重新复审。Task02A-B 当前不得作为 Task02B 的无条件输入。

## 最终复审（2026-09-08）

> 评审角色：Task02A-B backend-reviewer ｜ 模型：gpt-5.6-luna xhigh（仅本轮） ｜ 时间：2026-09-08 23:55–00:02 +0800
>
> 进展日志：[20260908-235538.md](../../../../../.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260908-235538.md)

### 复审命令与事实

- `./.venv/bin/python -m pytest -q tests/test_kb_markdown_provenance.py`：`17 passed`。
- `./.venv/bin/python -m pytest -q tests/test_kb_markdown_provenance.py tests/test_kb_normalize.py tests/test_kb_chunkers.py`：`70 passed`。
- `./.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_legacy_kb_integration.py`：`240 passed`、`29 subtests passed`；仅已有 PyMuPDF deprecation warnings，OTEL exporter 的本机 3000 连接重试与本 parser 无关。
- Ruff、`py_compile`、`git diff --check` 均通过。
- 首轮四份 Markdown fixture/expected 与 Task02A schema hash 未变：`markdown-blocks.md` `0b19f1dc…25e97`、`markdown-blocks.expected.json` `d7847f40…b22c`、`markdown-hostile.md` `8adfb117…f32`、`markdown-hostile.expected.json` `caae7293…a059`、schema `761e6507…7ff32`；完整 hash 见上一轮报告与交付报告。

### 首轮 FAIL 关闭矩阵

| 首轮问题 | 复审结论 | 证据 |
|---|---|---|
| 流式 50MiB sentinel | **部分关闭** | `_read_stream` 对 Path/stream 按 1MiB chunk 读取并以 `MAX+1` sentinel 拒绝（`markdown.py:211-228,238-247`）；bytes 入口也检查长度（`:234-237`）。但 raw `str` 入口 `:248-253` 直接 encode，不检查 50MiB。 |
| 单 block 1MiB 稳定错误 | **关闭** | parser 按 `len(text.encode("utf-8"))` 检查并返回 `MARKDOWN_BLOCK_TOO_LARGE`（`markdown.py:543-547`）；1MiB/1MiB+1 测试（`tests/test_kb_markdown_provenance.py:203-211`）通过。 |
| 空/BOM/空白拒绝 | **关闭** | `markdown.py:537-539` 统一返回 `MARKDOWN_PARSE_FAILED`；测试 `:196-200` 覆盖三类输入。 |
| 两份 expected blocks 与 hostile/HTML 分类 | **expected 字段关闭，纯 DTO 仍有测试边界** | helper `tests/test_kb_markdown_provenance.py:37-42` 现在逐 expected-key 比较；hostile single-line `<script>/<div>` 为 expected `paragraph`，多行 `<section>` 由 `markdown.py:326-327,481-483` 归类 `html`，相关测试通过。见 P1-2：helper 并未比较 expected 未包含的纯 DTO 字段。 |

### 阻塞问题

#### P0-1：raw `str` 入口绕过真正的 50MiB 上限

**证据：** `extract_markdown_provenance` 的公开 `source` 类型包含 `str`（`markdown.py:518-523`）；`_read_source` 对 `str` 直接 `source.encode("utf-8")`（`:248-253`），没有 `_MAX_MARKDOWN_BYTES` 判断。复现：`_read_source("a" * (50*1024*1024+1))` 返回长度 `52,428,801`，而上限为 `52,428,800`。这与 Path/stream/bytes 的 sentinel 行为不一致。

**影响：** 生产调用方只要传入 raw Markdown 字符串，即可绕过 Spec/Plan 的 50MiB 源输入容量门禁，后续 hash/decode/normalize 继续处理超限数据。该入口不是仅测试 API，而是 parser 明确支持的输入形状。

**修改建议：** 对 raw `str` 在 encode 后立即检查字节长度并返回 `PAYLOAD_TOO_LARGE`，或移除公开 str 入口、强制调用方使用受控 binary stream；补 `str` 入口 50MiB 与 50MiB+1 committed test，并保证所有入口共享同一错误码/限额。

#### P1-1：JSON Schema `maxLength` 与 parser 的 UTF-8 字节上限语义不一致

**证据：** parser 使用 `len(text.encode("utf-8")) > 1MiB`（`markdown.py:543-547`），但 schema 只写 `"text": {"type":"string","maxLength":1048576}`（`markdown-source-provenance.schema.json:79-81`）。JSON Schema `maxLength` 按 Unicode code point 计数，不按 UTF-8 bytes；复现构造 600,000 个汉字（1,800,000 UTF-8 bytes）时，真实 `Draft202012Validator` 对 schema 报告 0 个错误，而 parser 按 byte cap 应拒绝。

**影响：** “机器校验通过”可能接受超过 1MiB 的 UTF-8 block，无法作为 Spec 的序列化/容量门禁；ASCII 样本会掩盖多字节语言风险。

**修改建议：** 保留 parser 的 UTF-8 byte cap，并在 schema/交接契约中增加明确的 `x-maxUtf8Bytes: 1048576`（或等价专用 validator/fixture）；测试至少覆盖 1MiB ASCII、1MiB+1 ASCII、低于字符数但超过 1MiB bytes 的多字节文本，不能把 JSON Schema `maxLength` 单独宣称为 byte limit。若改成字符上限，需先修订 Spec 的“规范化 UTF-8 ≤1MiB bytes”语义。

#### P1-2：expected block “全字段 exact”仍是部分字段 exact，存在新 DTO 字段伪通过

**证据：** `_assert_expected_blocks` 使用 `{key: actual[key] for key in expected_block}`（`tests/test_kb_markdown_provenance.py:37-42`），因此只比较首轮 expected 已有字段。首轮 expected block 没有纯 DTO 新增的 `page`、`page_end`、`inline_resources`、`diagnostics`；测试虽单独断言部分 `page`/图片/诊断，但没有逐块 exact 比较这四项，也没有比较 top-level hostile `source_sha256` 与 expected。

**影响：** 测试可在 block text/type/heading/offset 与 expected 对齐时，通过错误的某个 block page/resource/diagnostic 语义；交接报告“全字段 exact”表述超出实际证据。当前实现对这些字段的结果看起来正确，但门禁仍可伪通过。

**修改建议：** 保留首轮 expected 只读；为 Task02A pure DTO 建立 projection/oracle，显式补齐并逐块比较 `page/page_end/inline_resources/diagnostics`，并断言 hostile source hash、status/error、metrics。若不修改首轮 expected，报告应准确称为“expected-defined fields exact”，不要称纯 DTO 全字段 exact。

### 已确认未回归项

- BOM/NUL/非法 UTF-8、原始 bytes hash、CRLF/CR→LF、1-based line 与规范化 `start/end` 均通过。
- heading、paragraph、list 续行/嵌套、GFM table、fenced code、blockquote、hr、single-line hostile 与 multiline HTML 边界均通过。
- 图片仅为 `loadable=false` metadata/placeholder；parser 无渲染、图片读取、网络或 JavaScript 执行路径。
- pure parser DTO 无 chunks/anchors/indexed hash/bundle/manifest；`page/page_end` 仍为 JSON `null`。
- source hash 非字符串输入已映射为 `SOURCE_HASH_INVALID`（`markdown.py:528-533`；测试 `tests/test_kb_markdown_provenance.py:289-292`）。

### 严格结论

**FAIL。**

空/BOM/空白、Path/stream/bytes 50MiB sentinel、单 block 1MiB 错误、expected-defined block 字段、hostile 单行分类和多行 HTML 覆盖已改善；但 raw `str` 仍可绕过 50MiB，schema `maxLength` 无法表达 UTF-8 byte 语义，且“全字段 exact”测试仍存在伪通过边界。修复上述问题并重新复审前，Task02A-B 不得作为 Task02B 的无条件输入。

## 第三轮最终复审（2026-09-09）

> 评审角色：Task02A-B backend-reviewer ｜ 模型：gpt-5.6-luna xhigh（仅本轮） ｜ 时间：2026-09-09 01:18 +0800
>
> 进展日志：[20260909-011839.md](../../../../../.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260909-011839.md)

### 复审范围与验证

- 本轮只读复核最新未提交的 `backend/app/knowledge_base/infrastructure/markdown.py`、`tests/test_kb_markdown_provenance.py`、Task02A-B schema/report 及冻结 Markdown fixtures；未修改业务代码或首轮证据。
- `./.venv/bin/python -m pytest -q tests/test_kb_markdown_provenance.py`：`19 passed`。
- `./.venv/bin/python -m pytest -q tests/test_kb_markdown_provenance.py tests/test_kb_normalize.py tests/test_kb_chunkers.py`：`72 passed`。
- `./.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_legacy_kb_integration.py`：`242 passed`、`29 subtests passed`、`5 warnings`；warnings 为既有 OTEL 本机 3000 连接重试，与 Markdown parser 无关。
- `py_compile`、Ruff、`git diff --check`：均通过。

### 上两轮 FAIL 项关闭矩阵

| 项目 | 本轮结论 | 证据 |
|---|---|---|
| raw `str` 50 MiB exact / +1 | **关闭** | `_read_source` 在 `markdown.py:248-256` 对 UTF-8 encoded bytes 执行同一 50 MiB 门禁；对应 exact/+1 测试 `tests/test_kb_markdown_provenance.py:308-315`。 |
| 单 block 1 MiB exact / +1 | **关闭** | parser 在 `markdown.py:546-550` 按 UTF-8 bytes 判定并返回稳定 `MARKDOWN_BLOCK_TOO_LARGE`；测试 `:262-270`。 |
| 空/BOM/空白拒绝 | **关闭** | 归一化后空文本在 `markdown.py:540-542` 返回 `MARKDOWN_PARSE_FAILED`；测试 `:255-260`。 |
| schema 字节语义 | **关闭** | schema `markdown-source-provenance.schema.json:81-85` 使用 `x-max-utf8-bytes=1048576`，不再误用 `maxLength`；测试 `tests/test_kb_markdown_provenance.py:364-380` 用 600,000 个汉字验证真实 parser byte gate。 |
| hostile 分类/资源/diagnostics | **关闭** | `_assert_pure_dto_fields` 在 `tests/test_kb_markdown_provenance.py:45-92` 覆盖 `page/page_end`、diagnostics、resources；single-line hostile 与 multiline HTML 仍通过。 |
| fixture/expected 原始证据 | **关闭且无回归** | 四份 Markdown fixture/expected 与 schema hash 未变：`markdown-blocks.md` `0b19f1dc…25e97`、`markdown-blocks.expected.json` `d7847f40…b22c`、`markdown-hostile.md` `8adfb117…f32`、`markdown-hostile.expected.json` `caae7293…a059`、schema `ace1c8b4…f5338`。 |

### 仍未关闭的 P1：fixture helper 没有完整断言顶层 pure-DTO metrics

**证据**

- `_assert_expected_blocks` 的实现（`tests/test_kb_markdown_provenance.py:37-42`）只比较 expected 文件已有的 block keys；这不是纯 DTO 全字段 exact helper。
- 普通 fixture 测试（`tests/test_kb_markdown_provenance.py:94-133`）断言了 source hash、`status/error` 和 `metrics.page_count`，但没有把 `line_count`、`block_count`、`image_count`、`diagnostic_count`、`markdown_line_exact_rate` 与冻结 pure-parser expected 全量比较。
- hostile fixture 测试（`tests/test_kb_markdown_provenance.py:136-173`）断言了 hash/status/error、line/block/page/image/diagnostic 的部分值，但漏断言 `markdown_line_exact_rate`，且 image/diagnostic 使用硬编码 `2/6`，没有统一走 expected metrics projection。
- schema 明确要求六个 pure-DTO metrics 字段（`markdown-source-provenance.schema.json:125-143`），因此仅做 schema shape validation 不能证明 fixture 的顶层数值契约未回归。

当前运行结果全绿只能证明当前值正确，不能证明上述遗漏字段在实现错误时会让 fixture 失败；这保留了测试伪通过边界，属于进入 Task02B 前的 P1 交接门禁问题。

**具体修改建议**

1. 为两个 Task02A pure-parser fixture 冻结一个明确的 metrics projection/oracle，只包含 `page_count`、`line_count`、`block_count`、`image_count`、`diagnostic_count`、`markdown_line_exact_rate`，不要直接复用首轮 bundle-only 的 `word_count`、`mapped_chunk_rate`、`anchor_count`、bbox 字段。
2. 让 fixture helper 对两个 fixture 统一逐字段 exact 比较上述六项，同时保留已存在的 source hash、status/error、block `page/page_end`、resources 和 diagnostics 断言。
3. 报告将“block expected-defined fields exact”与“pure DTO 全字段 exact”分开表述；补齐 helper 后再将结论升级为 PASS。

### 严格结论

**FAIL（P1 测试契约门禁；非 parser 实现容量/安全回归）。**

本轮确认上一轮的 raw `str` 50 MiB exact/+1、单 block UTF-8 1 MiB exact/+1、空/BOM/空白拒绝、`x-max-utf8-bytes` + 600,000 汉字实证、hostile 单行/多行分类、`page/page_end`/resources/diagnostics 及 fixture hash 均已关闭且无回归。但 fixture helper 尚未完整断言普通 fixture 的顶层 metrics，也未断言 hostile 的 `markdown_line_exact_rate`；在该 P1 修复前，Task02A-B 仍不得作为 Task02B 的无条件输入。

## 最终复审（metrics exact 修订，2026-09-09）

> 评审角色：Task02A-B backend-reviewer ｜ 模型：gpt-5.6-luna xhigh（仅本轮） ｜ 时间：2026-09-09 01:25 +0800
>
> 进展日志：[20260909-012500.md](../../../../../.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260909-012500.md)

### 复核结果

- `_assert_pure_metrics` 已位于 `tests/test_kb_markdown_provenance.py:62-76`，先严格要求实际 metrics key 集合等于六个 pure-parser 字段，再逐字段 exact 比较：`page_count`、`line_count`、`block_count`、`image_count`、`diagnostic_count`、`markdown_line_exact_rate`。
- 普通 fixture 在 `tests/test_kb_markdown_provenance.py:128-145` 调用 helper，hostile fixture 在 `:170-184` 调用 helper；两者均覆盖 `markdown_line_exact_rate`。
- 旧 frozen expected 不含纯 parser 专属的 image/diagnostic 两字段，测试以显式 pure-parser oracle 固定为普通 `0/0`、hostile `2/6`；其余四字段直接取 frozen expected。该投影与报告交接契约一致，未通过删除字段或只检查部分字段来弱化断言。
- status/hash/error 仍在普通 fixture `:139-145`、hostile fixture `:181-184` 断言；block `page/page_end`、resources、diagnostics 仍由 `:79-125` 的 helper 断言。

### 验证结果

- `./.venv/bin/python -m pytest -q tests/test_kb_markdown_provenance.py`：`19 passed`。
- `py_compile`（parser 与测试）、`git diff --check`：通过。
- 直接重放 frozen fixtures 的 pure metrics：
  - `markdown-blocks`：`ready`，hash 匹配；`{page_count:null, line_count:14, block_count:5, image_count:0, diagnostic_count:0, markdown_line_exact_rate:1.0}`。
  - `markdown-hostile`：`partial`，hash 匹配；`{page_count:null, line_count:11, block_count:6, image_count:2, diagnostic_count:6, markdown_line_exact_rate:1.0}`。
- 上轮已关闭项无回归：raw `str` 50MiB exact/+1、单 block UTF-8 1MiB exact/+1、空/BOM/空白拒绝、`x-max-utf8-bytes` + 600,000 汉字实证、hostile 单/多行分类、`page/page_end`/resources/diagnostics 及五份 fixture/schema hash 均保持不变。

### 严格结论

**PASS。**

本轮确认普通/hostile frozen expected 的 pure-parser 顶层六字段 metrics 已完整 exact，包含 `markdown_line_exact_rate`；没有发现 helper 弱化、漏字段或伪造通过。此前 P0/P1 容量、空输入、UTF-8 字节语义、hostile 安全边界和 fixture 证据均无回归。Task02A-B backend review 可通过，允许进入后续 Task02B 只读重放/总门禁裁决。
