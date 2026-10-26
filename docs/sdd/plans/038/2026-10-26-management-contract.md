# Spec 038 补充：记忆管理复接最小接口合同

## 合同元数据

- **合同版本**：`memory-management-v1`
- **对应 Spec**：`docs/sdd/specs/038-memory-layer-redesign.md` 的 2026-10-26 管理复接补充
- **状态**：已冻结；B01–B03/F01–F02 已按合同实现并完成本次管理复接验收。合同不扩展为 Spec038 历史阶段或 pending-confirm 人工流程的完成证明。
- **冻结时间**：2026-10-26（Asia/Shanghai）
- **真相源**：`MEMORY.md`、`projects/<project_id>.md`；`USER.md` 继续只由 `/api/system-rule` 管理
- **本合同不做**：恢复 `/api/memories*`、恢复 `MemoryRecord`/`memory_evidence` CRUD、增加任意路径读写、增加记忆 SQL 真相表或新 SQL 字段、改变单进程文件锁边界

## 1. 不可变约束

1. 客户端只能选择 `global` 或 `project`；服务端固定映射文件，客户端不能传 `path`、绝对路径、owner 或文件名。
2. 项目读写只接受当前 `OWNER_ID` 下状态为 `active` 的项目。未知项目、删除项目和其他 owner 的项目统一按不存在处理；已存在但非 active 的项目拒绝读写。
3. `MarkdownMemoryStore` 是唯一文件读写入口。路由不拼接文件路径，不调用私有原子写函数，不把 SQLite/FTS 行当作内容副本。
4. 通过同一解析后绝对路径的进程内 `RLock` 串行化 API 读改写，并继续使用同目录临时文件、`fsync`、`os.replace()`。此保证只覆盖本进程；不承诺与未持锁的外部编辑器之间的绝对 CAS。
5. 内容按 UTF-8 原文保存：不 trim、不自动补换行、不做 Unicode 归一化、不截断。长度上限为 **65,536 个 Unicode code points**；超过上限是 400，不降级为空或截断。
6. `revision` 是内容 UTF-8 字节的 SHA-256 小写十六进制（64 字符）。缺失文件按空内容读取，空内容 revision 为空串的 SHA-256；GET 不因缺失而创建文件。
7. `/api/system-rule` 与 `USER.md` 保持原有接口和 12,000 code points 门控；新接口没有 `user` scope，避免两个编辑入口覆盖同一文件。

## 2. 文件文档 API

挂载后的完整路径为：`GET/PUT /api/memory-documents`。

### 2.1 选择参数

| 参数 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `scope` | `global \| project` | 是 | 其他值返回 400 `INVALID_MEMORY_DOCUMENT_SCOPE` |
| `project_id` | string | project 时是 | 只允许 `[A-Za-z0-9_-]+`、最长 100；global 时必须省略 |

参数错误必须映射为稳定 400，而不是把 FastAPI/Pydantic 默认 422 暴露给前端：

- 缺少 project scope 的 `project_id`：`PROJECT_ID_REQUIRED`
- global 携带 `project_id`：`PROJECT_ID_NOT_ALLOWED`
- 非法字符、越界、空值或解析后符号链接越出 `projects/`：`INVALID_PROJECT_ID` 或 `MEMORY_DOCUMENT_PATH_INVALID`
- 未知/删除/foreign 项目：404 `PROJECT_NOT_FOUND`
- archived 或其他非 active 项目：409 `PROJECT_NOT_ACTIVE`

响应中的 `document` 只能是固定相对标签：global 为 `MEMORY.md`，project 为 `projects/<validated-project_id>.md`；绝不返回绝对路径、真实 `MEMORY_DIR` 或符号链接目标。

### 2.2 GET

请求示例：

```http
GET /api/memory-documents?scope=global
GET /api/memory-documents?scope=project&project_id=proj_123
```

成功响应为 200，形状固定：

```json
{
  "scope": "global",
  "project_id": null,
  "document": "MEMORY.md",
  "content": "- 先给结论\n",
  "revision": "<sha256-of-content-utf8-bytes>"
}
```

