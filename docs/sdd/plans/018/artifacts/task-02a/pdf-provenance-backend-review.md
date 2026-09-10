# Spec018 Task02A-A PDF provenance backend review

- 评审角色：Task02A-A backend-reviewer（独立只读评审）
- 模型：gpt-5.6-luna xhigh（仅本轮）
- 时间：2026-09-08 22:39–22:44 +0800，耗时约 5 分钟
- 评审范围：`backend/app/knowledge_base/infrastructure/parse.py`、`tests/test_kb_pdf_provenance.py`、`docs/sdd/plans/018/artifacts/task-02a/pdf-provenance-report.md` 当前未提交 diff；对照 Spec018 PDF provenance 条款、Task02A、首轮冻结 `provenance-dto.schema.json` 与 fixture expected，并核对现有 `normalize.py` / `chunkers.py` 消费方式。
- 业务代码变更：无（本评审只写本报告和进展日志）
- 进展日志：[20260908-223903.md](../../../../../.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260908-223903.md)

## 结论

**FAIL。**

当前 Task02A-A 交付不能作为通过的 backend provenance 基础交接给 Task02A-C/02B。至少有一个 P0 契约阻塞和一个 P0/P1 兼容性阻塞：序列化 DTO 未满足冻结 schema，测试因此存在伪通过；同时 `extract_pages_normalized()` 已改变既有默认提取顺序，可能改变 v1/v2 的生产切片文本。另有 hash 语义、hostile marker 误报、异常脱敏/坐标校验和回归测试覆盖缺口。报告中的“PASS”不能覆盖以下独立评审结论。

## 证据摘要

已执行：

- `./.venv/bin/python -m pytest -q tests/test_kb_pdf_provenance.py`：`10 passed`，5 个 PyMuPDF deprecation warnings。
- `./.venv/bin/python -m pytest -q tests/test_kb_normalize.py tests/test_kb_chunkers.py`：`53 passed`。
- 只读 schema 对照：当前 `to_dict()` 缺少 `mapped_count/unmapped_count`；实际 `source_hash_state="verified"`，冻结 schema 只允许 `verified_fixture/legacy_unknown/unverified`。
- 只读临时 PDF 差分：旧 `page.get_text("text")` 默认顺序为 `LOWER INSERTED FIRST → UPPER INSERTED SECOND`，新 `page.get_text("dict", sort=True)` 投影顺序为 `UPPER INSERTED SECOND → LOWER INSERTED`。
- 只读临时普通 PDF（含一个普通外部 URI 链接）：当前静态 marker 检测返回 `partial/HOSTILE_FEATURES_NOT_EXECUTED`。

## 阻塞问题

### P0-1：`PdfSourceProvenanceV1.to_dict()` 不满足冻结 DTO/schema，现有测试会伪通过

**证据：**

- `parse.py:204-226` 序列化了 pages/blocks，但没有 `mapped_count`、`unmapped_count`；也没有 `chunker`、`chunker_config`、`chunker_config_fingerprint`、`payload_schema_version`、`index_fingerprint` 或 `unmapped_reasons`。
- 首轮冻结 schema 的必填字段为 `provenance-dto.schema.json:7-19`，属性还明确要求 chunker/config/payload 版本（`:63-74`）和映射计数（`:116-125`）。
- 固定 expected 包含 `source_hash_state`、chunker/config、payload schema、index fingerprint 和最终映射计数（`docs/sdd/fixtures/spec-018/pdf-single-column-v1.expected.json:7-22,2225-2226`）。
- 当前测试 `tests/test_kb_pdf_provenance.py:40-73` 只挑选部分字段比较，没有 JSON Schema 验证，也没有断言上述 required 字段。只读对照直接得到 `missing_required=['mapped_count','unmapped_count']`。

**影响：** Task02A-A 报告声称输出可用于固定 provenance artifacts（`pdf-provenance-report.md:10-23`），但实际 DTO 不能通过首轮冻结 schema；Task02A 又明确本阶段不得私自定义/持久化 manifest（`task-02a-production-provenance-foundation.md:29,37,50,72-73`），不能用“后续 Task03 再补”掩盖当前交接形状未冻结。

