# Spec 038 补充计划：记忆治理与 Markdown 真相源复接

**状态：管理复接补充已完成（2026-10-26；需求/技术评审、跨端验收与架构师 GO 已落盘；本次仅更新文档，不修改业务代码、不执行 Git 操作）。** 原 Spec038 历史 P1/P2/P3 结论及 pending-confirm 人工边界保留。

> 2026-10-26 用户已明确确认按文件记忆方案实施；独立评审结论见
> [`038-requirement-review.md`](../../reviews/038-requirement-review.md) 与
> [`038-tech-review.md`](../../reviews/038-tech-review.md)，冻结合同见
> [`2026-10-26-management-contract.md`](./2026-10-26-management-contract.md)。

## 1. 当前根因

1. Spec 038 已将长期记忆真相源迁到固定文件：`USER.md`、`MEMORY.md`、`projects/<project_id>.md`；`memories`、`memory_evidence` 表及其 CRUD 已停用。`routes_conversations.py:2169` 的注释与当前路由表一致，`/api/memories*` 不存在。
2. `frontend/app.js:3379` 的旧记忆治理仍请求 `GET/POST/PATCH/DELETE /api/memories*`（列表、证据、确认、停用、删除、撤销），所以 `GET /api/memories?scope=global&status=active` 的 404 是真实的退役端点，不是 SPA 兜底误报。页面现在把“文件记忆”错误地当作旧的 `MemoryRecord` 行集合。
3. `tests/frontend/test_frontend_management_contract.py:26` 只断言源文件中出现字符串 `/api/memories`，没有请求/响应或文件落盘断言，因此会把这次 404 遮住。
4. 现有 `MarkdownMemoryStore` 没有 `memory_id/status/evidence/supersedes/undo` 语义：公开能力是 `read_user`、`write_user`、`read_project`、`append_memory`、`load_snapshot`、`list_pending`、`resolve_pending`。因此把旧 CRUD 路由原样补回来会重新制造第二套真相源。
5. 相邻的文件真相问题：`_analysis_item_decision()` 当前在 `routes_conversations.py:2141–2143` 只更新 SQLite 审计项为 `auto_saved`，没有用 `resolve_pending()` 写入目标 MD；“保存”按钮可能显示成功但正式文件没有变化。该问题必须一并纳入复接验收，不能用 UI 文案掩盖。

## 2. 已确认的复用边界

- `USER.md` 继续复用现有 `/api/system-rule`（`MemoryRepository` 的实现实际调用 `MarkdownMemoryStore.write_user/read_user`）。这里的 `enabled` 是兼容字段：内容非空即生效；不另建一个用户画像 API。
- 自动/待确认写入继续只走 `write_memory_candidate()` → `append_memory()` 或 `add_pending()`；会话装配继续走 `load_snapshot()`，检索继续走 `session_search`/既有 FTS 接线。
- 任何写入必须经过 store 的安全封装：进程内按绝对路径 `RLock`、同目录临时文件、`fsync`、`os.replace()`。路由不得直接拼接路径或调用私有 `_atomic_write()`。
- owner 不由客户端传入，沿用服务端固定 `OWNER_ID=local-user`。项目写入前同时复用仓储的 owner/项目状态校验与 store 的 `_project_path()`：`[A-Za-z0-9_-]+`、长度上限 100、`realpath` 必须留在 `projects/` 内；非法、未知或不可用项目不创建文件。
- FTS 行只是检索索引，不是记忆副本；不得恢复 `memories`/`memory_evidence` 表或把审计项当作长期记忆内容。

## 3. 推荐的最小诚实复接

### 3.1 无新公开 API 的安全基线

在 Spec 038 补充确认前，前端应停止所有 `/api/memories*` 请求，不把 404 转成空列表或“已加载 0 条”。保留并验证 `/api/system-rule` 的 USER.md 编辑器；普通长期记忆区域改为明确说明：

> 长期记忆由 `MEMORY.md` / `projects/<project_id>.md` 维护；当前页面不提供旧式逐条状态、来源、删除或撤销。

