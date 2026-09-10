# Spec018 Task06E-A 稀疏来源锚点后端实现报告

## 结果状态与摘要

```text
task=06E-A
result=IMPLEMENTED-IN-ISOLATION
mapping_algorithm_version=source-anchor-v2
fuzzy_similarity_mapping=false
anchor_relation_basis=exact-normalized-source-range-intersection
unresolved_reason=SOURCE_RANGE_UNRESOLVED
chunk_text_or_order_changed=false
real_data_or_qdrant_touched=false
```

本轮修复 `SourceProvenanceBundle` 的来源锚点构建：删除 `SequenceMatcher` 模糊正分关系，按 PDF 页级、v2/Markdown 文档级或 Markdown block 级规范化来源流解析唯一的半开区间。只有 chunk 的真实来源区间与 SourceBlock 区间存在正交集时才写 anchor；v1 overlap 保留前一来源片段尾部与当前来源片段两个证据区间，v2 跨页使用同一文档来源流。无法唯一、完整对齐的 chunk 不做模糊降级，记录 `SOURCE_RANGE_UNRESOLVED` 并使 bundle 进入受控 partial 状态。

## 改动文件

- `backend/app/knowledge_base/infrastructure/provenance.py`
  - 将映射版本升级为 `source-anchor-v2`，移除 `SequenceMatcher` 和 `_match_count`。
  - 为 v1 PDF 页、v1/Markdown block、v2 跨页/文档构造规范化来源流及 block `[start,end)` 区间。
  - 为 v1 chunk 解析唯一精确来源片段，保留 overlap 的两个真实来源区间；v2 仅接受唯一完整文本出现。
  - 依据区间交集字符数计算 coverage、按真实覆盖与 block ordinal 选择 primary；不匹配/重复出现统一输出 `SOURCE_RANGE_UNRESOLVED`。
  - 仅新增内部 source-key 元数据，v1/v2 chunk 的文本、页码、顺序和 payload 字段保持不变。
- `tests/test_kb_source_provenance_bundle.py`
  - 更新 bundle structural validation 与 `source-anchor-v2` 版本断言。
  - 将 two-column overlap 期望改为真实区间关系：chunk 0 仅覆盖 b0/b1，chunk 1 仅覆盖 b1/b2，去除无真实交集的 b2/chunk0 与 b0/chunk1。
  - 新增标题稀疏关联、缺失来源区间不建 anchor、重复精确出现 fail-closed 测试。
- `docs/sdd/plans/018/artifacts/task-06/sparse-anchor-backend-report.md`
  - 本报告。

未修改 schema、manifest/store、frontend、routes、原件、`data/kb`、Qdrant 或向量；Task06E-A 的允许范围不包含这些文件/数据。

## API / 数据细节

本轮没有新增 HTTP endpoint。现有 `build_source_provenance_bundle()` 仍返回同一 bundle 形状；变化为：

- `mapping_algorithm_version` 为 `source-anchor-v2`。
- anchor 关系只由规范化来源流中的真实区间正交集证明。coverage 为各证据区间与 block 区间的去重交集字符数除以规范化 chunk 文本长度，范围限制在 `[0,1]`。
- v1 overlap chunk 的拼接文本可能省略来源分隔空白，因此内部保留前一 piece 尾部和当前 piece 的两个区间，不能把省略的分隔符当作来源内容。
- chunk 文本在来源流中出现 0 次或多次、或 chunk 不能作为一个完整可验证区间出现时，不生成任何 anchor，增加 `{chunk_index, reason: "SOURCE_RANGE_UNRESOLVED"}`。
- block、chunk、anchor 的序列化形状仍遵守现有 bundle schema 字段；本轮测试在内存中将既有 Task02A schema 的映射版本常量切换为 v2 进行结构验证，未改动 schema 文件。

## 验证命令与结果

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `./.venv/bin/python -m pytest -q tests/test_kb_source_provenance_bundle.py` | 0 | **23 passed**；5 个既有 PyMuPDF DeprecationWarning |
| `./.venv/bin/python -m pytest -q tests/test_kb_source_provenance_bundle.py tests/test_kb_chunkers.py tests/test_kb_pdf_provenance.py tests/test_kb_markdown_provenance.py` | 0 | **96 passed**；5 个既有 PyMuPDF DeprecationWarning |
| `./.venv/bin/python -m pytest -q tests/test_kb_source_provenance_bundle.py tests/test_kb_candidate_rebuild.py tests/test_kb_document_routes.py tests/test_kb_document_reindex.py tests/test_kb_document_foundation.py` | 0 | **122 passed**；5 个既有 PyMuPDF DeprecationWarning |
| `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/provenance.py tests/test_kb_source_provenance_bundle.py` | 0 | 通过 |
| `./.venv/bin/ruff check backend/app/knowledge_base/infrastructure/provenance.py tests/test_kb_source_provenance_bundle.py` | 0 | `All checks passed!` |
| `git diff --check` | 0 | 通过 |

固定样本的 chunk 文本与顺序保持不变；PDF two-column 的 anchor 数量从旧模糊关系 6 条降为真实区间关系 4 条，且不再把无交集的关系写入。v2 cross-page 保留 page 1/page 2 两个真实 block 关系；Markdown block fixture 保持一对一 anchor 与精确行范围。

## 决策依据

