# Spec018 Task02A-A PDF provenance report

日期：2026-09-08
角色：Task02A-A backend-dev
模型：gpt-5.6-luna xhigh（临时，仅本轮）
结论：**READY FOR RE-REVIEW（已逐项关闭追加 WARNING；不替代 Task02A-B/C/D/E 门禁）**

## 交付范围

- `backend/app/knowledge_base/infrastructure/parse.py` 新增纯 parser 版本化
  `PdfSourceProvenanceV1`、`PdfPageProvenanceV1`、`PdfBlockProvenanceV1`、
  `PdfLineProvenanceV1` 与 `extract_pdf_provenance()`。
- 新增 `pdf-source-provenance.schema.json`，`schema_version` 固定为
  `pdf-source-provenance-v1`。parser DTO 不冒用首轮 `provenance-dto-v1`，不输出
  `chunker`、chunks/anchors、mapped/unmapped、index fingerprint、indexed hash 或
  `source_hash_state`；这些字段由 Task02A-C 的 SourceProvenanceBundle 负责。
- 每页仅调用一次 `page.get_text("dict", sort=False)`：raw text、normalized text、
  line/block bbox 和 insertion ordinal 来自同一 display extraction；provenance reading
  order 再按 `(bbox.y0, bbox.x0, display_ordinal)` 稳定排序，line 仅为诊断数据，word 不作硬门。
- block 保留 PDF point `bbox` 与按未旋转 `crop_box` 宽高归一化的 `normalized_bbox`，
  block `start/end` 为 block raw text（含行尾换行）的稳定局部区间。
- `extract_pages()` 保持旧 tuple/raw 语义；`extract_pages_normalized()` 从 DTO 的
  `display_ordinal` 投影回旧 tuple 结构，保留 `normalize_text` 与 reference-zone 行为，
  避免生产链路第二次 `get_text`。
- hostile 判定读取 PDF catalog/xref dictionary 的 action/form/embed 能力；普通 `/S /URI`
  link 不降级。检测失败为 `failed/PDF_PROVENANCE_UNAVAILABLE`，不使用原始 bytes 子串。
- source SHA-256 只表示本次受控读取的原始字节，始终规范为小写；显式 hash 不匹配
  `PDF_SOURCE_HASH_MISMATCH`，不在 parser 伪造 indexed hash/state。读取最多 50 MiB+1
  sentinel，使用同一 bytes stream 打开 PyMuPDF，I/O/open/shape/coordinate 错误均为稳定脱敏 code。

## 固定 fixture 对齐与 hash 证据

未修改 `docs/sdd/fixtures/spec-018` 中任何 PDF、README、expected JSON 或首轮 schema。
以下是实现后重新计算的 source hash 与 expected JSON hash；source hash 与 expected 中记录值
逐项一致：

新增纯 DTO schema 的 SHA-256：
`55ea8f0c0910f7a6493a4a3fde318b189879369bf4bd5fb9aa08417344045936`。

| fixture | PDF SHA-256 | expected JSON SHA-256 | 状态 |
|---|---|---|---|
| `pdf-single-column-v1` | `3cc6b61497f483fcb1933919cb00f1568ad1fd609953c96e4970c772cbe4e4ec` | `a91ace4a082d86365006f353c8ecb5ac3ad4d940ec265ff87216f6e43b382ea3` | ready |
| `pdf-two-column-v1-overlap` | `33726da69e2c79bd5b3d4fe10dc14a2b64760802151b4af97b97f4bb84e99e7d` | `418a558b78e24cb2bf8e400b868cbdea34bbfe4aa3236c9bdc21ddb2575322c0` | ready |
| `pdf-v2-cross-page` | `c0fccf6f1d0dde1c299ce044e63c79c2796ca981f7bcadaf62ec27db9e996468` | `cbece70d3a9296494aa4f28e1e4e27bcae89af7c9e3c09c80ea9b0c73f0e17fc` | ready |
| `pdf-no-text-layer` | `05e59443707b6976afedbf1b0c1de5ad9bf62609411c902feb241b5033303252` | `b116f4a6a81b74039f9327d55420d2a266218a2fc382b1ffefb363680c6a8289` | failed / PDF_NO_TEXT |
| `pdf-hostile-features` | `1bc72165cc992f88ad28ef9a6ea24438e1024c305082f03bd3d554a59d664377` | `20477b4ed7b1250adf12388b7565a305699d8f4986071f3687a8d9b0a811e4dc` | partial / HOSTILE_FEATURES_NOT_EXECUTED |

## 验证

- `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/parse.py`：退出码 0。
- `./.venv/bin/python -m pytest -q tests/test_kb_pdf_provenance.py`：退出码 0，25 passed，标准 `.venv` 直接使用 Draft 2020-12 `jsonschema`；5 个 PyMuPDF deprecation warnings。
- `./.venv/bin/python -m pytest -q tests/test_kb_pdf_provenance.py tests/test_kb_normalize.py tests/test_kb_chunkers.py`：退出码 0，78 passed，覆盖 schema、单次 dict/bytes spy、legacy exact、非单调插入、reference/image/blank、hostile benign/error、50 MiB/加密/零页和 ±0.005 坐标边界。
- `./.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_legacy_kb_integration.py`：退出码 0，223 passed，29 subtests passed，5 个 PyMuPDF deprecation warnings。
- `git diff --check`：退出码 0。
- `requirements-dev.txt` 已加入 `jsonschema>=4.19,<5`，并安装至标准 `.venv`；测试缺库即导入失败，不再 fallback。全套知识库测试退出后 observability exporter 曾尝试访问本机 `127.0.0.1:3000` 并重试；这是既有测试遥测副作用，不是 parser 网络访问。

## 决策、风险与交接

- 采用 `dict + sort=False` 冻结旧 insertion order；block id 使用 `sample_id`（存在时）+ 页内 `bN`，`ordinal` 使用跨页 reading-order 序号，`display_ordinal` 保存 legacy 序列。
- coordinate reading order 使用 `(bbox.y0, bbox.x0, display_ordinal)`；固定 fixture 与旧 normalized projection 均 exact，普通 URI link 不触发 hostile 状态。
- renderer overflow 容差已严格改为每个归一化坐标 ±0.005；原始 bbox 不改写，normalized 值仅在显式 `partial/PDF_PROVENANCE_UNAVAILABLE` 状态下受控落入 schema 范围；超过 ±0.005、非有限、反向或缺失坐标直接 fail-closed。
- 已 committed 覆盖 50 MiB+1 sentinel、加密 PDF、零页等价 mock、稳定 I/O/open 错误以及 ±0.005/±0.0051 坐标边界。
- 需由主 Agent 在后续 02A-C 接入时继续验证 source bundle 的 `document_id/source_sha256` 语义，并由 Task03 定义 manifest；本报告不声称完成 manifest、Qdrant 或 PDF.js 映射。
- 当前 Task02A-A 无实现阻塞，等待 backend-reviewer 复审。风险仅为后续若 PyMuPDF display dict 版本改变，必须提升 `source_parser_version` 并重新评审 fixture；既有 v1/v2 tuple chunker 回归已通过。
