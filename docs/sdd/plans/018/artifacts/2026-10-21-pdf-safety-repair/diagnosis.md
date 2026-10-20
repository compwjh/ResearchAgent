# Spec018 PDF 安全与 reindex 状态发布只读诊断

- 诊断日期：2026-10-21（Asia/Shanghai）
- 范围：真实文档 `55afc3b8f01445429462fe78ed0d4c98`、PDF 被动对象解析、Spec018 解析/manifest 合同、单文档 reindex worker 状态发布。
- 角色：backend-dev（只读诊断）
- 结论状态：已定位；等待 root 更新并确认 Spec 后再编码。
- 约束：未执行 PDF action、未跟随链接、未联网；未读取 PDF 正文；未修改业务代码、索引、metadata、manifest 或数据库；未部署、未运行全量回归、未 commit。

## 结论

真实 GAT PDF 的 `HOSTILE_FEATURES_NOT_EXECUTED` 触发源是一个普通的 Catalog `OpenAction` 页内导航，不是 JavaScript、表单、附件或远程行为：

- Catalog 的唯一 active 键为 `OpenAction`，引用的 action dictionary 为 `/S /GoTo`。
- 该 action 的 `/D` 是一个内部页目标数组，包含页引用和 `/Fit` 目标；没有 `/S /JavaScript`、`/Launch`、`/SubmitForm`、`/ImportData`、`/GoToR` 或 `/RichMedia`。
- Catalog 没有 `AA` 或 `AcroForm`；`Names` 只指向 Dests 名称树，没有 `EmbeddedFiles`。
- 全文档受控对象扫描未发现 `JavaScript`、`JS`、`XFA`、`RichMedia`、`Launch`、`SubmitForm`、`ImportData`、`GoToR` 等危险键/动作名。页面链接统计为 189 个页内目标和 7 个 URI 目标，没有文件/Launch/GotoR 链接。

因此当前 parser 对该文档的判定是安全边界上的误报：`OpenAction` 被存在性一刀切为 hostile，未进一步区分内部 `/GoTo` 与真正会执行脚本、提交表单、打开文件或访问远程资源的动作。不能因此放宽 `analysis.py` 的全文 evidence gate，也不能把已有 `partial` manifest 改成 `ready`。

## 证据链

### 1. Spec018 的安全与证据合同

Spec018 明确要求：