1. Spec018 source-anchor-v2 明确禁止任意共同词、编辑距离、`SequenceMatcher` 零散子串和全文相似度推断关系，要求唯一可验证的规范化来源字符区间正交集。
2. 既有 chunker 的 chunk 输出是本轮不可变事实，因此 provenance 层重建与 chunker 相同的来源流，并只接受 chunk 文本的唯一精确出现；v1 overlap 的省略分隔空白保留为两个证据区间。
3. 真实交集为空时不以“最多 N 条”或阈值补关系，避免标题、页眉、重复词造成接近 `chunk×block` 的组合爆炸。

## 风险与阻塞

- 当前任务未修改 `backend/app/knowledge_base/infrastructure/inspection.py` 及其 manifest schema；这些下游文件仍可能保留旧 mapping-version 常量，需由主 Agent/后续任务完成 v2 manifest 消费链同步后才能声称端到端交互已收口。
- `source-anchor-v2` 对重复 chunk 文本采取保守 fail-closed：即使调用方能凭顺序猜测，也记录 `SOURCE_RANGE_UNRESOLVED`，避免把猜测当作定位事实。
- v2 对被 chunker 重组为非连续文本的极端句子切片不伪造单一来源区间；这类 chunk 会进入 partial/unmapped，符合停止条件。
- 所有测试使用固定 fixture、临时 DTO 或 monkeypatch；未读取/写入真实用户原件、`data/kb` 或 Qdrant，未运行 embedding、下载或重建。

## 主 Agent 后续动作

1. 复核本报告与限定文件 diff，确认 `provenance.py` 不含 `SequenceMatcher`、模糊阈值或关系数量截断。
2. 同步 inspection manifest/schema 的 mapping-version 与旧 v1 清单失效门，复跑 manifest/route/frontend 集成验收；未完成前不要重建真实用户 manifest。
3. 在所有定向测试通过且 chunk/Qdrant fingerprint 对账后，再按 Task06E-E 的生产门禁决定是否重建单文档 manifest；本轮不执行该动作。

## 时间、模型与工具统计

- 开始：2026-09-10 约 19:40（Asia/Shanghai）
- 结束：2026-09-10 约 20:00（Asia/Shanghai）
- 总耗时：约 20 分钟
- 模型：临时 `Luna xhigh`（backend-dev 角色）
- Token 统计：当前工具环境未提供精确 token 用量
- 工具统计：约 15 次读取、补丁、测试与静态检查调用

## 进度日志

`.codebuddy/agent-logs/spec-018/task-06e/backend-dev/20260910-sparse-anchor.md`

## 2026-09-10 来源流规范化回对齐补充

主 Agent 的真实 PDF 只读核对发现，PDF chunk 使用页级 `normalize_text` 后再经过
`_mapping_text`，而 block 仅使用独立 block 文本的映射副本；`ﬁ → fi` 等 NFKC
长度变化会使 overlap 边界和 block 精确区间错位，跨 block 的行末断词以及参考文献
区的换行规则也会造成同样的假未命中。此次只修正 provenance 的映射副本，不改变
chunker 输入、chunk 文本、页码或顺序：

- source haystack 与所有 lookup 都经过同一 `_mapping_text`；PDF block mapping
  另复用该页 chunk 投影的 `normalize_text` 参考文献区规则。
- 仅当原始相邻 block 确实满足 `词-\\n词` 时，mapping copy 去掉跨 block 的那个
  断词连字符，使两段仍占据连续的精确半开区间；不做相似度或模糊匹配。
- v1 overlap 先对原始 chunk 的 overlap 后缀做 `_mapping_text`，再计算映射长度，
  避免 NFKC 扩展字符使 overlap 起点漂移。

新增 fixture 级回对齐测试覆盖 NFKC source/block 同构投影及跨 block 断词区间。对真实
PDF `data/kb/papers/d4dfd2a620384ad5bece27320661f8f0.pdf` 的只读验证结果如下：

```text
v1: blocks=504 chunks=107 anchors=566 mapped=107 unmapped=0 status=ready error=None
    possible block×chunk pairs=53928, anchor ratio=1.0495%
v2: blocks=504 chunks=214 anchors=497 mapped=213 unmapped=1 status=partial
    unresolved={chunk_index:128, reason:SOURCE_RANGE_UNRESOLVED}
    possible block×chunk pairs=107856, anchor ratio=0.4608%
```

因此 v1 真实 PDF 的 107/107 个连续 page chunks 均能映射；v2 仅保留一个因图表块被
chunker 非连续重组而无法证明单一来源区间的受控 unresolved，未以模糊关系补齐。两种
模式的 anchor 数量均远低于 block×chunk 全连接上限，未发生组合爆炸。真实 PDF 验证只
读取原件并在内存构建 DTO，没有写入原件、manifest、Qdrant 或用户数据。

本次补充验证：

| 检查 | 结果 |
|---|---|
| `./.venv/bin/python -m pytest -q tests/test_kb_source_provenance_bundle.py` | **24 passed**；5 个既有 PyMuPDF DeprecationWarning |
| `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/provenance.py tests/test_kb_source_provenance_bundle.py` | 通过 |
| `./.venv/bin/ruff check backend/app/knowledge_base/infrastructure/provenance.py tests/test_kb_source_provenance_bundle.py` | `All checks passed!` |
| `git diff --check` | 通过 |
