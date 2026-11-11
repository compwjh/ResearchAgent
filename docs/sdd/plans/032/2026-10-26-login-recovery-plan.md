# Spec032 登录恢复计划：优先复用导入条目持久快照

> 关联：[Spec032](../../specs/032-research-source-expansion.md) §接口、边界与产品步骤 6–7；Task11 登录/恢复范围。
>
> **状态：本次登录/继续窄修已完成（2026-10-26；tester READY_FOR_USER、architect GO；整体 Spec032 仍暂停）**。本文件保留原始诊断与最小实施方案，并追加当前人工验收步骤；不代表 Spec032 整体收口。历史执行记录保留 Luna max；本次追加临时 Luna xhigh，不修改角色配置。

## 结论

`waiting_login` 的登录入口应先从 `PaperImportBatchService` 已有的、带 hash 校验的持久候选快照恢复 URL，再决定是否需要读取仍有效的 live search session。这样用户可以在搜索 TTL 之后、甚至服务重启后重新打开 ACM/IEEE 登录页；这不等于延长搜索 TTL，也不需要重新运行研究。

最小改动是收紧 `_paper_snapshot_for_item` 的解析顺序：复用现有 `_snapshots_for(batch_id, None)` 的 durable-first 语义，只有持久快照缺失、损坏或无法完成身份校验时才保留当前 live-search fallback 和原有错误。`login`、`resume`、`retry-item` 共用这一解析边界；不新增 HTTP API、request/response schema、数据库表或第二套状态机。

## 只读运行时证据

仅使用 `data/paper_search/state.sqlite3` 的 SQLite `mode=ro`/`-readonly` 查询，没有调用 Store 构造函数或迁移逻辑：

| 实体 | 观察结果 |
|---|---|
| batch `1a76e369-c638-4f2c-a430-42552a1e7012` | `waiting_login`；`search_id=acm-manual-20260922144403614390`；`search_expires_at=2026-09-22T16:44:03.614546Z` |
| item `9eed783f-ff98-4021-99dd-1ab2787688cb` | `waiting_login`、`LOGIN_REQUIRED`、`attempt_count=1`；`snapshot_json` 2784 bytes，`snapshot_hash` 非空 |
| 持久快照身份 | `candidate_id=014eb508824e53378629b79e08d9ff2e` 与 item 一致；`search_id` 与 batch 一致 |
| 持久快照 URL | ACM article `https://dl.acm.org/doi/10.1145/3658644.3690205`；PDF 候选同为 `dl.acm.org` |
| 完整性 | 计算 SHA-256 与存储 hash 完全相等 |
| live search | 对应 `search_sessions` 已过期，`search_results` 当前为 0；已无可依赖的 live 结果重建路径 |

因此当前失败不是候选丢失，而是路由先执行 `_paper_search_expired`，在到达 durable snapshot restore 之前返回 `SEARCH_EXPIRED`。

## 现有可复用边界

- `routes_paper.py:_paper_snapshot_for_item`（约 893–924 行）目前先读 `search_sessions`/候选并检查搜索 TTL，是阻塞点。
- `PaperImportBatchService._snapshots_for`（约 399–502 行）已经先逐 item 调用 `store.get_snapshot`；完整且 hash 校验通过时直接返回，不依赖 live session、旧 `search_expires_at` 或进程内 `_snapshots`。快照不完整时才保留重建门禁。
- `PaperImportBatchStore.get_snapshot`（约 561–577 行）校验 `snapshot_json` 的 SHA-256、JSON 可恢复性和 `candidate_id/search_id` 非空；必须继续作为唯一持久快照读取入口。
- `_paper_item_browser_target`（约 1079–1100 行）继续从服务端快照取 URL，并只接受精确 `dl.acm.org`/`ieeexplore.ieee.org` origin；`PaperBrowserManager` 和下载器的 URL、重定向、SSRF/allowlist 校验不变。
- `login`（约 1134–1152 行）仍只打开受控 headed page；`resume`（约 1155–1208 行）仍检查内存 session 的 `required/expired/closed`，再交给 `resume_item` 的 CAS/lease/status 约束。
- `PaperBrowserManager` 的 session TTL（约 639–665 行）仍是浏览器会话生命周期，不是研究任务或候选快照 TTL；`open_session`（约 788–823 行）继续使用同一 persistent profile，空闲回收只释放 page/context/profile lock。

