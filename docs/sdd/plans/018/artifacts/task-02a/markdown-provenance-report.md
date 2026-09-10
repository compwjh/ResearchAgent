# Spec018 Task02A-B Markdown source provenance report

日期：2026-09-09
角色：Task02A-B backend-dev
模型：gpt-5.6-luna xhigh（临时，仅本轮）
结论：**READY FOR RE-REVIEW（本轮 metrics exact 测试门禁已关闭，等待 backend-reviewer 复核；纯 Markdown parser DTO；不替代 Task02B GO/NO-GO，也不定义 SourceProvenanceBundle/manifest）**

## 交付范围

- 新增 `backend/app/knowledge_base/infrastructure/markdown.py`，提供
  `MarkdownSourceProvenanceV1`、`MarkdownBlockProvenanceV1`、
  `MarkdownInlineResourceV1` 与 `extract_markdown_provenance()`。
- DTO 的 `schema_version` 固定为 `markdown-source-provenance-v1`；只包含当前
  原始 bytes 的 SHA-256、规范化 LF 文本、blocks、inline resource 元数据、诊断和
  metrics，不包含 chunks、anchors、indexed hash、bundle 或 manifest 字段。
- 原始 bytes 先计算 hash，再允许剥离 UTF-8 BOM；非法 UTF-8 或 NUL 稳定拒绝为
  `INVALID_ENCODING`。CRLF/CR 统一为 LF，行尾水平空白去除，规范化文本及 block
  `start/end` 均基于规范化 LF 文档；source hash 不受换行/BOM 规范化影响。
- block 边界覆盖 heading、连续 paragraph、list（续行/嵌套）、GFM table、fenced
  code、blockquote、horizontal rule 和 HTML block。每个 block 具备稳定 ordinal、
  1-based `locator.start_line/end_line`、heading path、block type 和规范化 text。
- Markdown block 的 `page`/`page_end` 均为 JSON `null`，绝不伪造为 0。图片只作为
  `inline_resources` 元数据返回，`loadable=false` 并生成 text placeholder；解析器不
  读取图片、不渲染 HTML、不执行 JavaScript、不访问网络。
- `<script>`、事件属性、`javascript:` 等 hostile 内容只生成诊断；原 block 行范围
  不改变，状态为 `partial`，错误为
  `HOSTILE_MARKDOWN_REQUIRES_SANITIZER_PROBE`。HTML sanitizer/DOM contract 留给
  Task05。
- parser 通过受控 chunk reader 在 hash/decode 前执行 50 MiB 源字节上限；Path、stream、
  bytes 和编码后的 raw `str` 入口共享该门禁。恰好 50 MiB 可接受，超过 50 MiB 稳定
  拒绝为 `PAYLOAD_TOO_LARGE`。规范化 UTF-8 单 block 上限为 1 MiB，超过稳定拒绝为
  `MARKDOWN_BLOCK_TOO_LARGE`；block 数硬上限为 200,000。
- 空、仅 BOM、仅空白文档统一拒绝为 `MARKDOWN_PARSE_FAILED`，避免进入 ready/index/manifest
  流程；长行在 1 MiB 内不被截断。

## 固定 fixture/hash 证据

未修改 `docs/sdd/fixtures/spec-018/` 中任何原件、README、expected JSON 或首轮
NO-GO 证据。

| 文件 | SHA-256 |
|---|---|
| `markdown-blocks.md` | `0b19f1dc1a3bd687b2b9f369ce6c93998648d4f7b6c976d1ed87a78b41325e97` |
| `markdown-blocks.expected.json` | `d7847f4089d88f4c5f989073eac2a3a048471a05986c3531deb694e782b2b22c` |
| `markdown-hostile.md` | `8adfb117879523e8858d9346307cfcfce94eb8b71d144c7453802b2973cf9f32` |
| `markdown-hostile.expected.json` | `caae72931d25d856453ece2134c9af6ae41da3a7dd076b553b9ad0b87293a059` |
| `markdown-source-provenance.schema.json` | `ace1c8b494a3575c240f9241c3e61541e4ea56343b43f5193aa2aa51b20f5338` |

