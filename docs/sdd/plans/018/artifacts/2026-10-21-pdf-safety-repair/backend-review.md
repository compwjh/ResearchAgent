# Spec018 PDF 安全与单文档发布修复：backend-review

- 日期：2026-10-21（Asia/Shanghai）
- 角色：独立 backend reviewer / 安全技术评审
- 模型：当前执行 Agent（不固化模型代号）
- 范围：只读实际 `backend/app/knowledge_base/infrastructure/{parse.py,index.py,manifest_store.py,migration.py}`、相关 generation/全文 gate 路径及 `tests/kb/test_kb_pdf_safety_publication.py`；不修改业务代码、不部署、不调用真实 provider/数据、不提交。
- 依据：`repair-contract.md`、历史 `tech-review.md`、最新 `backend-report.md`。历史技术 BLOCK 保留在 `tech-review.md`，本报告只追加本轮实现复审事实。

## 定向验证

运行：

```text
.venv/bin/python -m pytest -q \
  tests/kb/test_kb_pdf_safety_publication.py \
  tests/kb/test_kb_pdf_provenance.py \
  tests/kb/test_kb_document_reindex.py \
  tests/kb/test_kb_tasks.py
```

结果：**64 passed, 5 warnings, 3.19s**。未运行全量 pytest、真实 API reindex、GAT 恢复、Spec043 全文分析/问答、部署或 provider。

## 已确认通过的实现面

### 被动 PDF resolver

- `backend/app/knowledge_base/infrastructure/parse.py:64-66,111-176` 实际实现了 4 层间接引用上限、visited xref 循环拒绝、单对象 16KiB、目标数组最多 8 项，以及当前文档真实 page xref + `/Fit` 的最小白名单。
- `parse.py:179-267` 对 action 字典只允许 `Type/S/D` 的受控 GoTo 形状；`Next`、未知键、named/string/远程或文件目标不进入 safe。`parse.py:526-570` 保留全 xref 被动扫描，并对 Catalog 外的 `OpenAction` 直接拒绝；`parse.py:78-98,562-569` 先解码 PDF name `#xx` 变体再扫描危险 token。解析路径没有 action 执行、导航、附件加载或网络调用。
- `tests/kb/test_kb_pdf_safety_publication.py:47-131` 覆盖基本危险动作、间接 GoTo/Fit、裸数组、`Next`、未知键、非本页 xref、循环、超大对象、AcroForm/EmbeddedFiles；本轮 64 项全部通过。

补充探针确认：用手工 raw PDF 放入重复 `/D` 键时，PyMuPDF 的 `xref_get_key()`/`xref_object()` 会规范化并保留最后一个值；最后值为 literal/畸形引用时分别得到 hostile/unavailable，最后值为合法数组时得到 safe，未观察到仅由重复键造成的独立旁路。但仓库尚无该 fixture，仍需把规范化行为锁成精准测试。

### manifest → metadata/hash → marker

- `index.py:421-447,508-587` 将 manifest 写入、窄 schema metadata/hash 写入、generation refresh/require 与 manifest/source hash 复核按顺序串联，并让失败状态保持 gate 不可读。
- `migration.py:420-501` 的 `publish_index_state()` 只允许受控状态与既有 hash 字段，执行 schema 校验及原子 metadata 写；`manifest_store.py:34,50-59` 复用同一 `RLock`，避免并发发布交错。
- `manifest_store.py:154-185,212-232,667-697` 对 manifest mapping version、schema、hash/digest 与 marker 做 fail-closed 校验。`tests/kb/test_kb_pdf_safety_publication.py:155-286` 的 partial、v2/v1、manifest write、metadata write、generation refresh、索引后 source 变更故障注入均通过。

### 旧 partial 与版本边界

- `parse.py:52` 的 parser 版本仍为既有 `pymupdf-display-dict-insertion-v2`，`provenance.py:35` 的 mapping 版本仍为 `source-anchor-v2`；本修复没有偷偷改变 schema/generation 版本或触发全库重建。
- 旧 manifest 不会被读取时静默改成 ready：`manifest_store.py:154-164,212-222` 仍严格校验当前 mapping version，`routes_kb.py:744-850` 对已有 partial 直接返回其真实状态；只有显式 `POST /kb/documents/{document_id}/reindex`（`routes_kb.py:887-935`）才产生新 manifest。版本不匹配转为 `INDEX_REBUILD_REQUIRED`，因此“不全库升级”在安全上是 fail-closed 的，代价是旧 partial 需显式重建。

## 阻塞问题

### P1 — 解析前源文件变化会保留旧 ready manifest，并让 generation gate 继续通过

证据链：

