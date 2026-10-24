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

## 2026-10-21：Spec043 Task05 全文门禁关联阻塞的只读诊断

- 触发证据：`docs/sdd/plans/043/artifacts/task-05/api-e2e.md` 的真实运行 `20261021-015442-dd616d5-v1-reindex`。
- 目标范围：map `0baabeae7268429c9f7e4de8098ae1d0`、node `21041260a5394f42891b020128fa60fa`、document `55afc3b8f01445429462fe78ed0d4c98`。
- 约束：只读 canonical metadata、association sidecar、map import/analysis 代码和既有测试；未启动服务、未下载、未调用 provider、未重索引、未写生产关联、未修改业务代码。

### 结论

这是“导入链没有建立知识库项目关联”叠加“unbound map 的 shared-pool 关系在现有 sidecar schema 中无法表示”，不是目标文档的 owner key 偏差，也不是 hash/manifest/generation 失败：

1. 本地只读 canonical 检查得到受控统计：目标记录存在（canonical 总记录 51）；目标 `status=indexed`、`source_hash_state=verified`、`source_sha256 == indexed_source_sha256`；association sidecar 存在但关系数为 0；目标无 association；修复前实现的 `list_documents_for_project(None, owner)` 返回 0 条且不包含目标。
2. 最新 API 证据与此一致：node 的 `document_id` 精确匹配目标，map/document 的 `project_id` 均为 null；v1 manifest 已 `ready`、100%、verified、mapped 57/unmapped 0，generation 通过，但全文 source version 仍为 null，故 `fulltext_ready=false` 是正确的 fail-closed 结果。
3. `LiteratureMapImportBridge._persist()` 只调用 `update_node_import_result()`，它只更新 map node 的 `document_id`、下载状态和受控导入诊断；runtime 的 `_existing_paper_import()` 只经过既有 paper-import/KB canonical 创建与索引链，没有调用 `set_document_project()`。因此当前 sidecar 为 0 是“未写入关联”，不是已写入后被错误 owner 过滤。
4. `set_document_project(document_id, project_id, owner_id=...)` 的现有安全路径只能写非空 project ID；传 `None` 的语义是删除关系。`_load_associations()` 也拒绝非字符串/空 `project_id`。但 `list_documents_for_project(None, owner)` 与 map analysis 明确把 `None` 定义为 owner-scoped shared pool。故不能用 `set_document_project(target, None)` 修复：它会保持/造成无关联，不能产生授权关系。

### 既有代码与测试交叉证据

- `backend/app/literature_maps/application/service.py` 的 `import_node()` 只按 owner 读取 node、校验冻结 source URL，再委托 bridge；没有 map project 到 KB association 的后处理。
- `backend/app/literature_maps/application/runtime.py` 组装 bridge 时只注入 importer、map store、`OWNER_ID` 和 source resolver；没有 association writer/context。
- `backend/app/knowledge_base/application.py` 的 association reader 只按 sidecar 中的 owner/project relation 返回记录；canonical `papers.json` 的 `project_id` 只是历史兼容清理/展示 overlay，不是授权字段。
- `tests/system/test_project_document_context.py::test_project_visibility_excludes_other_project_documents` 已证明未关联记录不会因为 `project_id=None` 自动进入 shared 查询；这保留了 owner 隔离，但也暴露了 unbound map 的落盘表达缺口。
- `tests/literature_maps/test_map_analysis_evidence.py::test_shared_pool_full_analysis_and_conversation_keep_owner_scope` 使用受控 `list_documents_for_project` seam 验证了 shared-pool 分析意图；它没有覆盖真实 sidecar 如何写入 owner-scoped shared relation。
- `tests/literature_maps/test_map_import_bridge.py::test_bridge_calls_existing_importer_and_persists_real_document_handle` 只断言 importer 和 node handle 持久化，没有断言项目关联；现有测试因此不会发现本次真实 API 阻塞。

### 最小同范围修复方向（待 root 确认，不在本轮编码）

#### 方案 A：项目绑定地图，复用现有 association 门禁（优先的最小路径）

在用户明确把 map 绑定到 owner 可见 project 后，沿现有 `set_document_project(document_id, map.project_id, owner_id)` 建立关系；调用前必须由既有 map/project owner 校验确认 project 属于当前 owner，且导入成功与 `existing=true` 两条路径都要幂等关联。可以在 service 的已验证 map context 之后注入窄 association callable，或扩展 bridge 的受控 context；不得从 node.document_id 单独推定授权，不得把 project_id 写回 closed canonical schema。