## 最小实施方案（不扩大 Spec032）

1. 在 `_paper_snapshot_for_item` 已完成 item/batch 存在性检查后，先调用现有 service durable resolver（直接复用 `_snapshots_for(batch.batch_id, None)`；若代码边界不允许路由调用私有方法，只增加一个不对外暴露的薄 wrapper，内部仍只委托该方法）。
2. 对返回集合做窄身份检查：目标值的 `candidate_id` 必须等于 item 的 `candidate_id`，`search_id` 必须等于 batch 的 `search_id`；目标缺失、hash 校验失败、JSON 不可恢复或身份不匹配时 fail-closed，不能退回客户端输入或任意 live URL。持久快照完整时**跳过** `_paper_search_expired`。
3. 将已校验的 durable snapshot 列表交给现有 `_paper_item_browser_target`，保留其 URL 精确 origin 检查。`login`/`resume` 的公开响应、错误码和 session 清理逻辑不变；`resume_item` 继续只允许既有 `waiting_login/failed` 状态，`retry_item` 继续只允许 `failed`，`waiting_login` 不转入 retry。
4. 对缺失/损坏快照保留现有 live-search fallback 和稳定错误（如 `SNAPSHOT_REBUILD_REQUIRED`、`SEARCH_EXPIRED`、`SEARCH_NOT_FOUND`、`CANDIDATE_NOT_FOUND`）；不要用过期 search 结果重建，也不要静默把坏快照当成可用快照。
5. 不修改 `PaperBrowserManager` TTL。TTL 到期仍关闭临时 session/page 并 fail-closed；批次和 item 的持久状态不删除、不取消、不重跑研究。用户再次点击登录时，复用同一 persistent profile；profile 中仍有效的 publisher cookie 可以继续使用，publisher 授权已过期则照现有 `LOGIN_REQUIRED`/`BROWSER_SESSION_EXPIRED` 语义回到可行动的登录状态。
6. 不改搜索结果 GET、批次创建、整批 retry 或研究重检索/refresh 路径；本修复只解决已有 import-item 的登录/继续/单条恢复。没有必要新增 schema、迁移或公开接口。

## 现有测试与缺口

已有保护应继续通过：

- `tests/paper_discovery/test_paper_import_batch_service.py`：过期 search session + durable snapshot 可执行、缺失 `search_expires_at` 的 durable batch 可恢复、重启后从 SQLite 快照恢复、损坏快照要求 rebuild。
- `tests/paper_discovery/test_paper_import_batch.py`：快照/attempt 跨重启持久化、快照篡改触发 `SNAPSHOT_REBUILD_REQUIRED`。
- `tests/paper_discovery/test_paper_browser.py`：服务端快照与 allowlist、零 KB 写入、缺失/过期 browser session、精确 session 关闭。
- `tests/paper_discovery/test_paper_import_batch_api.py`：server snapshot resume、登录后 resume、browser session race 的 424 脱敏错误。
- `tests/paper_discovery/test_paper_browser_manager.py`：TTL 回收、profile lock、context 重开、过期后 fail-closed。

本修复必须补的最小缺口：

1. 路由测试：expired `search_sessions` + 完整 durable snapshot 时，`login` 仍返回 opened，并使用快照中的受控 ACM/IEEE URL；不读取客户端 URL、不触碰 KB。
2. 路由/API 测试：同一场景在服务/进程内 session 重新打开后，`resume` 不返回 `SEARCH_EXPIRED`，而继续走既有 downloader、CAS、item 状态和精确 session 清理。
3. 负向测试：持久快照缺失、hash 损坏、candidate/search 身份不匹配时，仍 fail-closed（`SNAPSHOT_REBUILD_REQUIRED` 或既有搜索门禁），且 browser manager 不被调用；allowlist/SSRF 与现有测试保持不变。
4. 生命周期回归：browser session TTL 到期只回收临时浏览器资源，批次仍为 `waiting_login`，下一次 login 可重新打开同一 persistent profile；不把 session TTL 改成无限或修改任务/搜索 TTL。

## 验收口径

实现后先跑上述后端定向测试和静态检查，再用实际已有 batch 做只读 GET 状态确认；真实登录/继续 smoke 需在实现、评审和部署门禁之后执行。成功标准是“过期搜索仍可从完整服务端快照打开受控登录页并继续”，而不是延长 live-search TTL、重跑目录检索或宣称 publisher 授权永不过期。

