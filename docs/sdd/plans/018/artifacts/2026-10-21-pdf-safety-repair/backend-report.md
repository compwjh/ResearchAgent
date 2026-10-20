# Spec018 PDF 安全与单文档发布修复：backend-dev 报告

- 日期：2026-10-21（Asia/Shanghai）
- 角色：backend-dev
- 范围：仅 `backend/**` 与受影响的后端测试（`tests/kb/**`、`tests/literature_maps/**`）
- 合同：`repair-contract.md`
- 状态：实现完成，等待 backend review / backend tester / root 的真实 API 验证
- 安全边界：所有 PDF action、JavaScript、导航、附件和网络行为均未执行；没有联网、部署、真实 reindex、全库重建或 commit。

## 结论

已按合同完成最小同范围修复：普通本文件页内 `/GoTo` + `/Fit` 的 Catalog `OpenAction`（包括裸数组、间接数组和受控动作字典）可通过严格被动白名单；危险 action、远程/文件目标、表单、嵌入、未知字段/动作链和无法证明安全的结构仍 fail-closed。真实 GAT 文档此前的 `HOSTILE_FEATURES_NOT_EXECUTED` 根因是普通内部页导航，未放宽全文 evidence gate。

单文档 worker 现按 `Qdrant payload → manifest → 严格 metadata/hash → generation refresh/require → source/manifest 复核` 发布。manifest 的 `ready/partial/failed` 映射到 chunker 的 `indexed/indexed_partial/failed`，v1 仍唯一驱动顶层兼容字段；partial 不会升级为 ready。失败路径不回滚原件或向量，但保持 marker/live 不一致时 fail-closed，避免全文读路径接受中间态。

## 实现摘要

### 被动 PDF active-feature resolver

- `parse.py` 新增 bounded resolver：最多 4 层间接引用、visited xref 防循环、单对象 16 KiB、目标数组 8 项。
- 白名单只接受当前文档真实 page xref 的 `[page-ref /Fit]`；动作字典仅接受可选 `Type=/Action`、`S=/GoTo`、`D`。字符串/named destination、remote/file/script/form/attachment、`Next` 和未知字段不放行。
- Catalog `AA`/`AcroForm` 保持非空 hostile；全 xref 扫描保留危险名字，并对 PDF name `#xx` 编码变体做被动归一化。普通 URI 仅保留为链接，不发起请求。
- 超限、循环、不可读或畸形结构映射到既有 `PDF_PROVENANCE_UNAVAILABLE` failed 语义；已识别 hostile 结构保持 `HOSTILE_FEATURES_NOT_EXECUTED` partial。

### 单文档 manifest / metadata / generation 发布

- `_publish_inspection_manifest()` 现在返回实际已校验写入的 manifest，不再自行刷新 generation。
- 复用 manifest store 的现有 `_lock`，通过 `publication_mutation_lock()` 串行化 manifest、严格 metadata 和 marker 操作；embedding/Qdrant 写入不持锁。
- `migration.publish_index_state()` 是窄 schema/原子写入口，仅允许受控 chunker 状态及现有 hash 字段；verified 只有 source hash 与 canonical source H 一致时写入。source 变化可记录 `SOURCE_HASH_MISMATCH` / `mismatch`，不会伪造 verified。
- 解析/向量写后及 marker 复核阶段都重新核对原件 hash。manifest 写失败、metadata 原子写失败、generation refresh/require 失败均不会返回成功；严格失败状态写入失败时保留 marker/live mismatch。

## 定向验证

以下命令均在本地临时目录/受控 fake client 上执行，没有触碰真实知识库数据：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `python scripts/check_test_naming.py` | 0 | `test naming check passed` |
| `.venv/bin/python -m pytest -q tests/kb/test_kb_pdf_safety_publication.py` | 0 | 18 passed，5 warnings |
| `.venv/bin/python -m pytest -q tests/kb/test_kb_pdf_safety_publication.py tests/kb/test_kb_pdf_provenance.py tests/kb/test_kb_document_reindex.py tests/kb/test_kb_tasks.py` | 0 | 64 passed，5 warnings |
| `.venv/bin/python -m pytest --collect-only -q tests/kb/test_kb_pdf_safety_publication.py tests/kb/test_kb_pdf_provenance.py tests/kb/test_kb_document_reindex.py tests/kb/test_kb_tasks.py` | 0 | 64 tests collected，无 collection error |