project 响应将 `scope` 改为 `project`、填入经过校验的 `project_id`，其余字段相同。缺失文件返回 `content: ""` 及空内容 hash，不创建目标文件。真实读取/解码/权限/目录错误返回 503 `MEMORY_DOCUMENT_UNAVAILABLE`，不能伪装为空文档。

### 2.3 PUT

请求 query 选择与 GET 完全相同；JSON body 只允许以下两个字段：

```json
{
  "content": "- 先给结论\n",
  "revision": "<revision returned by the last GET>"
}
```

- `content` 必须是字符串，允许空串（空串就是明确清空，不提供 DELETE）。
- `revision` 必须是小写 64 位 SHA-256。首次创建用空文件 hash；禁止省略、通配或“强制覆盖”值。
- 未知 body 字段（尤其 `path`、`owner`、`document`）返回 400 `INVALID_MEMORY_DOCUMENT_REQUEST`。
- body 校验失败统一返回 400；错误体保持 `{ "detail": { "code", "message", "retryable": false } }`。

服务端在同一文件锁内重新读取当前 bytes、核对 revision，再原子写入并计算新 revision。成功返回 200，形状与 GET 相同，`content` 为实际保存的原文。旧 revision 不匹配时返回 409：

```json
{
  "detail": {
    "code": "MEMORY_DOCUMENT_CONFLICT",
    "message": "文档已被其他写者修改，请合并后重试",
    "retryable": false,
    "scope": "global",
    "project_id": null,
    "document": "MEMORY.md",
    "current_content": "<server-content>",
    "current_revision": "<server-revision>"
  }
}
```

`current_content` 仅供同一 owner 的冲突合并视图使用；前端不得用它覆盖正在编辑的 textarea。若冲突读取当前文件本身失败，返回 503 `MEMORY_DOCUMENT_UNAVAILABLE`，仍不得覆盖草稿。正常 stale API revision 必须 409；不能用“最后写入者胜出”或 200 空成功替代。

文件写入成功后，已有 FTS 同步钩子可 fail-open；索引失败不撤销已成功的 L1 文件写入，也不把文件写失败报告成成功。索引重建继续复用现有 `reindex_all`。

### 2.4 错误码表

| HTTP | code | 触发条件 | 是否可重试 |
|---:|---|---|---|
| 400 | `INVALID_MEMORY_DOCUMENT_SCOPE` | scope 缺失/未知 | 否 |
| 400 | `PROJECT_ID_REQUIRED` | project scope 未提供 project_id | 否 |
| 400 | `PROJECT_ID_NOT_ALLOWED` | global scope 携带 project_id | 否 |
| 400 | `INVALID_PROJECT_ID` | project_id 空值、非法字符、超长 | 否 |
| 400 | `MEMORY_DOCUMENT_PATH_INVALID` | realpath/符号链接越界 | 否 |
| 400 | `MEMORY_DOCUMENT_TOO_LARGE` | 超过 65,536 Unicode code points | 否 |
| 400 | `INVALID_MEMORY_DOCUMENT_REVISION` | revision 格式错误/缺失 | 否 |
| 400 | `INVALID_MEMORY_DOCUMENT_REQUEST` | body 类型错误或存在未允许字段 | 否 |
| 404 | `PROJECT_NOT_FOUND` | 未知、删除或 foreign 项目 | 否 |
| 409 | `PROJECT_NOT_ACTIVE` | archived/其他非 active 项目 | 否 |
| 409 | `MEMORY_DOCUMENT_CONFLICT` | stale revision | 否（先 GET/合并） |
| 503 | `MEMORY_DOCUMENT_UNAVAILABLE` | 文件读写/原子替换/权限/解码失败 | 是 |

## 3. 待确认记忆闭环合同

### 3.1 稳定身份：复用 `MemoryAnalysisItem.item_id`