**修复建议：** 先明确 Task02A-A 输出的是纯 `PdfSourceProvenanceV1` 还是 Task02A-C 的 `SourceProvenanceBundle`。若是纯 DTO，新增并校验其独立 schema；若要直接消费首轮 frozen schema，则由 bundle 层补齐全部 required 字段，不能在 parser 中伪造 manifest。测试必须用 JSON Schema（或等价严格校验）校验 `to_dict()`，并逐字段断言 hash state、版本、计数和空/非空映射语义。

### P0/P1-2：`extract_pages_normalized()` 改变既有默认提取顺序，生产切片可能回归

**证据：**

- 旧 `extract_pages()` 在 `parse.py:401-419` 调用 `page.get_text("text")`，未传 `sort=True`；现有 v1/v2 chunker 以页文本序列作为输入（`backend/app/knowledge_base/infrastructure/chunkers.py:161-173,181-234`）。
- 新 provenance 在 `parse.py:339` 固定使用 `page.get_text("dict", sort=True)`，`extract_pages_normalized()` 在 `:432-445` 再把排序后的 block raw text 投影回旧 tuple。
- 只读临时 PDF 复现：先插入低位文本、再插入高位文本时，旧默认文本顺序是 `LOWER INSERTED FIRST / UPPER INSERTED SECOND`，新 normalized 顺序变为 `UPPER INSERTED SECOND / LOWER INSERTED`。

**影响：** 这会改变 normalize → v1/v2 chunker 的输入，可能改变 chunk 边界、chunk_index、embedding 和既有检索结果。双栏阅读顺序可以是新需求，但若要改变既有索引语义，必须显式版本化并完成迁移/回归，不能通过替换 `extract_pages_normalized()` 隐式改变。

**修复建议：** 冻结一个明确的 display/extraction order：要么让 provenance 与 legacy projection 使用旧 `get_text("text")` 的排序策略（仍来自同一次 display extraction），要么承认顺序变更并新增版本/迁移门禁。补充非单调插入顺序、双栏、参考文献页、图片块夹在文本之间、空白页的 exact old-vs-new regression fixtures。

## 高风险问题（P1）

### P1-3：hash state 把“当前文件可读”冒充“已索引源”

- `parse.py:386-394` 对所有调用无条件写 `indexed_source_sha256=resolved_source_sha256`、`source_hash_state="verified"`。parser 没有索引上下文，不能证明当前文件就是历史 embedding 的源文件。
- 冻结 schema `provenance-dto.schema.json:44-55` 不接受 `verified`；Spec 018 要求无法证明历史对应关系时使用 `indexed_source_sha256=null` / `legacy_unknown`（Spec:99-101,166）。
- `source_sha256` 传入大写时 `parse.py:306-308` 只用小写比较，却把原始大写字符串返回，可能违反 schema 的小写十六进制约束。

**建议：** 分开 current source hash、trusted indexed hash 和 fixture verification state；默认 parser 只产生当前 hash，只有上游明确提供可信 indexed hash 时才填该字段。统一返回小写 SHA-256，并将 enum 对齐 Task02A-C bundle schema；补 legacy unknown、hash mismatch、uppercase input 测试。

### P1-4：hostile marker 是原始子串扫描，会误降级普通 PDF

- `_HOSTILE_PDF_MARKERS` 在 `parse.py:52-62` 包含 `/uri`、`/aa` 等短 token；`_contains_hostile_features()` 在 `:275-281` 对整个 bytes 做 `marker in payload`，`extract_pdf_provenance()` 在 `:380-384` 发现任一 marker 就把状态设为 `partial`。
- 只读临时普通 PDF 插入一个常见 URI 链接后，实际得到 `partial HOSTILE_FEATURES_NOT_EXECUTED`，命中 marker 为 `/uri`；`/aa` 还可能匹配更长合法名称的前缀。

**建议：** 不以原始子串作为状态机判据；使用 PDF 对象/字典级结构解析，区分普通 link annotation 与 JavaScript、Launch、SubmitForm、嵌入文件/XFA 等能力。增加 benign URI/annotation 和各 hostile feature 单独样本；证明 parser 不执行、不解析远程资源。