此基线允许用户按 Spec 038 产品步骤用编辑器修改 Markdown，同时避免伪装成已支持的行级治理。若产品必须在页面内读写 `MEMORY.md`，进入 3.2 的补充范围后再实现。

### 3.2 需要 Spec 038 补充确认的页面内文件编辑器

这是最小的新增用户行为：把当前“记忆列表”改成固定文档编辑器，而不是恢复旧 `MemoryRecord` CRUD。建议新增一个窄接口（名称可在评审时调整）：

`GET/PUT /api/memory-documents?scope=global|project[&project_id=<id>]`

约束：

- `scope=global` 只映射 `MEMORY.md`，必须拒绝 `project_id`；`scope=project` 必须有项目 ID，只映射 `projects/<id>.md`。请求中不接受 `path`、绝对路径或 owner。
- 项目读取/写入沿用 `OWNER_ID` 和 active 项目校验；未知、删除或不允许写入的项目返回稳定 404/409，不创建孤儿文件。
- 响应只表达文件事实，不伪造旧字段：

  ```json
  {
    "scope": "global",
    "project_id": null,
    "document": "MEMORY.md",
    "content": "…",
    "revision": "sha256-of-utf8-content"
  }
  ```

- `PUT` body 为 `{ "content": "…", "revision": "<last-read-revision>" }`。服务端以内容哈希做乐观并发检查；外部编辑或另一请求已改变文件时返回 409，绝不静默覆盖。空内容是明确的清空操作，不提供单独 `DELETE`。
- 缺失文件按既有 store 语义返回空内容；读取/持久化异常返回可识别的 503，不能返回“空列表”或成功状态。内容上限、Unicode 规则和 archived 项目读取策略需在补充 spec 中裁决，不能自行沿用 `USER.md` 的 12,000 上限或截断。
- store 只需增加固定 scope 的读写门面（例如 global read/write、project write；现有 `read_project` 可复用），内部仍调用原子写和索引钩子；不得新增通用任意文件访问器。

前端对应调整：

- 删除 `memoryStatusSelect`、`memory_id`、来源证据、候选/停用/删除/撤销等旧行操作；用 global/project 选择器、纯文本 textarea、读取/保存/冲突提示表达文件内容。
- 保留独立的系统规则卡片（USER.md）；不把 `USER.md` 混入新的 `memory-documents` scope，避免两个写入口产生覆盖竞态。
- 纯文本展示使用 `textContent`/textarea，不渲染 Markdown HTML。保存成功后显示返回的 `revision` 已更新；409 要求重新加载/人工合并，503 要保留原编辑内容并显示失败。
- “新建记忆”应成为编辑器中的追加/编辑动作，成功标准是 PUT 后重新 GET 与文件内容一致，而不是旧的 `POST /api/memories`。

### 3.3 待确认项写入闭环（必须与页面编辑器分开）

现有 `add_pending()` 会生成 `item_id`，但 worker 未把该 ID 落入 `MemoryAnalysisItem`；当前决策接口无法可靠调用 `resolve_pending()`。补充 spec 需要选择并锁定一种方案：

- 在审计项保存稳定 `pending_id`，决策保存时校验原始项目快照/全局显式意图后调用 `resolve_pending(pending_id, ...)`，只有 MD 写入成功才把审计项改为 `auto_saved`；或
- 定义等价的、可审计的 pending 映射/消费操作。禁止只按陈述文本猜测条目，禁止先把审计状态改成成功。

“忽略”也必须有明确语义：要么原子丢弃对应 `PENDING.md` 条目并记录 `ignored`，要么保留 pending 并在 UI 明示仍待处理；不能出现 DB 显示 ignored、文件仍被当作待确认项的未定义状态。系统规则意图仍只能进入 `/api/system-rule` 的显式编辑流程。

## 4. 安全与一致性检查