1. `parse.py:596-607` 在源文件已经改变时抛出 `PDF_SOURCE_HASH_MISMATCH`（注意前缀为 `PDF_`）。
2. `index.py:625-671` 将异常字符串直接传给 `_fail()`；`index.py:611-619` 只有错误字符串恰为 `SOURCE_HASH_MISMATCH` 才关闭 marker 刷新。
3. 因而 PDF 的解析前 mismatch 会进入 `_mark_index_failed(..., error="PDF_SOURCE_HASH_MISMATCH", refresh_marker=True)`；`index.py:476-480` 不写 `source_hash_state="mismatch"`，而 `index.py:491-492` 刷新 generation marker。已有 ready manifest 不会被删除或标记失效。
4. 全文依据路径 `backend/app/literature_maps/application/analysis.py:128-149` 只读取 owner-scoped metadata 的 `source_sha256`、generation marker 和 manifest 的 ready/verified/hash 字段，不重新计算源文件 hash，也不检查对应 chunker 已进入 failed。因此源文件被改写或删除后，旧 ready manifest 仍可能作为全文依据返回。

可复现临时目录探针（fake client、无 provider/生产数据）：先成功索引一个 PDF，再在第二次索引前追加字节。结果为：

```text
first_status: indexed
second_status: failed
chunkers.v1.error: PDF_SOURCE_HASH_MISMATCH
source_hash_state: verified
manifest_status: ready
FinalizeBundleStore.require_generation(): run_id=probe  # 通过
```

这不是“本次 worker 返回成功”，而是失败后系统仍保留并暴露旧的 ready/verified 全文证据，违反 `repair-contract.md:15,19-20` 的源 hash 变化 fail-closed 及“任何中间态不得被全文 ready 读路径接受”要求。应在修复实现中将 parser/source-read 侧的 mismatch/缺失统一归一到关闭 marker、写 mismatch/受控 failed，或在全文 gate 对当前 canonical source 做不可绕过的 hash 复核；不能依赖旧 manifest 继续可用。

### P1 — OpenAction 的正则提取会把 literal string 内伪造的安全目标误判为 safe

`backend/app/knowledge_base/infrastructure/parse.py:187-225` 用正则从整个 action 字典文本提取 `/S`、`/D`，而不是按 PDF lexical object 解析实际字典值。临时真实 PDF fixture 的 Catalog 为：

```text
<< /Type /Action /S /GoTo /D (literal /S /GoTo /D [4 0 R /Fit]) >>
```

PyMuPDF 返回的实际 `OpenAction` 仍是 `/D` literal string；但 `_inspect_active_features()` 返回 `safe`，`extract_pdf_provenance()` 返回 `ready`。字符串不是合法 page destination，按 `repair-contract.md:8-10` 必须 fail-closed；当前 `destination_match` 却捕获了字符串里的伪造数组。这不是 action 被执行，而是恶意 PDF 可伪造“已证明安全”的 provenance，直接破坏安全分类和全文证据门禁。

修复必须只接受结构化解析后的真实 dictionary `/D` 值：literal string、嵌套 dict、注释/字符串中的伪造 `/S`/`/D`、重复/未知内容不得由 first regex match 放行；需要补真实 fixture 与 no-execution/no-network 断言。

### P1 — page reference 丢弃 generation，错配的间接引用会被放行

`parse.py:162-175` 的正则捕获 `page number` 和 `generation`，但 `parse.py:170` 只转 `match.group(1)`，`match.group(2)` 未校验即丢弃；因此真实 fixture `[4 999 R /Fit]`、`[4 65535 R /Fit]` 均返回 `ready`，与 `[4 0 R /Fit]` 无差别。PDF 间接引用的 generation 是引用身份的一部分，错配引用不是“真实本文件页引用”；按合同的真实 page reference/格式异常 fail-closed 要求，不应进入白名单。需要从 PyMuPDF/底层对象确认实际页引用 generation（当前文档页通常为 0），对错配或无法证明的 generation 返回 unavailable/hostile，而不是只按 xref 整数放行。

## 非阻塞但需补齐的测试证据

- 当前 64 项未覆盖 PDF name 编码变体（例如 `Java#53cript`、`Op#65nAction`）的真实构造，也没有 spy/monkeypatch 明确断言“不执行 action、不联网”。静态实现路径是被动 `xref_object`/正则扫描，未见执行或网络调用，但合同要求的安全矩阵仍应补用例；上述 literal string 与 generation 错配已是 P1，不是单纯测试缺口。
- 当前 64 项覆盖的是“向量写入后”源变化（`test_kb_pdf_safety_publication.py:266-286`），没有覆盖本报告 P1 的“解析前/旧 ready manifest 存在时”源变化；修复后必须增加该能力测试。

## 最终裁决

**BLOCK（P1，不得进入真实 GAT 恢复/部署门禁）。**

manifest/metadata/generation 故障注入及旧 partial 不静默升级达到合同方向，64 项定向测试通过；但当前仍有三项 P1：解析前源变化留下旧 ready manifest 且 generation 仍通过；literal string 伪造安全目标会误判 ready；page reference generation 错配会放行。修复并补上这些场景后，需重新运行受影响精准测试，再进行独立复审；本轮未改代码、未部署、未调用真实 provider/数据。