### P1-5：异常信息可能泄露路径，且 malformed bbox 未映射为稳定错误

- `parse.py:300-314` 将 `read_bytes()`/`pymupdf.open()` 的原始异常插入 `PdfParseError` message，可能包含绝对路径，不符合 Spec 的脱敏稳定错误要求。
- `_as_bbox()` 在 `:65-69`、line/block 读取在 `:241-266,344-356` 直接抛 `ValueError`；非四元组、NaN/Inf、反向或越界 bbox 没有稳定错误映射。`_normalized_bbox()` 在 `:83-90` 静默 clamp 到 `[0,1]`，会把坏坐标伪装成合法坐标。

**建议：** 所有 I/O、PyMuPDF、DTO 形状和坐标错误统一映射稳定 code，客户端只见脱敏摘要，原始异常仅内部日志；校验有限数值、顺序、crop box 尺寸，越界/无法恢复应返回 `partial + PDF_PROVENANCE_UNAVAILABLE` 或受控失败，不能静默 clamp。补损坏、加密、零页、缺 bbox、NaN/反向 bbox 测试。

### P1-6：资源读取重复且缺少容量/读取失败语义

- `parse.py:302-305` 先完整 `read_bytes()` 计算 hash，`:312` 再让 PyMuPDF 按路径打开，`:276-281` 又完整读取一次 bytes 做 hostile marker 扫描；同一原件至少重复读取两次，可能在 50 MiB 上限和并发升级时放大 I/O/内存压力。
- hostile 读取异常在 `:277-280` 直接返回 `False`，属于安全检测 fail-open；当前测试没有覆盖权限/截断/读取中断。

**建议：** 复用已读取的受控 bytes 或流式 hash/marker 结果，明确单文件和构建预算；读取/检测失败应产生稳定可诊断状态而不是把 hostile 检查当作“无特征”。

## 测试伪通过与覆盖缺口

1. `tests/test_kb_pdf_provenance.py:40-73` 未校验 frozen schema、required 字段、hash-state、chunker/config/payload/index fingerprint 和 counts；当前 `10 passed` 不能证明 DTO 可交接。
2. `:93-115` 只检查 tuple 类型、页号和一个字符串包含关系；没有把新 projection 与旧实现 exact diff，也没有参考文献页、图片块夹文本、页面空白、非单调 block 顺序样本。
3. `:107-115` monkeypatch 的只是 `parse_module.extract_pages`；新实现根本不会调用该函数，因此不能证明“只调用一次 display extraction”。应 spy `page.get_text`/PyMuPDF wrapper 并断言每页一次及不触发第二次 text extraction。
4. `:118-133` 只断言 rotation、宽高和 bbox 在 `[0,1]`，没有断言旋转/crop-box 转换后的具体坐标；错误坐标只要被 clamp 就会通过。
5. `:76-85` 只用已知 hostile fixture 断言 marker 路径，没有 benign URI/annotation 负例；没有加密/损坏/零页、I/O 异常、路径脱敏和恶意内容不执行/不发网络的可观察 spy。

## 已通过但不足以放行的点

- `parse.py:324-339` 每页有一个显式 `get_text("dict", sort=True)` 调用，且 `:397-398` 使用 `finally` 关闭文档；这支持实现意图为单次 display extraction 和基本资源关闭，但测试尚未证明调用次数、排序兼容和异常边界。
- `extract_pages()` 的返回类型仍是 `List[Tuple[int,str]]`（`:401-419`），现有 tuple 形状测试通过；这不能抵消 `extract_pages_normalized()` 内容顺序已经变化。
- 当前定向 pytest 与 normalize/chunker 回归均绿，但测试集合没有覆盖上述 P0/P1 场景，不能据此把报告标为 PASS。

## 放行条件