- 路径：拒绝 `../x`、`a/b`、`.`、超长 ID、非法字符和越过 `projects/` 的符号链接；覆盖读和写，且失败前不得产生目标文件。
- owner/project：客户端不传 owner；服务端用 `OWNER_ID` 查询项目，并保留发送时项目快照约束，防止会话移动后把待确认项写入新项目。
- 原子性：临时文件与目标同目录，写后 `fsync` 再 `os.replace`；索引失败仍保留 L1 写入，但 API 不能把 L1 写入失败报成成功。
- 并发：进程内锁是 Spec 038 当前部署边界；若改为多进程，跨进程锁是发布阻断项，不在本次复接顺手补齐。`revision` 用来覆盖外部编辑竞态。
- 隐私：不返回绝对文件路径、Cookie、Token、完整 Prompt 或隐藏思维链；真实 `data/memory/` 仍不入库。

## 5. 必须替换的验收合同

静态契约可保留作 DOM/XSS 辅助，但不能再把它当 API 证明。至少补齐以下真实合同：

1. **后端文件 API（TestClient + 隔离 `MEMORY_DIR`/数据库）**：global/project GET/PUT 与实际 `MEMORY.md`、项目 MD、`load_snapshot()`、`session_search` 互相一致；跨项目隔离；非法/未知/非 active 项目不写文件；404/503/409 体稳定。
2. **修订冲突与原子写**：外部改文件后 stale revision 的 PUT 返回 409 且不覆盖；并发写不丢条目、不暴露半截文件；索引失败不影响已落盘内容。
3. **待确认 E2E**：真实 worker 产生 `PENDING.md` → 查询分析结果 → 保存决策后目标 MD 含条目且 pending 条目消失 → 下一次快照/检索可见；忽略路径不写正式文件；项目快照不匹配不写入。当前只断言 `decision_status` 的用例不足。
4. **浏览器路径（Playwright）**：打开记忆页时不发 `/api/memories*`；真实 GET 内容进入编辑器；保存后重新 GET 与文件一致；409/503 有可见错误且不会清空编辑内容；页面不再展示虚假的 status/evidence/undo 行操作。
5. **回归旧活接口**：`/api/system-rule` 继续验证 `USER.md` 读写、12,000 Unicode 门控、清空语义和稳定 503；已有 `MarkdownMemoryStore`、FTS wiring、context usage 测试继续通过。

## 6. 明确不实施

- 本计划不恢复 `/api/memories` 旧 CRUD，不建立 `MemoryRecord`/`memory_evidence` 的 Markdown 映射，不伪造 `memory_id`、status、来源、版本或撤销能力。
- 本计划不把 `/api/memories` 404 隐藏成 200 空列表，不新增任意路径/文件下载 API，不直接暴露 `MEMORY_DIR`。
- 本计划不修改业务代码、前端、schemas、数据库、真实记忆文件或 API 状态；必须先由 Spec 038 补充完成需求/技术评审并获确认，再分派实现与验收。

## 7. 2026-10-26 当前进度与人工验收交接

管理复接补充已完成，真实人工案例只使用隔离的 active 项目 `a4a1745f801441188dc1f75b0534be11`（名称“文件记忆验收 20261026”），禁止把全局 `MEMORY.md` 或用户已有项目记忆作为测试目标。验收报告为 `READY_FOR_USER`、架构师为 `GO`；这只关闭本次管理复接补充。

