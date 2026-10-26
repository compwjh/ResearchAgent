# Spec 038 补充需求评审：记忆管理与 Markdown 真相源复接

## 评审元数据

- **评审对象**：`docs/sdd/specs/038-memory-layer-redesign.md` 的 2026-10-26 管理复接补充
- **关联计划**：`docs/sdd/plans/038/2026-10-26-management-reconnect-plan.md`
- **接口合同**：`docs/sdd/plans/038/2026-10-26-management-contract.md`
- **评审者**：architect（独立评审）
- **角色**：架构师（需求/技术门禁）
- **模型**：Luna max（用户本轮临时指定；不写入长期 agent 配置）
- **分派方式**：`Task(architect)`，未分派编码、测试、API 写入、模型调用或部署
- **评审时间**：2026-10-26（Asia/Shanghai）
- **评审范围**：目标、用户行为、接口边界、数据/身份语义、失败与并发验收、前后端拆分

## 结论

**通过（GO；附实现前置门槛）。**

用户已明确确认“文件记忆方案”后，本补充的目标和范围足够明确，无需再次请求裁决。当前实现存在两个必须在验收前关闭的 P1 行为缺口：

1. `_analysis_item_decision()` 目前只更新 SQLite 审计项，没有写入/消费 `PENDING.md`；实现必须先完成 §3 的稳定 `item_id` 闭环。
2. `MarkdownMemoryStore.resolve_pending()` 当前先移除 PENDING 再 append 正式文件；实现必须改为 append-first、失败保留 PENDING，并以既有文件锁提供幂等重试。

这两个是实现门槛，不是需求打回项；若实现保留现状，验收应判不通过，不得以 UI 成功文案或审计状态冒充文件成功。合同中已固定 `GET/PUT /api/memory-documents`、65,536 Unicode code points、active project、OCC 409、draft 保留、稳定错误码和前后端顺序，不需要 re-grill 用户。

## 需求核对

| 检查项 | 判定 | 代码/计划事实与可测边界 |
|---|---|---|
| 一句话目标 | 通过 | 计划 §1 明确旧 `/api/memories*` 是真实退役 404；目标是固定 Markdown 文档编辑器，不伪造旧行式 CRUD。 |
| 真相源与 `USER.md` 边界 | 通过 | Spec 038 Q1/Q8 与计划 §2 已规定 MD 为唯一记忆真相源；`routes_conversations.py:501–535` 的 `/system-rule` 继续走 `USER.md`，合同禁止新 `user` scope。 |
| 新用户行为 | 通过 | 合同 §2 只增加全局/项目纯文本编辑；空内容是明确清空；无独立删除、来源、状态、撤销或任意文件动作。 |
| 作用域与所有权 | 通过 | 计划 §3.2 要求服务端固定 `MEMORY.md` / `projects/<id>.md`；合同要求当前 owner、active 项目，未知/foreign 404，非 active 409。 |
| 路径安全 | 通过 | 既有 `markdown_store.py:_project_path()` 已有白名单、长度和 realpath 防线；合同要求路由不接收 path/owner，非法或 symlink 越界前不创建目标文件。 |
| 内容限制 | 通过 | 合同冻结 65,536 Unicode code points，原文保存、无 trim/截断/Unicode 归一化；边界可用空串、65,536 与 65,537 字符测试。 |
| 并发冲突 | 通过 | 计划 §3.2 已提出内容 hash OCC；合同冻结同路径锁内比较/原子替换，stale revision 返回 `MEMORY_DOCUMENT_CONFLICT` 409，前端不覆盖草稿。明确不宣称对未持锁外部编辑器的绝对 CAS。 |
| API 错误可操作性 | 通过 | 合同 §2.4 固定 400/404/409/503 及 code；参数校验不得把默认 422 或空列表伪装成成功。 |
| 待确认闭环 | 通过（P1 实现门槛） | 当前模型 `MemoryAnalysisItem` 只有 `item_id/memory_id`，而 worker 在 `conversation_service.py:951–966` 先写 MD 再创建审计项；合同改为先预留 audit `item_id`，以同 ID 写 PENDING，决策只消费精确 ID。 |
| 保存/忽略语义 | 通过 | 计划 §3.3 与合同 §3.2 要求 save/ignore 都经过 `resolve_pending`；文件动作成功后才更新审计；不按 statement 相似度猜测。 |
| 遗留/无关联项 | 通过 | 合同固定 `PENDING_UNLINKED` 409 和“不自动处理”提示；不新建 SQL 映射、不把 `memory_id` 伪装成 pending 外键。 |
| 前端用户旅程 | 通过 | 合同 §4 固定 textarea、保存、刷新、冲突区域；409/503 保留草稿；旧 `/api/memories*`、status/evidence/undo 行操作移除。 |
| 验收可复核 | 通过 | 计划 §5 与合同 §5.3 要求隔离 TestClient/SQLite、文件 bytes/hash、真实 API、浏览器无旧请求和人工恢复步骤；真实私人文件不作为测试数据。 |
| 明确不做 | 通过 | 不恢复旧 SQLite CRUD、任意路径、第二存储、多租户、跨进程锁、全量聊天重构；合同 §6 对范围扩张设置暂停门。 |