该路径不扩大 unbound map 的语义：若 map 仍为 `project_id=null`，全文应继续保持不可用，直到用户显式选择 owner 可见 project，或者 Spec043 明确批准 shared-pool 数据模型变化。

#### 方案 B：为 unbound map 增加 owner-scoped shared relation（需要 Spec043/数据契约确认）

若产品确实要求未绑定 map 直接使用全文，必须在既有关联存储上增加窄的 owner-scoped shared 表达（例如受 schema 校验的 `project_id=null` relation），并同步修改 `_load_associations()`、`set_document_project()`、`list_documents_for_project(None, owner)` 与 043 analysis gate 的读取契约。迁移、旧 sidecar、删除/转绑定、跨 owner 读取和回归都必须 fail-closed；不能通过“所有未关联 canonical 文档都属于 shared pool”或直接信任 node.document_id 来绕过。

在 root 确认 Spec043 该数据模型方向前，本角色不修改 sidecar schema 或 analysis gate。若选择方案 B，需先补 requirement/tech 范围与 migration/test 契约；若不选择，方案 A 的显式 project bind 是现有 API 能安全补关联的唯一窄路径。

### 建议的受控回归

- project-bound 成功导入：验证 map owner/project 校验、canonical document handle、sidecar relation 的 owner/project、`list_documents_for_project(project_id, owner)` 可见；重复导入不产生第二关系。
- project-bound 跨 owner/跨 project：验证 relation 不可被另一 owner 读取或覆盖，node.document_id 不能单独放行全文。
- unbound map 当前契约：无 association 时仍返回 `fulltext_ready=false`，不因 canonical `indexed/verified` 或 shared generation refresh 复活。
- 若批准方案 B：仅 owner-scoped null-project relation 可进入 `list_documents_for_project(None, owner)`；另一 owner、任意未关联 canonical 文档、删除/解绑和旧 sidecar 均拒绝或不可见。
- 保留本次 `dd616d5` 的 hash/manifest/generation 证据；不重复 reindex，补关联后只做受控 source-status/fulltext E2E。

### 初始诊断状态

已定位到真实阻塞与最小安全分叉；没有把 node.document_id 当作授权凭据，也没有写入生产 association。后续 root 已确认不扩展 sidecar schema，采用“None 仅 canonical 无 association 条目”的窄读契约，详见下节。

## root 确认后的最小窄修复（2026-10-21）

root 确认不扩展 sidecar schema，也不为 unbound map 伪造 `project_id=null` relation；既有合同解释为：`project_id=None` 只返回 canonical 中完全没有 association 条目的记录。任何 sidecar relation（无论其 owner 或 project）都必须排除；指定 project 继续要求 relation 的 `project_id` 相等并通过 owner 精确匹配。

已按该方向实施的唯一 backend 行为变更：`backend/app/knowledge_base/application.py::list_documents_for_project()` 改为显式分支遍历。None 分支只接受 `document_id` 不在 association map 的 canonical v1 记录，并返回展示用 `project_id=None`；project 分支保留原有 relation + owner 过滤。没有修改 `_load_associations()`、sidecar schema、`set_document_project()`，没有写生产 association，也没有从 node.document_id 推定授权。`backend/app/literature_maps/application/analysis.py` 仅同步更新 shared-pool 语义注释。

新增回归 `tests/system/test_project_document_context.py::test_unbound_visibility_includes_only_unassociated_documents`，覆盖：一个真正 unbound 文档可见；两个不同 owner/project 的已关联文档均不进入 None；正确 owner 的 project 可见，另一 owner 不可见。既有项目隔离和 map analysis 回归保持通过。

验证记录：

- `./.venv/bin/python -m pytest tests/system/test_project_document_context.py tests/literature_maps/test_map_analysis_evidence.py`：退出码 0，19 passed。
- `./.venv/bin/python scripts/check_test_naming.py`：退出码 0。
- `./.venv/bin/python -m py_compile backend/app/knowledge_base/application.py backend/app/literature_maps/application/analysis.py`：退出码 0。
- `git diff --check`：退出码 0。
- 未启动服务、未调用 provider、未下载、未重索引、未写生产 metadata/association、未运行全量回归或 commit。
