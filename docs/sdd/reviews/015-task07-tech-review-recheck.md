# Spec015 Task07 修复后技术复核

- 评审者：当前协作 Agent
- 角色：独立开发主管（Tech Lead）
- 评审模型：本回合 `gpt-5.6-luna/high`
- 评审时间：2026-09-05 00:16–00:25（Asia/Shanghai）
- 复核范围：Task07 计划、既有技术复核、全部 Task07 implementation/repair reports、`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`、论文相关后端路由/Schema、前端契约与论文检索/导入测试
- 评审约束：只读复核；未修改业务代码或测试，未执行 commit、push、reset、stash、clean
- 进展日志：`.codebuddy/agent-logs/tech-lead-spec015-task07-recheck-20260905-001647.md`

## 结论

**打回。**

修复已闭合批次 DOM 互相覆盖、等待登录项不可见、论文动态文本注入、客户端自带 URL 导入、结果 checkbox accessible name 和会议搜索结果基本键盘语义；后端也已提供真实的受控会议搜索 GET，且没有越界的自定义会议 POST。

但功能开关与导航无障碍硬约束仍未闭合：前端启动时无条件请求会议配置，关闭后也不停止已有搜索/批次轮询；`showView()` 不更新导航项 `aria-current`。此外，多会议结果仍是多个单会议快照在客户端拼接，虽按分数/rank/输入序号形成确定顺序，但未使用统一服务端快照、未跨响应去重，也未实现 Spec015 完整 tie-break；会议搜索 UI 还绕过了已提供的真实 GET，仅在已加载配置上本地过滤。当前不应进入验收放行。

## 验证结果

| 检查项 | 命令 / 证据 | 结果 |
|---|---|---|
| JavaScript 语法 | `node --check frontend/app.js` | 通过，退出码 0 |
| Task07/论文定向回归 | `.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py tests/test_paper_discovery_api.py tests/test_paper_import_batch_api.py tests/test_paper_discovery_search.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_store.py tests/test_paper_import.py tests/test_paper_import_identity.py tests/test_paper_download.py tests/test_paper_download_security.py` | 通过，`100 passed, 9 subtests passed` |
| Python 编译 | `.venv/bin/python -m compileall -q backend/app` | 通过，退出码 0 |
| 差异检查 | `git diff --check` 覆盖 Task07 HTML/JS/CSS、论文路由/Schema 与前端/API 测试 | 通过，退出码 0 |
| 会议搜索 API | OpenAPI 与 TestClient：`GET /api/papers/conferences/search` 已注册并由测试覆盖；按 server-side 配置筛选安全 payload | 通过（后端） |
| 自定义会议 POST 越界 | OpenAPI 不含 `POST /api/papers/conferences`；TestClient 返回 405 | 通过 |

## 重点复核

### 1. 会议搜索真实 API与自定义 POST 边界

后端 `backend/app/api/routes.py:264-294` 已提供真实 `GET /api/papers/conferences/search?q=`，仅在服务端已有会议配置上做大小写不敏感匹配，返回 `_conference_payload()` 的安全字段；空查询、超长查询、功能关闭和存储异常均有稳定错误体。`tests/test_paper_discovery_api.py:43-102` 定向测试通过。

`POST /api/papers/conferences` 没有注册，TestClient 返回 405，符合当前 Task02 Venue Search/custom conference blocked 的收窄边界；前端 `frontend/app.js` 也没有发送自定义会议 POST。

仍有一个集成缺口：`frontend/app.js:763-787` 的 `searchPaperConferences()` 不调用上述 GET，而是对 `paperState.conferences` 做本地过滤，且只匹配 `name/short_name`，没有匹配后端允许的 `conference_id`。因此“真实会议搜索 API”本身已存在，但论文 Tab 的会议搜索并未消费该 API，也无法发现尚未通过初始列表加载的服务端配置。该项应在验收前明确为“仅搜索已加载配置”或改为调用真实 GET。

### 2. 多会议稳定排序与去重

`frontend/app.js:514-556` 会按选中会议分别请求单会议 `/api/papers/search`，再按 `final_score`（回退 `rerank_score/retrieval_score`）、`rank`、合并索引排序。由于 `Promise.all` 保持 `conferenceIds` 的输入顺序，这一实现对相同输入通常是确定的；修复报告声称的“多会议结果不按服务端顺序”问题已得到部分改善。

但当前仍不存在统一的多会议 `search_id`/server snapshot。前端没有跨响应 DOI、DBLP key 或规范标题去重；相同分数/rank 只按合并索引，而不是 Spec015 要求的 `initial_rank → year desc → normalized_title → candidate_id` 完整 tie-break。该实现不能证明多会议结果严格遵循服务端定义的全局 rank，建议改为服务端统一多会议搜索快照，或在 Task07 契约中明确客户端合并、去重和完整 tie-break。

