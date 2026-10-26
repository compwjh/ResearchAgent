# Spec 038 补充技术评审：记忆管理与 Markdown 真相源复接

## 评审元数据

- **评审对象**：`docs/sdd/specs/038-memory-layer-redesign.md` 的 2026-10-26 管理复接补充
- **关联计划**：`docs/sdd/plans/038/2026-10-26-management-reconnect-plan.md`
- **接口合同**：`docs/sdd/plans/038/2026-10-26-management-contract.md`
- **评审者**：architect（独立评审）
- **角色**：架构师（需求/技术门禁）
- **模型**：Luna max（用户本轮临时指定；不写入长期 agent 配置）
- **分派方式**：`Task(architect)`，未分派编码、测试、API 写入、模型调用或部署
- **评审时间**：2026-10-26（Asia/Shanghai）
- **评审范围**：复用边界、存储/锁/OCC、项目授权、审计与 PENDING 身份、路由/前端接缝、任务拆分和验证门

## 结论

**通过（GO；附 P1 实现门槛）。**

合同选择了与当前单进程实现相容的最小方案：固定 scope 门面、SHA-256 内容 revision、同路径 RLock + 原子替换、无 SQL schema 扩展、`MemoryAnalysisItem.item_id` 复用为 PENDING ID。没有恢复旧数据库真相，也没有把 API 扩展成任意文件服务。

以下问题必须在实现/验收前关闭，否则为 P1 不通过：

- 当前 `resolve_pending()` 的 remove-before-append 会在 append 失败时丢待确认项；必须 append-first，且目标 append 与重复重试幂等。
- 当前分析 worker 在 `write_memory_candidate()` 后才创建审计项；必须先预留审计项并把 `item_id` 传给 `add_pending()`，否则决策端无法可靠消费指定项。
- API 读路径不能复用 fail-open 的 `_read_text()` 并把权限/解码错误当空文件；必须增加固定文档的严格读写 seam，返回稳定 503。

这些是现有实现与已确认补充之间的接缝修复，不构成范围扩张；无需重新询问用户。未发现必须新增迁移、跨进程锁或第二套服务层的设计理由。

## 现有代码事实

1. `backend/app/memory/markdown_store.py:106–151` 已集中管理 `MEMORY_DIR`、`projects` 根和 project_id 白名单/realpath；`write_user()` 与 `_sync_memory_index()` 已提供原子写和现有索引钩子。
2. `markdown_store.py:357–421` 的 `add_pending()` 目前自行生成 12 位 ID；`resolve_pending()` 先在 PENDING 锁内写回删除项，再在锁外 `append_memory()`，因此 append 异常会造成条目丢失。
3. `backend/app/memory/models.py:158–168` 的 `MemoryAnalysisItem` 没有 `pending_id`；`migration.py` 的分析项表也没有新 pending 关联列。
4. `conversation_service.py:951–966` 目前先调用 `write_memory_candidate()`，后调用 `create_memory_analysis_item()`；`routes_conversations.py:2113–2143` 的决策路径对 save 只调用 `update_memory_analysis_item(... auto_saved)`，没有 `resolve_pending()`。
5. `repository.py:1546–1571` 已按 `(analysis_id, statement)` 去重创建审计项；可通过先创建/获取项再写文件来复用同一 `item_id`，不需要新 SQL 列。`update_memory_analysis_item()` 已有 pending→决策状态条件更新，可继续作为“文件动作成功后的审计投影”。
6. 当前 `MarkdownMemoryStore._read_text()` 是会话注入所需的 fail-open 读取；管理 API 需要另一条固定文档 strict seam，不能改变 snapshot fail-open 语义。
7. `frontend/app.js:3379–3427` 仍调用 `/api/memories*` 列表/创建/证据/确认/停用/删除/撤销；`frontend/index.html:392–435` 仍是 status selector + memory list，静态测试也把旧端点当成功契约。必须随前端 Task 更新，不能让 404 变成空列表。

## 技术决策矩阵

| 技术点 | 判定 | 冻结决策 |
|---|---|---|
| 文件 API 选择 | 通过 | 只新增 `GET/PUT /api/memory-documents`；global 固定 `MEMORY.md`，project 固定 `projects/<id>.md`；不收 path/owner/document。 |
| 内容 revision | 通过 | SHA-256(UTF-8 bytes) 小写 hex；PUT 在同路径锁内比较；stale 409；外部未持锁写入的绝对 CAS 不在单进程边界内承诺。 |
| 内容上限 | 通过 | 65,536 Unicode code points；原文保存；空串清空；不 trim、截断或归一化；测试 65,536/65,537。 |
| 项目授权 | 通过 | `repo.get_project(project_id, OWNER_ID)`；`None` 统一 404；`status != active` 409；先校验 ID/realpath，失败不创建文件。 |
| 错误体 | 通过 | 稳定 `{detail:{code,message,retryable,...}}`；参数错误映射 400，不能把 Pydantic 422 当公开合同；读写故障 503。 |
| SQLite/MD 真相 | 通过 | MD 唯一内容真相；DB 只保留既有审计；不恢复 memories/memory_evidence，不新增 SQL 字段。 |
| pending 身份 | 通过 | 分析项先创建/获取，复用同一 `item_id` 作为可选 `add_pending(item_id=...)`；旧/evolution 生成的无关联项不自动猜测。 |
| worker 写序 | 通过（P1） | reserve audit → L1 action；pending 写失败标记 failed；formal write 成功后才 auto_saved；同 statement retry 不新建项。 |
| resolve 写序 | 通过（P1） | save 目标 append-first → 精确消费 PENDING → DB 审计成功；ignore 消费 PENDING → DB ignored；异常不更新成功。 |
| 幂等/崩溃 | 通过（有诚实窗口） | 目标 append 在既有文件锁内按同 scope/项目/正文幂等；append 成功后崩溃，重试不重复；PENDING 已消费但 DB 未更新时明确 409，不伪造成功。 |
| 并发 | 通过（单进程） | PENDING 锁保护 add/resolve；目标文件锁保护 append；不同文件可并行；不宣称跨进程/外部编辑器互斥。 |
| FTS | 通过 | 复用现有 `_sync_memory_index`/`reindex_all`；索引失败 fail-open，不反向成为文件错误。 |
| 前端接缝 | 通过 | textarea + revision state + conflict alert；`value`/`textContent`；409/503 保留草稿；不再请求旧 CRUD；资源版本号随 app/css 修改同步。 |