## 产品使用步骤：随时打开登录并恢复

以下步骤用于已有 `waiting_login` 导入条目。它允许用户在搜索会话过期、服务重启或稍后方便时重新打开登录；不要求重新检索，也不把“打开登录窗口”当作下载或认证完成。

1. **打开待处理入口**：打开当前部署的服务首页，点击左侧“论文检索”，在“导入进度”/“需要登录后继续”区域找到目标 ACM 条目；本次真实样本的 `item_id` 为 `9eed783f-ff98-4021-99dd-1ab2787688cb`，所属批次为 `1a76e369-c638-4f2c-a430-42552a1e7012`。页面应显示“等待登录”或“需要登录后继续”，而不是要求重新搜索。
2. **随时打开受控登录**：在该条目或“待处理论文”卡片点击“打开登录”。等待页面提示“已打开既有浏览器登录，请完成登录后点击‘登录后继续’”，并等待本机既有 ACM 浏览器窗口打开。页面只使用服务端已核验的持久快照 URL；用户不在聊天框、页面表单之外或任何日志中提交密码/Cookie。
3. **在本机完成登录**：切换到刚打开的受控 ACM 浏览器窗口，按发布方页面完成登录/授权；等待页面加载出论文访问页或授权完成提示。若暂时不方便登录，可直接关闭窗口并稍后重新执行第 2 步，批次/item 仍保持 `waiting_login`，不会因搜索 TTL 过期而丢失快照。
4. **提交继续**：回到“论文检索”页面，点击同一条目的“登录后继续”。等待按钮短暂进入处理中状态，并看到“已提交登录完成，正在同步当前研究任务状态”；随后点击页面的刷新/重新打开任务详情，等待该条目显示下载、校验、入库或新的失败状态。不要把“已打开登录”或 HTTP 200 `opened` 当作 PDF 已下载、已认证或已入库。
5. **查看后续结果**：只有页面明确显示论文已完成/已入库，并且 root 保存了对应真实请求、响应、item/document ID、最终状态和产物路径，才可记录为下载完成。若仍为“等待登录”，可再次点击“打开登录”；若变为“失败”，使用“重试”，或在页面提供时选择“上传 PDF”并完成身份确认。`waiting_login` 不走仅支持 `failed` 的重试语义。

### 提示、等待与恢复

- **已打开登录**：当前真实证据只证明 `POST /api/papers/import-items/9eed783f-ff98-4021-99dd-1ab2787688cb/login` 返回 HTTP 200、`status=opened`、`site=acm`；它不证明登录凭据已通过、PDF 已下载或论文已认证。
- **搜索已过期但快照可用**：继续使用“打开登录”即可；不点击“重新检索”、不要求用户重建研究任务。服务重启后仍先从持久快照恢复，临时浏览器 session 过期也只需重新打开登录。
- **窗口/会话不可用**：页面提示 browser/session 过期或 424 时，先重新点击“打开登录”；若仍失败，保留 `waiting_login` 和页面错误，稍后在服务所在电脑重试，不把它改写为下载失败。
- **快照损坏或身份不一致**：若出现 `SNAPSHOT_REBUILD_REQUIRED`、`INVALID_SEARCH_SNAPSHOT` 或受控来源错误，停止点击并记录页面提示；不要使用客户端 URL、任意链接或过期搜索结果绕过门禁，交由 root 处理修复。
- **继续后进入失败**：点击“重试”只针对 `failed`；若下载仍不可得，按页面选择“上传 PDF”并勾选身份确认。确认前不写入知识库，错误论文不得绑定候选。

## 当前真实产物与签收边界

- 真实登录请求说明：`docs/sdd/plans/032/artifacts/20261026-login-recovery/request.md`。
- 真实响应：`docs/sdd/plans/032/artifacts/20261026-login-recovery/login-response.json`。
- 前端 issue/login/recovery 交接与标签契约：`artifacts/spec-032/task-12/frontend-report.md`。
- 实现、独立复审与后端定向回归：`2026-10-26-login-recovery-implementation.md`、`2026-10-26-login-recovery-review.md`、`2026-10-26-login-recovery-test.md`。
- 2026-10-26 同步边界：本次窄修已完成“过期 search + 完整 durable snapshot → 受控 ACM login 打开”路径，HTTP 200、`status=opened`、`site=acm` 仍不代表下载完成、publisher 已认证或后续入库。认证后 resume、PDF 下载/校验、KB 入库和其它 Spec032 范围没有在本次验证，Spec032 整体继续保持暂停，不能标为整体完成。