### 3. 多批次互不覆盖与登录项可见

`frontend/app.js:620-696` 以 `data-batch-id` 为键为每个批次创建独立容器；轮询更新只替换当前批次容器，不再清空共享 `#paper-import-items`。失败重试按钮、条目状态、知识库跳转和等待登录按钮都挂在对应批次下，多个批次可以同时显示。等待登录项在每个批次内部创建可见的 `.paper-login-queue`，并提供“打开登录”和“登录完成，继续”按钮；登录/续传请求路径使用 `encodeURIComponent(item_id)`，不传 URL 或凭证。此项通过（真实浏览器账号验收仍由 Task06 环境门禁负责）。

### 4. ARIA 与键盘

通过项：

- `frontend/app.js:472-478` 为每个结果 checkbox 设置含论文标题的 `aria-label`。
- `frontend/app.js:772-783` 为会议搜索结果设置 `role="option"`、`aria-selected`、`tabIndex=0`，Enter/Space 可选择。
- HTML 使用 `fieldset/legend`、显式 `label`、`aria-live`、`role=status/alert`、`aria-busy`，CSS 提供论文视图控件的 `:focus-visible` 焦点环。

阻塞项：`frontend/index.html:19` 将论文导航固定为 `aria-current="false"`，但 `frontend/app.js:817-825` 的 `showView()` 只切换 `.active`，不把当前项更新为 `aria-current="page"`，也不移除其他导航项的当前语义。切换到论文 Tab 时，读屏用户无法获得当前页面语义；这是前次 T7-6 未修复项。

### 5. 功能开关

后端请求级开关短路已通过既有 API 测试；但前端仍有两处违反“关闭时入口和请求均不出现”的事实：

1. `frontend/app.js:814` 在脚本初始化时只要 `paperNav` 存在就无条件调用 `loadPaperConferences()`；`paperState.enabled` 初始为 `true`，因此即使 `PAPER_DISCOVERY_ENABLED=false`，首屏仍先显示导航并发出 `GET /api/papers/conferences`，收到 503 后才隐藏。
2. `frontend/app.js:399-403` 的 `setPaperEnabled(false)` 只隐藏入口/视图，不 abort `searchController`，不清理或停止 `batchPollTimer`，也不阻止已经排队的批次状态请求。

需要由服务端提供首屏能力状态/注入配置，或把验收契约改为允许一次能力探测；同时关闭时必须取消搜索、停止轮询并清理待发动作。此项是前次 T7-5 的未闭合阻塞。

### 6. Opaque ID、导入边界与文本安全

通过：

- `PaperImportRequest` 与 `PaperImportBatchRequest` 使用 `extra="forbid"`，导入路由在 `_paper_server_snapshot()` 中用 `search_id/candidate_id(s)` 解析服务端候选，客户端不能提供 `pdf_url`、标题或作者替代候选快照。
- 前端单篇/批量导入仅提交 `search_id`、`candidate_id` 或 `candidate_ids` 及服务端可验证的幂等键；login/resume 只提交空对象和 opaque `item_id`。
- `renderPaperResults()` 与 `renderPaperBatch()` 的论文动态内容全部使用 `textContent`/DOM 节点；论文专属代码区域（`frontend/app.js:314-816`）没有 `innerHTML`。全局文件中的既有聊天 Markdown `innerHTML` 不属于本 Task07 论文字段，未将其误计为本项缺陷。

## 放行前必须完成

1. 修复开关：首屏关闭时不显示入口、不发起论文配置/业务请求；关闭后 abort 搜索并停止批次轮询。
2. 修复导航可访问性：`showView()` 同步维护所有导航项的 `aria-current`，并为论文 Tab 补键盘/读屏回归契约。
3. 明确并实现会议搜索契约：要么前端调用已存在的受控 GET（并允许/拒绝 `conference_id` 搜索写入测试），要么在文档和 UI 上明确“仅筛选已加载服务端配置”，避免显示为通用会议发现。
4. 明确多会议全局排序/去重责任；至少补充跨会议重复候选、相同 score/rank 的 year/title/candidate tie-break 回归。若要求严格服务端 rank，应新增统一 server snapshot，而不是继续拼接单会议快照。
5. 修复后重新执行 Task07 A1–A9、A12–A15 的 tester 验收；Task06 的 ACM/IEEE 真实登录仍不得以离线测试替代。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：打回**
- 签字时间：2026-09-05 00:25 +0800