覆盖的故障注入包括：合法/危险/未知/非本文件页目标、间接 GoTo、循环、过大对象、partial manifest、v2 不覆盖 v1 顶层字段、manifest 写失败、metadata 原子写失败、generation refresh 失败、索引期间原件变化，以及 generation gate 对中间态的拒绝。

## 未覆盖项与风险

- 未运行项目全量 pytest；按任务边界只运行 KB/PDF 受影响领域定向回归。
- 未执行真实 API reindex、GAT 恢复、Spec043 全文分析/问答、部署或 provider；这些是 root 在合并前依照合同执行的后续门禁。
- Qdrant upsert/manifest 写失败可能留下已写入的派生向量，这是合同允许的 fail-closed 结果；本轮未新增补偿删除协议。
- 失败状态在可证明的 source mismatch、manifest 写失败和 generation 验证失败路径保留 marker/live mismatch，因此全文读路径会拒绝；旧的已成功 manifest 只在不涉及本轮派生写入失败且旧索引仍可用时保留。
- 本轮没有改变公开 API、持久 task 模型、schema 版本、全文 evidence gate 或 generation 拓扑。

## P1 review 修复追加记录（2026-10-21）

针对 `backend-review.md` 的三项 BLOCK P1 已在同一合同范围内集中修复：

- `parse.py` 不再用 action/destination 的 first-match 正则判断安全。现在对直接/间接对象做被动、有界类型解析；字典重复键取 PDF 规范化后的最后值，字符串/嵌套未知结构不冒充数组；OpenAction、destination 和 page xref 的间接引用均限制深度/对象大小/visited，generation 非 0 拒绝，page xref 必须是当前 PDF 的真实 `/Page`，目标数组严格为 `[page-ref /Fit]`。危险/远程/脚本/form/embedded/`Next`/未知字段继续 fail-closed。
- 解析前 `PDF_SOURCE_HASH_MISMATCH` 统一归一为 canonical `SOURCE_HASH_MISMATCH`，写入 v1 `failed`、`source_hash_state=mismatch` 与原 canonical hash，并禁止该失败路径刷新 generation marker。
- Spec043 `analysis._full_source_for_project` 增加窄读门禁：canonical record 必须是 `source_hash_state=verified`、`indexed_source_sha256=source_sha256`、v1 chunker `indexed`/100%/无错误；因此其他文档随后合法刷新共享 generation marker 也不能复活该文档的旧 ready manifest。未新增 API、task 或第二套存储协议。

### P1 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/kb/test_kb_pdf_safety_publication.py` | 0 | 24 passed，5 warnings |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_analysis_evidence.py` | 0 | 11 passed |
| `.venv/bin/python -m pytest -q tests/kb/test_kb_pdf_safety_publication.py tests/kb/test_kb_document_reindex.py tests/kb/test_kb_candidate_rebuild.py tests/literature_maps/test_map_analysis_evidence.py` | 0 | 110 passed，5 warnings |
| `.venv/bin/python -m pytest --collect-only -q tests/kb/test_kb_pdf_safety_publication.py tests/kb/test_kb_document_reindex.py tests/kb/test_kb_candidate_rebuild.py tests/literature_maps/test_map_analysis_evidence.py` | 0 | 110 tests collected |
| `python scripts/check_test_naming.py` | 0 | test naming check passed |
| `python -m py_compile backend/app/knowledge_base/infrastructure/parse.py backend/app/knowledge_base/infrastructure/index.py backend/app/knowledge_base/infrastructure/manifest_store.py backend/app/knowledge_base/infrastructure/migration.py backend/app/literature_maps/application/analysis.py` | 0 | compile passed |
| `git diff --check` | 0 | whitespace check passed |

新增回归包括真实临时 PDF 的 literal-string 伪造 safe action、页 generation `999/65535`、重复 `/D` 最后值（合法/非法）以及解析前 hash mismatch；map gate 测试先将 canonical v1 持久标记为 mismatch，再执行合法 generation refresh，仍拒绝 full source。未运行全量 pytest、真实 API/provider/reindex、部署或全库重建。

## 交接

交给 reviewer/tester 前，建议复核 `parse.py` resolver 的直接/间接字典键识别、`publish_index_state()` 的 schema 约束，以及故障注入时 marker 不被刷新为合法中间态。root 仍需在当前部署版本完成真实单文档 API E2E 后，才可推进 Spec043/Spec018 收口。