- 真实项目 API E2E 已落盘：`200 GET` 空文档 → `200 PUT` 初次保存 → `200 GET` 重读 → stale revision `409 MEMORY_DOCUMENT_CONFLICT`（草稿未被覆盖）→ `200 GET` 读取当前副本。`api-e2e.json` 的原始 trace 不包含后续合并 PUT；真正的合并 PUT 成功由最终 runtime、恢复截图和第二真实页面的冲突恢复写入证据共同证明。请求/响应、revision、project ID 及证据边界见 [`2026-10-26-management-runtime.md`](./2026-10-26-management-runtime.md)、`artifacts/20261026-file-management/api-e2e.json`、`artifacts/20261026-file-management/final-runtime.json` 与 `artifacts/20261026-file-management/browser-conflict-recovery-server-write.json`。
- 浏览器 runtime 已核对：在两个真实页面同时打开 `http://127.0.0.1:8000` 的“记忆治理”，选择同一 active 专用项目；页面 B 先保存并发版本，页面 A 用旧 revision 保存触发 409；页面 A 点击“读取最新版本并保留草稿”，人工合并后再次保存成功。最终截图与页面资源/状态见 [`recovery-saved.png`](artifacts/20261026-file-management/recovery-saved.png) 和 `final-runtime.json`。
- 当前门禁进度：后端全量最终为 `3121 passed, 0 failed, 3 skipped, 67 subtests passed`；前端最终完整集合为 `317 passed, 0 failed, 0 skipped, 59.01s`，Node 合同测试 `33/33`。此前 `315/1` 的 synthetic 地图性能失败已在测量窗修复后通过最终完整复跑。自然语言项目记忆已完成：conversation `6a59bd0707d54761a6cd3a5a68e88ecf`、analysis `a3d8ad2a46a1406cb020db450954834e`，`saved_count=1`、`pending_count=0`，独立 GET 文件确认含“蓝色松果”；SSE capture 的 `events` 为空，仅记录为解析未命中，不冒充原始事件。
- 逐步点击、等待提示、409 恢复、最终产物路径及证据边界统一记录在 [`2026-10-26-management-runtime.md`](./2026-10-26-management-runtime.md)；最终后台托管与健康复核见 runtime 末尾。pending-confirm 人工保存/忽略流程未冒充已执行，原 Spec038 其它潜在工作不因本补充改变。

### 同范围 P2 复开最终页面复核（2026-10-26；等待 QA 最终验收）

- `#memory-view` 的 scoped `[hidden]` 修复已由独立 review 判定 `GO`；作者候选 commit `87b0a88b` 未对外推送。页面资源更新为 `app.js?v=66`、`styles.css?v=66`、地图 21/13；旧版 65/21/13 与旧错误截图保留。
- 最终前端完整回归为 `318 passed, 0 failed, 0 skipped, 58.17s`；后端未变，仍为 `3121 passed, 0 failed, 3 skipped, 67 subtests passed`。root 真实 CUA 状态为初始 `none` → 409 `grid` → 保存后 `none`；最终 revision 为 `e96ff2a825ed22acda7cd18eb35560bb575bd3c101c87866edf456d36f71cf51`，蓝色松果与此前 demo 内容均保留。
- 新证据：[`hidden-before-fix.json`](artifacts/20261026-file-management/hidden-before-fix.json)、[`hidden-recheck.json`](artifacts/20261026-file-management/hidden-recheck.json)、[`hidden-recheck-final-document.json`](artifacts/20261026-file-management/hidden-recheck-final-document.json)、[`recovery-saved-hidden-fixed.png`](artifacts/20261026-file-management/recovery-saved-hidden-fixed.png)。后者实际无红框；此前错误截图 [`recovery-saved.png`](artifacts/20261026-file-management/recovery-saved.png) 仅作为历史证据保留。
- 本轮只更新运行时/证据索引；QA 最终验收尚在补齐，不新增或改写 Spec/状态台账的完成记录，等待 root 收到本轮 architect 结论后统一处理。

## 最终 P2 收口绑定（2026-10-26 23:27，北京时间）

可见性修复候选为 `87b0a88b`，当前 app/styles 为 66，地图为 21/13；完整前端回归 318 passed、0 failed、0 skipped。`038-acceptance-review.md` §7 的 tester 与 architect 补签均已通过，本次管理复接补充已完成。此前“待补签”仅为历史阶段记录；旧错误截图保留，当前正确截图为 `artifacts/20261026-file-management/recovery-saved-hidden-fixed.png`。后台服务仍由当前登录会话的 `com.researchagent.recovery8000` 托管，原用户记忆未用于测试写入。