- 修正或冻结 DTO/SourceProvenanceBundle 序列化边界，并以严格 schema 验证覆盖 required 字段及 hash state；不在 Task02A-A 私自定义 manifest。
- 冻结并证明 legacy normalized extraction 顺序兼容，或显式版本化顺序变更并完成相应迁移/回归；至少补参考文献、图片块间文本、空白页和非单调 block 样本。
- 修正 indexed/current hash 语义、stable sanitized errors、坐标 fail-closed 校验和 hostile marker 误报/读取失败行为。
- 补齐单次 extraction spy、schema validation、旋转/crop-box 具体坐标、异常/资源安全和 benign hostile-marker 负例测试。

在上述条件完成并由 backend-reviewer 重新复审前，Task02A-A 结论保持 **FAIL**，不得以当前 `pdf-provenance-report.md` 的 PASS 作为 02A-E 或 Task02B 的放行依据。

## 修订轮复审（2026-09-08）

> 评审角色：Task02A-A backend-reviewer（独立只读复审） ｜ 模型：gpt-5.6-luna xhigh（仅本轮） ｜ 时间：2026-09-08 23:05–23:15 +0800
>
> 进展日志：[20260908-230548.md](../../../../../.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260908-230548.md)
>
> 复审对象：上一轮 FAIL 后的 `parse.py`、`tests/test_kb_pdf_provenance.py`、`pdf-provenance-report.md` 和新增 `pdf-source-provenance.schema.json`；未修改业务代码，首轮 fixture/schema 未改写。

### 复审命令与事实

- `./.venv/bin/python -m pytest -q tests/test_kb_pdf_provenance.py`：`21 passed`，5 warnings。
- `./.venv/bin/python -m pytest -q tests/test_kb_pdf_provenance.py tests/test_kb_normalize.py tests/test_kb_chunkers.py`：`74 passed`，5 warnings。
- `./.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_legacy_kb_integration.py`：`219 passed`，29 subtests，5 warnings；既有 exporter 仍尝试连接本机 `127.0.0.1:3000`，与 parser 无关。
- `python -m pytest -q tests/test_kb_pdf_provenance.py`（系统 Python，真实 `jsonschema` 4.19.2）：`21 passed`。
- 新 schema SHA-256 为 `55ea8f0c0910f7a6493a4a3fde318b189879369bf4bd5fb9aa08417344045936`，与交付报告一致。
- 对首轮 `fixture-index.json` 的 22 项原件/expected/README/schema 路径逐项重算 hash：`fixture_hash_errors=0`。
- 手动缩小 `_MAX_PDF_BYTES` 后用 11-byte 临时输入复现 `PDF_TOO_LARGE`；代码路径正确，但当前测试文件没有 committed 的 oversize boundary 用例。

### 上轮问题关闭矩阵

| 上轮问题 | 复审结论 | 证据 |
|---|---|---|
| P0-1：DTO 冒用 frozen `provenance-dto-v1`、缺 required 字段 | **已关闭** | 新纯 DTO schema 固定 `pdf-source-provenance-v1` 且边界清楚（`pdf-source-provenance.schema.json:1-38`）；`PdfSourceProvenanceV1.to_dict()` 不再输出 bundle/manifest 字段（`parse.py:204-251`）；测试严格校验 schema 并断言 bundle 字段不存在（`tests/test_kb_pdf_provenance.py:115-145`）。Task02A 仍把 bundle 留给后续阶段（`pdf-provenance-report.md:13-16`）。 |
| P0/P1-2：legacy normalized order 回归 | **已关闭** | display extraction 改为 `sort=False`（`parse.py:354-356,424`）；保存 `display_ordinal`、provenance 再按坐标排序，legacy projection 按 display ordinal 恢复（`parse.py:466-497,552-556`）；fixture exact、非单调插入、参考文献/图片/空白页测试均已加入（`tests/test_kb_pdf_provenance.py:186-198,298-339`）。 |
| P1-3：current/indexed hash 混淆 | **已关闭** | 纯 parser DTO 只输出本次受控读取的规范化小写 `source_sha256`，不输出 indexed hash/state（`parse.py:379-387,508-516`）；测试断言 bundle 字段缺席并覆盖大写输入规范化/错误 hash（`tests/test_kb_pdf_provenance.py:127-145,173-183,223-227`）。后续 SourceProvenanceBundle 仍需独立实现并复审。 |
| P1-4：hostile marker 原始子串误报 | **已关闭（实现层）** | 原始 bytes 扫描替换为 catalog/xref object inspection；普通 `/S /URI` link 明确不算 hostile，未知 inspection fail-closed（`parse.py:329-351`）；benign URI、hostile fixture 和 inspection unavailable 测试已加入（`tests/test_kb_pdf_provenance.py:201-220,245-250`）。 |
| P1-5：路径泄露、bbox 错误静默 clamp | **已关闭（实现层）** | I/O/open/hash/坐标均使用稳定脱敏 code，原始异常只作为 cause（`parse.py:317-325,375-397,452-458`）；bbox 检查 finite/order/crop，超界只在显式 partial 容差下受控归一化，严重错误 fail-closed（`parse.py:65-121`）；测试覆盖路径不泄露和 malformed bbox（`tests/test_kb_pdf_provenance.py:223-261`）。 |
| P1-6：重复读取与容量 | **基本关闭** | 原件只读入一次，hash 与 PyMuPDF 共用同一 bytes stream，逐页一次 dict extraction（`parse.py:317-326,379-390,424-426`）；测试有 bytes/read 与 per-page dict spy（`tests/test_kb_pdf_provenance.py:264-295`）；50 MiB+1 sentinel 代码存在（`parse.py:317-326`）。但缺少仓库内真实 50 MiB boundary 测试，见下方 WARNING。 |