当前 `MemoryAnalysisItem` 没有 `pending_id` 字段；本补充不新增 SQL 列，也不把 `memory_id` 偷换成 pending 外键。分析 worker 采用以下最小顺序：

1. 先用现有 `create_memory_analysis_item` 预留/获取审计项，返回稳定的 `item_id`，初始状态为 `pending_confirmation`；相同 `(analysis_id, statement)` 重试仍返回原项。
2. 将这个 `item_id` 作为 `add_pending(..., item_id=item_id)` 的可选显式 ID。未传 ID 的既有调用继续生成 UUID，兼容 evolution worker 与旧文件。
3. `add_pending` 在 PENDING 锁内幂等：同 ID、同内容、同项目后缀是 no-op；同 ID 内容或项目不一致返回 `PENDING_ID_CONFLICT`，不得覆盖。
4. 正式文件直写成功后，才把预留审计项更新为 `auto_saved`；待确认文件写成功后保留 `pending_confirmation`。待确认文件写失败则审计项为 `failed`，不能宣称“待确认”却没有 PENDING 条目。

显式 ID 复用既有审计项 ID（当前为不透明的 UUID/hex 字符串；store 只接受 `[0-9A-Za-z_-]{1,64}`，不接受空格、控制字符或路径分隔符），不增加前缀、不增加 SQL 列。建议的最小方法形状为：

```python
add_pending(*, content: str, project_id: str | None = None,
            item_id: str | None = None) -> str
resolve_pending(item_id: str, *, scope: str, project_id: str | None,
                decision: Literal["save", "ignore"] = "save") -> None
```

这样，分析审计项 ID 与 PENDING ID 是同一稳定身份，避免新 SQL 真相。`memory_id` 继续保持历史弱引用字段语义（本补充不写入它）。

### 3.2 决策保存/忽略必须消费指定项

分析决策路由必须先做 owner、状态、原始消息 global/system-rule 约束及项目快照校验，然后只调用 `MarkdownMemoryStore.resolve_pending(item.item_id, ...)`；禁止按 statement 相似度、顺序或项目猜测条目，禁止只调用 `update_memory_analysis_item`。

- **保存**：`resolve_pending` 在 PENDING 锁内读取并校验精确 ID/内容/项目；先在目标固定文件的既有文件锁内执行幂等 append，再在 PENDING 锁内删除仍与快照一致的该条目。append 失败时 PENDING 保留；只有 resolver 成功返回后才更新审计为 `auto_saved`。
- **忽略**：`resolve_pending(..., decision="ignore")` 只消费精确 PENDING 条目，不写正式文件；只有消费成功后才更新审计为 `ignored`。
- **范围**：project 保存必须使用发送时的 active 项目快照（用户选择不同项目返回 `PROJECT_SCOPE_SNAPSHOT_MISMATCH`）；global 仍需原始消息显式 global 意图；system-rule 意图继续返回 `SYSTEM_RULE_REQUIRES_EXPLICIT_SAVE`。
- **原子边界**：SQLite 审计更新与文件系统写入不是跨系统事务。代码不得声称两者绝对原子；审计状态必须在文件动作成功后写入，文件动作失败不得更新成功状态。

### 3.3 失败、并发、重试和遗留语义

| 场景 | 必须行为 |
|---|---|
| append 目标文件失败 | 保留 PENDING 和 `pending_confirmation` 审计状态；返回 503 `MEMORY_PENDING_RESOLUTION_UNAVAILABLE`，不写 `auto_saved` |
| PENDING 写入失败（worker） | 该分析项为 `failed`；不得返回成功或“待确认但不可见” |
| 同项并发 save/ignore | PENDING 锁保证至多一个消费；第二请求返回 409 `PENDING_ALREADY_CONSUMED` 或 `PENDING_CHANGED`，不重复追加、不更新错误项为成功 |
| append 成功后进程在删除 PENDING 前崩溃 | PENDING 仍在；重试使用同 ID，幂等 append 不重复，然后消费 PENDING |
| 删除 PENDING 后、SQLite 审计更新前崩溃 | 不伪造成功；后续请求返回 409 `PENDING_ALREADY_CONSUMED` 并保留审计 pending，进入明确人工/运维恢复路径；不得按文本猜测或新建第二套映射 |
| 用户/外部编辑器在两步之间改了该项 | 精确快照校验失败，返回 409 `PENDING_CHANGED`，不删除新内容 |
| 旧 PENDING ID 没有对应审计项，或旧审计项没有同 ID PENDING | 409 `PENDING_UNLINKED`，明确“无法自动处理”；不按相似文本落盘、不改变审计成功状态 |
| FTS 索引失败 | L1 文件结果保持；索引失败记录既有日志并由 reindex 兜底，不把文件写失败 |