## 存储/并发实施门槛

1. 固定文档 API 的读写 seam 必须能区分“缺失文件（空文档）”与“权限/目录/解码错误（503）”；不得削弱既有 snapshot fail-open。
2. PUT 的 compare+write 必须在同一解析绝对路径锁内；临时文件与目标同目录，`fsync` 后 `os.replace()`；锁内不得调用可能造成锁顺序反转的 FTS 长 IO，索引可在文件成功后 fail-open。
3. `resolve_pending` 需在删除前保存目标的完整 `(item_id, content, project_id)` 快照；删除阶段重新读取并只删除仍匹配的项，外部/用户编辑变化返回 `PENDING_CHANGED`，不覆盖新内容。
4. 同项并发决策中第二请求不能把“已被第一请求消费”当作新 save，也不能重建 PENDING；对审计状态非 pending 的请求保持现有幂等读取，仍不写文件。
5. 进程崩溃窗口必须在文档/测试中诚实记录：DB 与文件不是 XA 事务；没有可靠证据时保持 pending/返回明确 409，而不是推断或按相似文本补写。

## 接口与安全门槛

- `scope=global` 携带 project_id、`scope=project` 缺 project_id、非法 project_id、非法/越界 symlink、超长 content、坏 revision、未知 body 字段均有合同 §2.4 对应错误码。
- foreign/删除项目不可通过错误差异探测存在性；archived 项目明确 `PROJECT_NOT_ACTIVE`，不创建项目文件。
- 错误响应不得返回绝对路径、真实 `MEMORY_DIR`、owner/token/cookie、堆栈或原始异常；`current_content` 仅在已授权的 OCC 409 中作为同 owner 合并副本。
- Markdown 仍是纯文本，不在前端渲染 HTML；用户内容必须 `textarea.value`/`textContent`，禁止 `innerHTML` 拼接。

## 分端任务与验证

### 后端顺序

1. **B01**：`markdown_store.py` + store 测试，完成 strict document seam、hash/limit/path、pending explicit ID、append-first 和幂等/故障语义。
2. **B02**：`repository.py` + `conversation_service.py`，完成 audit 预留/复用、worker 顺序、失败状态和 retry。
3. **B03**：`schemas.py` + `routes_conversations.py`，完成 GET/PUT、project/owner/OCC 错误体、decision 闭环；不恢复旧 CRUD。
4. `backend-reviewer` 后再由 `backend-tester` 跑 store/API/pending 定向测试；真实 TestClient 使用隔离临时 `MEMORY_DIR`/SQLite。

### 前端顺序

1. **F01**：在 B03 合同可读后，`index.html` + `app.js` 替换旧管理器为 editor；实现 scope/project GET、PUT、409/503 draft guard、旧 endpoint zero-call。
2. **F02**：仅在需要时修改 `styles.css` 并同步前端契约测试/版本号；复用现有 memory 作用域优先。
3. `frontend-reviewer` 后由 `frontend-tester` 做 `node --check`、DOM/class/`?v`/XSS 静态核对与浏览器记忆页 smoke，不跑后端 pytest。

### 必须落盘的验证证据

- 后端：每个 API 请求/响应、文件 bytes/hash、project/owner 隔离、OCC 409、503、pending `item_id`、最终 MD 和审计状态；append 失败/同项并发/重复重试用例。
- 前端：浏览器网络记录无 `/api/memories*`；GET 内容进 textarea；保存后重新 GET 一致；409/503 不丢草稿；旧 status/evidence/undo 控件消失。
- 收口：真实部署 API smoke 与人工步骤必须在最终候选版本执行；只有验收评审、架构签字、状态台账和部署均完成才可将 Spec 标记完成。

## 范围审计

本技术方案没有实际 scope expansion：新接口、文件 editor、OCC 和 pending 闭环均在用户确认的补充计划内；`item_id` 复用和 append-first 是修复既有缺口的实现选择。若开发提出新 SQL 列、任意路径访问、跨进程锁或旧 CRUD，立即 BLOCK 当前 Task，回到 Spec 修订/确认，不在本评审中默许。

## 证据诚实声明

本评审只读了代码事实、Spec、计划、既有测试和合同；未修改业务代码/测试，未运行 pytest、启动服务、调用 API、模型、下载或访问真实记忆文件。GO 是设计可实施结论，不是实现/运行时成功证明。

## 签字

- **评审人**：architect（独立技术评审）
- **日期**：2026-10-26
- **结论**：**通过（GO；P1 实现门槛见上）**