### 仍需记录的非阻塞 WARNING

#### W1：标准 `.venv` 测试不是完整 Draft 2020-12 validator

`tests/test_kb_pdf_provenance.py:22-26,83-90` 在缺少 `jsonschema` 时自动走项目自定义 fallback。当前 `.venv` 确实没有 `jsonschema`，因此 `./.venv/bin/python` 的 21 个测试不是完整 JSON Schema 实现；系统 Python 的真实 Draft 2020-12 命令已通过，但该依赖未进入项目依赖文件。建议后续把 `jsonschema` 作为测试依赖并让 schema test 缺库时 fail，而不是降级。当前实现 DTO shape 经两路验证无 P0/P1 发现，但该验证环境差异使结论不能标为完全无条件 PASS。

#### W2：50 MiB、加密/零页/读取中断缺少 committed boundary 用例

`parse.py:317-326,394-397` 已实现 50 MiB+1 sentinel、加密和零页稳定码，手动缩小常量可以复现 `PDF_TOO_LARGE`；但 `tests/test_kb_pdf_provenance.py` 没有直接断言 `_MAX_PDF_BYTES`、加密 PDF、零页或读取中断。这些是资源/异常硬边界，建议在 02A-E 前补齐；目前不构成已观察到的错误行为。

#### W3：renderer overflow 容差尚未与 Spec ±0.005 明确同源

实现常量 `_RENDERER_BBOX_TOLERANCE_RATIO=0.01`（`parse.py:58`）按 crop 尺寸的 1% 判定可受控 overflow，并将结果标记 `partial/PDF_PROVENANCE_UNAVAILABLE`（`parse.py:504-505`）。这比 Spec 的正常 bbox ±0.005 fixture 门槛更宽；当前测试只覆盖大幅越界（`tests/test_kb_pdf_provenance.py:252-261`），没有 0.005/0.01 边界。建议 Task02A-B 冻结“归一化误差阈值 vs renderer overflow 容差”的关系并增加边界样本；在当前代码中超界不会伪装为 ready，因此暂不升级为 FAIL。

### 修订轮结论

**WARNING（无已复现的 P0/P1 实现错误；存在验证环境/边界测试警告）。**

上轮 P0 DTO 边界、legacy exact order、单次 bytes/page dict extraction、URI 与 hostile object 区分、current/indexed hash 分层、脱敏稳定错误和坐标 fail-closed 均已由代码与定向测试关闭；首轮 fixture 全量 hash 也保持不变。当前不再有足以判定实现 `FAIL` 的已复现问题。

但由于标准 `.venv` 仍以 fallback 替代真实 JSON Schema，且 50 MiB/异常边界没有 committed test，复审不作无条件 `PASS`。建议把 W1–W3 纳入 Task02A-E/Task02B 前置补强；在不改变纯 DTO/legacy 兼容边界的前提下，当前交付可进入后续子任务的受控复核，不得据此宣称 Task02B 或完整 provenance bundle 已通过。