## Backend-dev 交接（历史启动条件；当前窄修已由实现报告承接）

以下启动条件保留为历史交接记录：仅在根会话关闭 KB 分支并创建 `codex/fix-paper-login-recovery` 后启动；当前工作树的 KB/frontend 改动不得作为本 Task 的实现基线。当前窄修的实际代码范围、评审和回归以本计划上方链接的实现/复审/测试报告为准。角色配置要求依次读取 `progress-logging`、`strategic-compact`、`backend-patterns`、`regression-guard`、`tdd-workflow`、`python-testing`；本 Task 只允许改 `backend/**` 与后端测试。

### TDD 最小顺序

1. **RED（两个测试文件）**：先在 `tests/paper_discovery/test_paper_import_batch_service.py` 增加 durable snapshot 在过期 search session 后仍可解析的 wrapper 契约；再在 `tests/paper_discovery/test_paper_browser.py` 增加 expired search + valid durable snapshot 时 login 仍打开受控 URL 的路由契约。测试必须使用 `tmp_path`/fake boundary，不初始化 `data/paper_search`，不 POST、不启动浏览器。
2. **GREEN（两个生产文件）**：在 `backend/app/paper_discovery/application/paper_import_batch_service.py` 增加一个 public-internal 薄 wrapper（建议 `get_item_snapshot_candidates`），内部委托现有 `_snapshots_for(batch_id, None)` 并校验 item/batch/candidate/search 身份；在 `backend/app/api/routes_paper.py` 让 `_paper_snapshot_for_item` 调用 wrapper。路由不得直接调用私有方法；不新增 HTTP API、schema、迁移或浏览器 TTL 配置。hash/损坏快照应继续 fail-closed，现有状态/CAS/allowlist/SSRF 逻辑不动。

### 建议命令

RED（写完测试后预期失败）：

```text
.venv/bin/python -m pytest -q \
  tests/paper_discovery/test_paper_import_batch_service.py::test_item_snapshot_candidates_reuse_durable_snapshot_after_search_expiry \
  tests/paper_discovery/test_paper_browser.py::test_login_opens_from_durable_snapshot_after_search_expiry
```

GREEN/定向回归：

```text
.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_import_batch_service.py tests/paper_discovery/test_paper_browser.py tests/paper_discovery/test_paper_import_batch_api.py
.venv/bin/ruff check backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/api/routes_paper.py tests/paper_discovery/test_paper_import_batch_service.py tests/paper_discovery/test_paper_browser.py tests/paper_discovery/test_paper_import_batch_api.py
.venv/bin/python -m py_compile backend/app/paper_discovery/application/paper_import_batch_service.py backend/app/api/routes_paper.py
.venv/bin/python scripts/check_test_layout.py
```

依赖边界：当前 Spec032 总体仍暂停，本次仅完成上述 login/resume 恢复窄范围；未顺手处理整批 retry、搜索刷新、浏览器 TTL 或 Spec032 收口。真实窄修 login API 已有独立产物，认证后 resume/download/import 仍是后续边界。

## 2026-10-26 窄修收口（当前状态）

- 范围：已有 `waiting_login` item 使用 hash/身份核验的 durable snapshot 绕过过期 search TTL 的错误阻断；保留受控 ACM/IEEE origin、SSRF、CAS、浏览器 session TTL 与 fail-closed 语义。
- 证据：集成定向回归 `64 passed, 0 failed, 0 skipped`；真实旧批次 login 返回 HTTP `200`、`status=opened`、`site=acm`；验收报告窄修矩阵 `10/10 PASS`。
- 签字：[`docs/sdd/reviews/032-acceptance-review.md`](../../reviews/032-acceptance-review.md) 后续范围澄清栏为 tester `READY_FOR_USER`、architect `GO`。
- 明确未验证：认证后 resume、PDF 下载/校验、KB 入库、来源年度覆盖及其余暂停范围；不要把 `opened` 响应写成下载或入库成功。