**独立 backend reviewer / 安全技术评审：BLOCK（2026-10-21）。**

---

## 2026-10-21 P1 修复最终窄复审

本节追加并 supersede 上方实现复审 BLOCK；历史 BLOCK 文本保留用于追溯。复审依据最新 `backend-report.md`、`repair-contract.md`、实际实现与新增精准测试，不扩大到全库迁移、公开 API、持久 task、真实 provider 或部署。

### 原三项 P1 逐项闭合

| 原阻塞 | 实际实现与测试证据 | 结论 |
|---|---|---|
| source mismatch 在解析前留下旧 ready 证据 | `index.py:351-356` 将 `PDF_SOURCE_HASH_MISMATCH` 归一为 `SOURCE_HASH_MISMATCH`；`index.py:619-628` 因此不刷新 marker；`index.py:482-500` 写入 v1 `failed`、canonical `indexed_source_sha256` 与 `source_hash_state=mismatch`。`test_kb_pdf_safety_publication.py:347-381` 覆盖该路径。临时旧 ready manifest 探针结果为 `state.error=SOURCE_HASH_MISMATCH`、`source_hash_state=mismatch`、刷新前 generation=`INDEX_FINALIZE_REQUIRED`；随后合法刷新共享 marker 后 generation 可用，但 manifest 仍 ready。 | **PASS** |
| literal/nested/重复内容伪装 typed action，或 page generation 错配放行 | `parse.py:79-227` 使用有界类型化 PDF value parser（string/dict/array/ref/name、注释与嵌套字符串处理），`parse.py:326-356` 只接受实际 dict 的 `Type/S/D`；`parse.py:296-323` 严格要求 destination 数组两项、page ref generation=0、真实 `/Page`。`test_kb_pdf_safety_publication.py:105-133` 覆盖 literal、raw duplicate final-value；`113-117` 覆盖 999/65535 generation；24 项安全发布测试及全集合均通过。 | **PASS** |
| manifest→metadata/hash→marker 失败闭环与 full gate | `index.py:516-594` 保持 manifest→窄 metadata/hash→refresh/require→manifest/source recheck 顺序；`migration.py:420-501` 只接受受控字段和原子 schema 写。`analysis.py:135-169` 现在还要求 canonical `source_hash_state=verified`、indexed hash 等于 source hash、v1 `indexed`/100%/无 error，再通过 generation/manifest gate。`test_map_analysis_evidence.py:220-248` 先持久写入 mismatch，再合法刷新共享 marker，full source 仍拒绝；110 项受影响测试全通过。 | **PASS** |

### 旧 partial / 版本及旁路核对

- `parse.py:652-698` 继续只被动读取对象，不执行 action、导航、附件或网络；危险名称/编码变体和 Catalog 外 `OpenAction` 仍由全 xref 扫描 fail-closed。
- `manifest_store.py:154-164,212-222` 保持 mapping/schema/hash 校验；`routes_kb.py:744-850` 不把已有 partial 静默改为 ready，只有显式 reindex 才生成新清单。未引入全 KB 版本升级或第二套存储协议。
- 手工 raw duplicate-D fixture 显示 PyMuPDF 规范化为最后值；类型化解析也按最后值处理，当前未发现重复键旁路。该行为已纳入 `test_pdf_duplicate_destination_uses_final_dictionary_value`。
- `project_id=None` 的 shared-pool 合法语义未被本修复收窄；full gate 仍以 owner-scoped `list_documents_for_project` 加现有 generation/manifest 条件判定，相关 shared-pool 测试仍通过。

### 定向验证与未覆盖运行门禁

独立运行：

```text
.venv/bin/python -m pytest -q \
  tests/kb/test_kb_pdf_safety_publication.py \
  tests/kb/test_kb_document_reindex.py \
  tests/kb/test_kb_candidate_rebuild.py \
  tests/literature_maps/test_map_analysis_evidence.py
```

结果：**110 passed, 5 warnings, 12.36s**。backend-report 记录的命名检查、py_compile、git diff check 亦为 0。未运行全量 pytest、真实 API reindex、真实 GAT 恢复、Spec043 全文分析/问答、provider、部署；这些仍是 root 的后续运行时门禁。当前测试没有通过网络 spy 证明，但解析实现无网络/执行调用点，危险与伪装 fixture 已由精准测试覆盖。

## 最终裁决

**GO（backend implementation review 通过，可进入真实 GAT/Spec043 运行门禁）。**

原先三项 P1 均有实际代码、精准测试和临时状态探针证据闭合；尤其 canonical mismatch 不再依赖暂时 marker/live 差异，其他文档合法刷新共享 marker 后，`analysis.py` 的持久状态 gate 仍拒绝旧 ready manifest。后续运行时验证不得被本报告 GO 替代；若真实 API、GAT 恢复或全文 evidence gate 失败，应另行记录新的运行阻塞。

**独立 backend reviewer / 安全技术评审：GO（2026-10-21，最终窄复审）。**