`resolve_pending` 不能被当作跨文件事务；验收必须用故障注入证明 append 失败不丢 PENDING、并发消费不重复，以及重试不会产生重复正式条目。正式 `append_memory` 需在既有目标文件锁内对相同 scope/项目/规范化正文幂等，作为 crash/retry 的最小去重，不引入 scheduler、队列或第二存储。

待确认决策的稳定错误映射：

| HTTP | code | 触发条件 |
|---:|---|---|
| 400 | `PROJECT_REQUIRED` | save_project 没有可用 project_id |
| 409 | `PROJECT_SCOPE_SNAPSHOT_MISMATCH` | 选择的项目不是发送时快照项目 |
| 409 | `PENDING_ID_CONFLICT` | 显式 item_id 已存在但内容/项目不一致 |
| 409 | `PENDING_CHANGED` | 消费前后 PENDING 快照被外部修改 |
| 409 | `PENDING_ALREADY_CONSUMED` | 指定 ID 已被另一决策消费，当前审计仍待人工恢复 |
| 409 | `PENDING_UNLINKED` | 审计项与 PENDING 没有同 ID 可靠关联 |
| 503 | `MEMORY_PENDING_RESOLUTION_UNAVAILABLE` | 目标 MD append/消费所需文件动作失败 |

`SYSTEM_RULE_REQUIRES_EXPLICIT_SAVE`、`PROJECT_NOT_FOUND` 等既有分析决策错误码保持原语义；上述新码不得用 statement 猜测来绕过。

## 4. 前端 DOM 与行为合同

### 4.1 固定 DOM

继续复用 `#memory-scope-select`、`#memory-project-select`、`#memory-project-label`、`#memory-refresh-button`、`#memory-status`；新增/替换为：

- `#memory-document-editor`：`textarea`，只显示/编辑纯文本 Markdown；不用 `innerHTML`。
- `#memory-document-save-button`：发送 PUT；请求期间禁用，成功后显示已保存 revision 的短状态。
- `#memory-document-revision`：非编辑字段（可用 `data-revision` 或隐藏文本）保存当前 GET/PUT revision，不能由用户编辑。
- `#memory-document-conflict`：`role="alert"` 的冲突区域，可用 `textContent` 展示合并提示；如展示服务端副本，使用另一个纯文本节点，不覆盖 editor。

移除管理页运行时对 `#memory-status-select`、`#memory-create-button`、`#memory-list`、旧 row 的 status/evidence/confirm/disable/delete/undo 操作依赖；`USER.md` 系统规则卡片和其按钮保持独立。

### 4.2 请求与草稿保护

1. 进入 memory view、scope/project 改变或显式刷新时 GET 固定接口；active 项目列表来自既有 `/api/projects`，不允许用户手填路径。
2. PUT body 只发当前 textarea 的原文和最后 GET revision。成功以响应 content/revision 回填；空文本也按成功清空处理。
3. 409 `MEMORY_DOCUMENT_CONFLICT`：保留 textarea 草稿和本地 revision，不清空、不覆盖；显示“服务器已有新版本”，允许用户查看服务端副本、重新 GET 后人工合并再保存。
4. 503 或网络错误：保留 textarea 草稿与 revision，显示可重试状态；不渲染空列表/“已加载 0 条”。404/409 项目错误同样不伪造空文档。
5. 全部动态文本走 `textContent`，输入走 `textarea.value`；不把 Markdown 转 HTML，不使用用户内容拼接 `innerHTML`。修改 `app.js`/`styles.css` 必须同步升 `index.html` 资源版本号。