## 需求层强制约束（交开发与验收）

1. 成功的“保存”必须同时可见于目标 MD 文件、GET 返回及下一次 snapshot/FTS 读取；仅 `decision_status=auto_saved` 不算成功。
2. stale API revision 只能 409；前端不能把 409/503 当作空文档或清空 textarea。
3. project scope 不能通过客户端传 owner/path 绕过 owner、active、realpath 校验；未知和 foreign 不泄露差异。
4. 分析项与 PENDING 使用相同稳定 `item_id`；旧/无关联项必须明确不可自动处理，不按文本、时间或项目推断。
5. append 失败时 PENDING 必须仍存在、审计不能变成 `auto_saved`；并发决策至多一个消费且不重复正式条目。
6. 文件系统与 SQLite 不作跨系统原子承诺：动作顺序必须诚实，崩溃窗口要返回明确未确认状态，不伪造成功。
7. 前后端实现必须读取并复用 `2026-10-26-management-contract.md` 的字段和错误码；任何新增 SQL 字段、任意文件 API 或恢复旧 CRUD 都是范围变化，先停工修订 Spec。

## 最小前后端上下文与任务顺序

- **后端最小上下文**：合同 §1–§3；`backend/app/memory/markdown_store.py` 的 RLock/原子写/FTS 钩子；`repository.py` 的 project owner 和分析项；`conversation_service.py` 的 worker；`routes_conversations.py` 的 system-rule/分析决策错误风格。不得读取或写入真实 `data/memory/`。
- **前端最小上下文**：合同 §2/§4；`frontend/index.html` memory view；`frontend/app.js` 旧 memory handlers；`frontend/styles.css` memory 作用域；前端安全与版本号约定。不得修改后端或调用真实私人文件。
- **顺序**：B01 Store seam → B02 audit/worker seam → B03 API seam → backend reviewer/tester → F01 editor shell → F02 必要样式/契约 → frontend reviewer/tester → 跨端真实 API/browser smoke。B01–B03 不并行覆盖同一文件；前端与后端分开分派。

## 证据诚实声明

本轮只读了 Spec、计划、合同相关代码和既有测试/评审格式；未修改业务代码或测试，未运行 pytest、启动服务、调用真实 API、访问 Ollama/Qdrant 或读取真实记忆内容。GO 仅表示需求已冻结并可进入实现，不表示功能已实现或验收通过。

## 签字

- **评审人**：architect（独立需求评审）
- **日期**：2026-10-26
- **结论**：**通过（GO；P1 实现门槛见上）**