- hostile PDF 只验证 parser 不执行 JavaScript、表单动作、附件或远程资源，不发起网络请求（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md` 的 PDF provenance 门禁段）。
- manifest `status` 的 `ready/partial/failed` 必须反映真实 provenance；`partial` 不能伪装成 `ready`。
- `source_sha256` 是当前原件摘要；只有同一索引构建前后核对成功才将 `indexed_source_sha256` 写入并将 `source_hash_state` 设为 `verified`。
- 全文分析只接受 `status=ready`、进度 100、verified hash、source/index hash 一致且 generation 可验证的 manifest。这个门禁应保持不变。

### 2. 真实 PDF 的被动对象统计

被动使用 PyMuPDF 的 `pdf_catalog()`、`xref_get_key()`、`xref_object()` 和页面链接枚举完成统计；没有调用 action 执行、导航、资源加载或网络 API。只保留受控键名、动作名和数值统计：

- 文档：12 页，xref 总数 484。
- Catalog：存在 `OpenAction`；无 `AA`、无 `AcroForm`。
- `OpenAction`：引用 xref 69；对象键为 `S`、`D`；`S` 的受控值为 `GoTo`；`D` 为内部页引用 + `/Fit` 目标数组。
- Catalog `Names`：引用 Dests 名称树；未见 `EmbeddedFiles`。
- 页面链接：kind 2/URI 共 7 个；kind 4/页内目标共 189 个；文件、Launch、GoToR 均为 0。
- 全 xref 的 active 正则命中只有 Catalog 的 `OpenAction` 1 次；没有 JavaScript/JS、XFA、RichMedia、Launch、SubmitForm、ImportData、GoToR 等命中。

当前 live 产物的受控状态也与该判断一致：

- canonical metadata：整体 `indexed`；v1/v2 均 `indexed`、100%、error 为空；顶层 `indexed_source_sha256=null`、`source_hash_state=legacy_unknown`。
- v1 manifest：`partial`、100%、`HOSTILE_FEATURES_NOT_EXECUTED`，57 chunks，mapped 57、unmapped 0；manifest source/index hash 相等且 `verified`。
- v2 manifest：`partial`、100%、`HOSTILE_FEATURES_NOT_EXECUTED`，92 chunks，mapped 81、unmapped 11；manifest source/index hash 相等且 `verified`。v2 的 11 个 unresolved mapping 是独立的 provenance 缺口，不能通过放宽 hostile 判定掩盖。
- generation marker 与当前 live manifest digest 的只读校验通过；本问题不是 generation/alias 门禁漂移。

### 3. Parser 的最小误报点

`backend/app/knowledge_base/infrastructure/parse.py`：

- `_ACTIVE_ACTION_RE`（约 64–68 行）把 `/OpenAction` 与真正危险的 action/form/embedded 名称放在同一正则中。
- `_inspect_active_features()`（约 327–349 行）对 Catalog 的 `OpenAction`、`AA`、`AcroForm` 只判断“非 null 即 hostile”（约 339–342 行），随后扫描所有 xref 的正则命中（约 343–346 行）。这使普通内部 `/S /GoTo` 也被拒绝。
- `extract_pdf_provenance()`（约 458–505 行）在有文本块且 active 状态为 hostile 时固定返回 `partial/HOSTILE_FEATURES_NOT_EXECUTED`。所以目标 PDF 的 partial 是 parser 直接产生的，不是 map analysis 或 manifest builder 虚构的错误。

### 4. Worker 的 metadata/manifest 不一致点

`backend/app/knowledge_base/infrastructure/index.py` 的 `index_paper_chunker()` 当前顺序为：

1. 解析 provenance、生成 bundle 和 chunks。
2. Qdrant upsert 成功后，约 549–557 行先把 chunker metadata 写成 `STATUS_INDEXED`、100%、error `None`。
3. 约 558–562 行才调用 `_publish_inspection_manifest()`。
4. `build_inspection_manifest()`（`inspection.py` 约 320–345 行）会保留 bundle 的 `partial` 状态和错误，并固定写 `indexed_source_sha256=source_hash`、`source_hash_state=verified`。

因此真实结果必然可能是“metadata indexed + manifest partial”。这不是安全门禁过严造成的第二个问题，而是 worker 在 manifest 结果已知前提前发布了 indexed 状态。

hash 未同步的最小原因是：

- `store.update_chunker_state()`（`store.py` 约 744–781 行）只更新 `chunkers`，并把 v1 状态复制到兼容顶层 `status/chunk_count`；没有 `indexed_source_sha256/source_hash_state` 参数或写入逻辑。
- `_publish_inspection_manifest()` 只写 manifest 并刷新 generation live digest（`index.py` 约 404–435 行），没有回写 canonical metadata。
- `patch_knowledge_document()`（`migration.py` 约 403–417 行）是严格 metadata 写入口，但当前允许字段只有 `status/page_count/chunk_count/chunkers/error`，不允许 hash 状态；直接 reindex worker 也没有调用它。

`submit_document_reindex()`（`application.py` 约 801–849 行）只生成返回用的 UUID，实际任务由 `tasks.py` 的进程内 `_running` + `Future` 管理。这个 task id 没有持久终态，是可独立修复的可观测性缺口，但不是本次全文 gate 拒绝的根因。

## 最小同范围修复建议（不在本轮实施）

### A. 解析安全判定

将 `OpenAction` 从“存在即 hostile”改为结构化、只读、白名单判定：

1. 继续对 `AA`、`AcroForm`、`JavaScript/JS`、附件/嵌入资源、`Launch`、`SubmitForm`、`ImportData`、`GoToR`、`RichMedia` 以及未知/无法解析的 active 结构 fail-closed。
2. 仅允许 Catalog `OpenAction` 是内部 `/S /GoTo`，且 `/D` 是可验证的内部页目标（包括本例的页引用 + `/Fit` 目标数组；如支持 named destination，也只允许其最终形态为内部页目标）。不执行 action、不调用导航、不加载资源。
3. 裸内部 destination array 可按同一页目标规则放行；未知 action、远程目标、文件目标、脚本、表单提交等仍保持 hostile 或 unavailable 的现有失败语义。
4. xref 扫描应避免仅凭 `OpenAction` 名称本身触发；危险 action 名仍需保留。若无法可靠读取对象字典，返回 `unavailable`，让 provenance 继续 `failed/PDF_PROVENANCE_UNAVAILABLE`。

这只减少普通内部页导航的误报，不改变“绝不执行 PDF action、绝不联网”的安全保证，也不改变 hostile fixture 的 partial 结果。

### B. Worker 状态与 hash 发布

保持现有 Qdrant/generation 绑定和 fail-closed 规则，只调整发布顺序与字段契约：

1. `_publish_inspection_manifest()` 返回已校验、已写入的 manifest 摘要（至少 `status/error/indexed_source_sha256/source_hash_state`）。
2. Qdrant upsert 成功后先发布 manifest；manifest 写失败时只进入 `failed`，不得先留下 `indexed`。
3. 按 manifest 状态发布 chunker metadata：`ready → indexed`；`partial → indexed_partial` 并保留稳定错误码；`failed → failed`。不得把 partial 转为 ready。兼容顶层状态仍按既有“跟随 v1”约定，不把 v2 状态误写到顶层。
4. 在 manifest 已成功发布、source/index hash 已核对一致后，通过严格 canonical metadata 写入口同步 `indexed_source_sha256` 和 `source_hash_state=verified`。建议扩展 `patch_knowledge_document()` 或新增同一层的窄 helper，仅允许这两个明确字段及受控状态更新；禁止用未经 schema 校验的 `save_papers()` 拼写新状态。
5. metadata 状态/hash 写完后再次刷新并校验 generation live digest；不要让 manifest 已变更但 marker 仍指向旧 metadata digest。若任一 metadata 提交失败，保持 fail-closed，不向 map analysis 暴露 ready。
6. 对 partial hostile PDF，允许 metadata `source_hash_state=verified` 与 chunker `indexed_partial` 同时存在：前者只证明索引使用的字节与当前不可变原件一致，后者仍明确表示 provenance 不能作为全文 ready 证据。

任务终态若要对外可查询，应另加持久化、可恢复的 reindex task record；不要继续把仅存在于进程内的 `task_id` 当作终态凭据。该项可作为同一 worker 修复的独立小节，但不能替代 manifest/metadata 状态修复。

## 测试方案（实现后由 backend-dev/backend-tester 执行）

### Parser 安全回归

- 新增一个只含内部 Catalog `OpenAction` `/S /GoTo` + 页目标数组的 PDF fixture：期望 `ready`，无错误；用 spy 证明没有 action 执行、导航或网络调用。
- 保留并加强 `pdf-hostile-features` fixture：含 JavaScript、表单/附件等真实 hostile 能力时仍为 `partial/HOSTILE_FEATURES_NOT_EXECUTED`，不得因放行 GoTo 而变为 ready。
- 新增/补齐未知 action、`GoToR`、`Launch`、`SubmitForm`、`ImportData` 的构造样本：仍为 hostile/partial；无法解析 action 时仍为 unavailable/failed。
- 现有 benign URI annotation 测试继续通过；URI 统计不得触发 fetch。
- 对真实 GAT 文档只做脱敏受控断言：页数、active key/action 类型、链接类别与计数；不把正文或路径写入测试输出。

### Worker 发布回归

- 用 canonical document + fake Qdrant + 可注入 bundle 覆盖 `partial/HOSTILE_FEATURES_NOT_EXECUTED`：断言 manifest 为 partial，metadata 对应 chunker 为 `indexed_partial`/100%/同一稳定 error，canonical hash 为 verified 且 indexed hash 等于 source hash。
- 覆盖 ready bundle：断言 metadata `indexed` 与 manifest `ready` 一致，hash 同步，generation marker/live digest 复核通过。
- 覆盖 manifest 写失败：断言 metadata 不会先变成 indexed；任务最终为 failed，hash 不会在 manifest 未提交时伪造为 verified。
- 覆盖 v2 partial 时顶层兼容字段仍只跟随 v1，避免把 v2 状态错误覆盖到旧 API 顶层。
- 若实现持久 task record，再覆盖 202 返回的 task id 可在 worker 完成、partial、failed 和重启后读取同一终态；否则保留为后续独立缺口，不把当前 UUID 当成功证据。

## 风险与停止条件

- 放行范围必须严格限定为内部页内 `/GoTo` 目标；任何 remote/file/script/form/embedded/unknown 结构都不能放行。结构判定不应通过执行 action 或解析外部资源完成。
- 状态发布顺序调整后，manifest 写失败可能留下已 upsert 的派生向量但 metadata 为 failed；这是 fail-closed 的可见结果，不能为追求清理便利而放宽门禁。若需要补偿删除，必须另按 Spec018 的索引写入/补偿合同设计。
- hash 同步 helper 必须走 canonical schema 校验、原子写和 generation digest 更新，不能仅修改 JSON 字段绕过既有 metadata 合同。
- 在 root 更新 Spec、完成需求/技术评审并明确确认前，本角色不修改 `parse.py`、`index.py`、`store.py`、migration schema、测试或真实数据。

## 本轮验证记录

- 被动 PyMuPDF 对象/链接统计：退出码 0；未执行 action、未联网。
- 受控读取 live metadata、v1/v2 manifest、generation marker：退出码 0；未写入。
- 未运行测试（本轮为只读诊断，且禁止修改后进行实现验证）。