`markdown-blocks` 正式 parser 输出的 source hash 与首轮 expected 一致，并对首轮
`blocks` 逐字段 exact 比较（含 block_id、ordinal、text、locator、heading_path、
block_type、start/end）。5 个 block 的 `start_line/end_line` 和字符区间分别精确匹配首轮 expected：
`1-1/0-23`、`3-3/25-121`、`5-6/123-159`、`8-10/161-215`、`12-14/217-247`。
hostile fixture 也逐字段 exact 比较，保持 expected 冻结的 6 个 `paragraph` block、
原始行范围 `1/3/5/7/9/11`；纯 DTO helper 额外逐块断言 `page/page_end=null`、
完整稳定 diagnostics，以及 remote/relative 两个图片 resource 的 destination、
placeholder 和 `loadable=false`。普通 fixture 的 diagnostics/resources 均断言为空；
真正多行 `<section>...</section>` 仍由独立边界测试归为 `html` block。

两份冻结 fixture 现在都通过同一 helper 对纯 parser 顶层 `metrics` 的六字段投影做
完整 exact 断言：`page_count`、`line_count`、`block_count`、`image_count`、
`diagnostic_count`、`markdown_line_exact_rate`。其中首轮 bundle expected 已有的四个
字段直接取自冻结 expected；首轮 expected 未包含的纯 parser `image_count`/
`diagnostic_count` 由固定 oracle 明确冻结为普通 `0/0`、hostile `2/6`，因此任何
字段缺失、漂移或 `markdown_line_exact_rate` 不为 `1.0` 都会使测试失败。

## 验证

- `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/markdown.py`：退出码 0。
- `./.venv/bin/python -m pytest -q tests/test_kb_markdown_provenance.py`：退出码 0，19 passed。
- `./.venv/bin/python -m pytest -q tests/test_kb_markdown_provenance.py tests/test_kb_normalize.py tests/test_kb_chunkers.py`：退出码 0，72 passed。
- 显式展开 `tests/test_kb_*.py` 并加入 `tests/test_legacy_kb_integration.py`：退出码 0，242 passed、29 subtests passed、5 个既有 PyMuPDF deprecation warnings。
- `./.venv/bin/ruff check backend/app/knowledge_base/infrastructure/markdown.py tests/test_kb_markdown_provenance.py`：退出码 0；import、lazy list/blockquote、multiline HTML 边界均通过静态检查。
- `git diff --check`：退出码 0；测试使用标准 `.venv` 的真实 Draft 2020-12 `jsonschema` 校验，无 fallback。Schema 用非断言 `x-max-utf8-bytes: 1048576` 注解；Draft 2020-12 原生 `maxLength` 按 code point，不表达 UTF-8 byte 上限，真正硬门由 parser 与边界测试执行。600000 个汉字的 schema instance 可被 validator 接受，但 parser 按 UTF-8 bytes 返回 `MARKDOWN_BLOCK_TOO_LARGE`。
- 本轮补丁将普通/hostile 两个 fixture 的六字段纯 parser metrics 投影统一做 exact 比较（含 `markdown_line_exact_rate`），未改 parser、fixtures 或 expected；上述 19/72/242 计数保持不变。

## 决策、风险与交接

- 使用纯标准库的行级 parser，避免为 Task02A-B 引入第二套 chunker 或渲染链；v1/v2
  后续应消费这些 blocks 并保持各自既有 chunk DTO/config fingerprint。
- `start/end` 是 Python 字符偏移，指向规范化 LF 文本；`start_line/end_line` 是
  原始结构对应的 1-based 行范围，即使 HTML 需要净化也不变。
- hostile Markdown 的 sanitizer/DOM 安全证据有意移交 Task05；本 parser 不声称已
  完成浏览器零网络门禁。
- 当前无实现阻塞；主 Agent 后续应让 backend-reviewer 检查 schema/DTO 字段、固定
  fixture hash 与 Task02A→02B 交接，再由 Task02B 只读重放正式入口并裁决严格 GO/NO-GO。