## 最终复审（2026-09-08）

> 评审角色：Task02A-A backend-reviewer ｜ 模型：gpt-5.6-luna xhigh（仅本轮） ｜ 时间：2026-09-08 23:22–23:24 +0800
>
> 进展日志：[20260908-232244.md](../../../../../.codebuddy/agent-logs/spec-018/task-02a/backend-reviewer/20260908-232244.md)

### 复审范围与验证事实

- `requirements-dev.txt:8-9` 已声明 `jsonschema>=4.19,<5`；`tests/test_kb_pdf_provenance.py:7,37-41` 直接使用 `Draft202012Validator`，不再存在 fallback。当前 `.venv` 实际版本为 `jsonschema 4.19.2`。
- `parse.py:54` 保持 `_MAX_PDF_BYTES = 50 * 1024 * 1024`，`tests/test_kb_pdf_provenance.py:231-240` committed 测试构造 50MiB+1 输入并断言 `PDF_TOO_LARGE`；`:243-259` 覆盖加密 PDF/`PDF_ENCRYPTED`；`:262-275` 覆盖零页/`PDF_EMPTY`。
- `parse.py:63,84-94` 与 `tests/test_kb_pdf_provenance.py:215-228` 严格使用 0.005；100.5/100.0（0.005）通过，100.51/100.0（0.0051）失败并映射 `PDF_PROVENANCE_UNAVAILABLE`。
- `parse.py:315-395` 仍保持单次受控 bytes 读取、稳定错误和同一 bytes stream 打开；`parse.py:352-354,401-426` 仍保持每页一次 passive display dict 提取；纯 DTO/current hash/hostile object/legacy projection 代码未回退。

### 执行结果

- `./.venv/bin/python -m pytest -q tests/test_kb_pdf_provenance.py`：`25 passed`，真实 JSON Schema validator 生效，无 fallback。
- `./.venv/bin/python -m pytest -q tests/test_kb_pdf_provenance.py tests/test_kb_normalize.py tests/test_kb_chunkers.py`：`78 passed`。
- `./.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_legacy_kb_integration.py`：`223 passed`、`29 subtests passed`；仅已有 PyMuPDF deprecation warnings，OTEL exporter 的本机 3000 连接重试与本评审无关。
- `fixture-index.json` 22 项源文件/expected/README/schema hash 重算：`fixture_hash_errors=0`；首轮 fixture 未变更。纯 DTO schema SHA-256 仍为 `55ea8f0c0910f7a6493a4a3fde318b189879369bf4bd5fb9aa08417344045936`。
- `parse.py` 与 provenance tests `py_compile` 通过；本轮未修改业务代码，首轮 FAIL 和上一轮 WARNING 历史保留。

### 上轮 WARNING 关闭矩阵

| 上轮 WARNING | 最终结论 | 证据 |
|---|---|---|
| W1：`.venv` 缺真实 JSON Schema validator | **已关闭** | `requirements-dev.txt:8-9` 声明依赖；测试直接导入 `Draft202012Validator`，`.venv` 实际为 4.19.2，25 个定向测试通过。 |
| W2：50MiB/加密/零页缺 committed tests | **已关闭** | `tests/test_kb_pdf_provenance.py:231-275` 三组用例均 committed 并在定向/回归测试中通过。 |
| W3：renderer overflow 容差未与 Spec ±0.005 对齐 | **已关闭** | `parse.py:63,90-94` 固定 0.005；`:215-228` 明确 0.005 pass、0.0051 fail。 |

### 最终结论

**PASS。**

上一轮 P0/P1（纯 DTO schema 边界、legacy exact order、单次 bytes/page-dict extraction、benign URI 与 hostile object、current/indexed hash 分层、脱敏稳定错误、坐标 fail-closed）均无回归；三项 WARNING 已由依赖、committed 边界测试和严格 0.005 容差断言关闭。Task02A-A backend review 可放行进入后续受控任务；本结论不替代后续完整 provenance bundle/Task02B 的独立评审。