## 5. 分端任务与门禁顺序

### 5.1 后端（必须先冻结并完成）

后端最小上下文：本合同 §1–§3、`markdown_store.py` 的既有锁/原子写/FTS 钩子、`repository.py` 的 project owner 查询与 `memory_analysis_items`、`conversation_service.py` 的 worker 顺序、`routes_conversations.py` 的 `/system-rule`/analysis decision 错误风格；不读/不改真实 `data/memory/`。

按仓库“每任务不超过两文件”拆分，顺序固定：

1. **B01 Store seam**（backend-dev）：`backend/app/memory/markdown_store.py` + 后端 store 定向测试。固定文档读写、hash、上限、路径、pending 显式 ID/幂等、resolve append-first/故障语义。
2. **B02 Audit/worker seam**（backend-dev）：`backend/app/memory/repository.py` + `backend/app/chat/application/conversation_service.py`。先预留/复用 `item_id`，再写 PENDING/正式文件；失败状态和重试不重复。
3. **B03 API seam**（backend-dev）：`backend/app/api/schemas.py` + `backend/app/api/routes_conversations.py`。冻结 GET/PUT、owner/active project、错误体和决策闭环；不恢复旧 CRUD。
4. `backend-reviewer` 只评 `backend/**`；`backend-tester` 只跑受影响后端测试和真实隔离 TestClient/API smoke，不跑无关前端回归。

### 5.2 前端（后端合同与 API seam 可读后独立分派）

前端最小上下文：本合同 §2、§4、现有 `frontend/index.html` memory view、`frontend/app.js` 的 memory handlers、`frontend/styles.css` 的 memory 作用域、`frontend-patterns`/`regression-guard`；不改后端、不调用真实用户文件。

后端 B03 接口合同落盘后再分派，前端任务与后端实现分开：

1. **F01 editor shell**（frontend-dev）：`frontend/index.html` + `frontend/app.js`。移除旧 `/api/memories*` 行式操作，接入 GET/PUT、draft/409/503 保护和固定 DOM。
2. **F02 style/contract check**（frontend-dev）：如确需样式才改 `frontend/styles.css`，并同步前端契约测试/资源版本；否则复用现有样式，不新增 CSS。
3. `frontend-reviewer` 检查 DOM、版本号、XSS；`frontend-tester` 只做 `node --check`、静态契约和浏览器 memory view smoke，不跑后端 pytest。

### 5.3 统一验收门禁

- B01–B03 的定向测试必须先绿，再允许 F01 接真实接口；前后端可在合同冻结后分开工作，但不得各自发明字段/错误码。
- 最终验收必须有真实 API 请求/响应、隔离 `MEMORY_DIR`/SQLite、文件 bytes/hash、实体 `item_id`、最终审计状态和产物路径；不能用 mock、旧静态 `/api/memories` 断言或真实私人文件替代。
- 浏览器必须证明：不请求 `/api/memories*`；GET 内容进入 textarea；PUT 后重新 GET 与文件一致；409/503 草稿不丢；旧 status/evidence/undo 行操作不再出现。
- 本次收口已完成全量回归、真实部署 API smoke 与人工逐步验收；本合同仍只约束管理复接补充，不改变 Spec038 其它历史/潜在范围。

## 6. 变更控制

本合同把用户已确认的文件编辑器、固定 scope、OCC、待确认闭环和单进程边界具体化，没有新增用户行为或第二存储。若实现需要新增 SQL 字段、任意文件 API、跨进程锁、恢复旧 CRUD、改变 `USER.md` 入口，或把“审计更新成功”置于文件动作之前，必须暂停当前 Task，修订 Spec 038 并重新请求确认；不得在实现中自行扩大范围。
