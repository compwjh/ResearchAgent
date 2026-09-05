# 验收评审：Spec015 Task07 论文检索 Tab 最终 Gate Fix

- 执行角色：测试（QA）
- 验收时间：2026-09-05 00:37（Asia/Shanghai）
- 验收范围：最新 Task07 JavaScript gate fix、受控会议搜索 API、论文检索/导入定向回归，以及静态 flag、ARIA、搜索、去重、批次和 XSS 检查
- 改动约束：未修改业务代码或测试；未执行 commit、push、reset、stash、clean
- 进展日志：`.codebuddy/agent-logs/tester-spec015-task07-final-20260905-003700.md`

## 一、结论

**Task07 最终验收不通过（自动化定向回归通过；仍有可确认的功能缺口、A3 外部阻塞和全量回归环境/顺序问题）。**

最新 gate fix 已闭合导航 `aria-current`、受控会议搜索 GET、批次容器隔离、导入 opaque ID 和论文动态文本安全渲染等门禁。A3 自定义会议不宣称通过：DBLP Venue Search 当前仍被 Task02 的外部依赖门禁阻塞，现有实现明确不提供自定义会议 POST/新增闭环。

仍不能放行的两项代码事实：

1. `frontend/app.js` 的页面初始化默认把论文功能视为开启；`/api/health` 不返回 `paper_discovery_enabled`。在 `PAPER_DISCOVERY_ENABLED=false` 下 TestClient 实测健康响应仍只有 `status/model/models`，因此服务端关闭状态无法在首屏可靠隐藏论文入口。
2. 跨会议去重仅使用 `candidate_id` 和规范化 `title/year/conference`，没有 DOI 或 DBLP key；排序比较器也只有分数、`rank`、响应序号和候选序号，未满足 Spec015 要求的 `initial_rank → year desc → normalized_title → candidate_id` 完整 tie-break。

## 二、执行证据

| 检查项 | 命令/证据 | 结果 |
|---|---|---|
| JavaScript 语法 | `node --check frontend/app.js` | 通过，退出码 0 |
| 前端契约 | `.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py` | 通过，3 passed |
| 论文定向回归 | `.venv/bin/python -m pytest -q tests/test_paper_discovery_api.py tests/test_paper_import_batch_api.py tests/test_paper_discovery_search.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_store.py tests/test_paper_import.py tests/test_paper_import_identity.py tests/test_paper_download.py tests/test_paper_download_security.py` | 通过，97 passed、9 subtests |
| Python 编译/差异 | `.venv/bin/python -m compileall -q backend/app frontend`；`git diff --check` | 均通过，退出码 0 |
| 论文 API 路由 | `app.openapi()["paths"]` | `POST /api/papers/search`、`GET /api/papers/conferences/search`、`POST /api/papers/imports`、批次状态及 login/resume 路由存在；`POST /api/papers/conferences` 未注册 |
| 关闭开关健康状态 | `PAPER_DISCOVERY_ENABLED=false` + TestClient `GET /api/health` | 200，但响应键仅 `model/models/status`，缺少 `paper_discovery_enabled` |
| 全量 pytest | `.venv/bin/python -m pytest -q` | **失败：505 passed、1 skipped、38 subtests、3 failed、5 warnings** |
| 全量失败隔离复测 | 单独运行 3 个失败测试 | 通过：3 passed；浏览器 manager 两项在注入公共 DNS resolver 后通过，说明默认 DNS 受沙箱限制；既有 Agent 下载测试单独运行通过 |

全量失败明细：

- `tests/test_api.py::AgentApiTests::test_download_with_use_skill_records_skill_name`：全量顺序中收到 503 而期望 200；单独运行通过。
- `tests/test_paper_browser_manager.py::test_authenticated_pdf_request_uses_context_request_and_safe_result`：当前沙箱解析 `dl.acm.org` 失败，被安全层映射为 `DOWNLOAD_BLOCKED`；注入测试公共 resolver 后通过。
- `tests/test_paper_browser_manager.py::test_authenticated_pdf_request_maps_forbidden_without_response_details`：同一 DNS 阻塞导致未到达 fake 403 响应；注入 resolver 后通过。

## 三、Task07 静态验收矩阵

| 检查项 | 结论 | 证据与边界 |
|---|---|---|
| 功能 flag | **部分通过/不放行** | `readPaperFeatureFlag()` 与 `setPaperEnabled()` 存在；关闭会 abort 搜索、清理轮询、阻止后续动作（`frontend/app.js:411-426`）。但健康响应不注入服务端 flag，默认值仍为 true，无法证明 `PAPER_DISCOVERY_ENABLED=false` 的首屏入口消失。关闭时已发出的批次 fetch 返回后也没有二次 enabled 守卫（`frontend/app.js:703-708`）。 |
| ARIA/键盘 | 通过（静态） | `showView()` 为所有导航项同步 `aria-current`（`frontend/app.js:906-918`）；结果 checkbox 有标题 accessible name，会议结果使用 `role=option`、`aria-selected`、Enter/Space。未执行真实读屏器。 |
| 会议搜索 | 通过（收窄契约） | 前端调用 `GET /api/papers/conferences/search?q=`（`frontend/app.js:850-875`），服务端只匹配已有安全配置字段。没有伪造 DBLP Venue Search，也没有自定义会议 POST。 |
| 跨会议去重/排序 | **不通过** | `paperCandidateIdentityKeys()` 仅生成 candidate ID 与 title/year/conference key（`frontend/app.js:497-509`），遗漏 DOI/DBLP key；比较器未实现 Spec015 完整 tie-break（`frontend/app.js:512-528`）。 |
| 批次隔离/等待登录 | 通过（静态+定向回归） | `renderPaperBatch()` 按 `data-batch-id` 创建并只替换对应容器；轮询按所有 batch ID 更新，等待登录项提供独立 login/resume 动作。真实浏览器登录未执行。 |
| XSS/动态文本 | 通过（静态+契约） | `renderPaperResults()`、`renderPaperBatch()` 论文字段均使用 DOM 节点与 `textContent`，对应 renderer 区域无 `innerHTML`；导入只提交 server-side `search_id/candidate_id(s)`。聊天既有 Markdown `innerHTML` 不属于论文动态字段。 |

## 四、验收场景与环境限制

| 验收点 | 结论 | 说明 |
|---|---|---|
| A1 独立入口/关闭 | 阻塞 | 静态入口和运行时隐藏逻辑存在，但服务端首屏 flag 缺失；未完成 GUI 证明入口行为。 |
| A2 默认范围 | 离线逻辑通过，GUI 未执行 | 默认会议、年份初始化逻辑和 API 测试存在；没有桌面浏览器可用性证据。 |
| A3 自定义会议 | **阻塞（不伪造通过）** | DBLP Venue Search blocked；当前 API 只搜索已配置会议，`POST /api/papers/conferences` 未注册，不能完成搜索/新增/保存闭环。 |
| A4–A6 检索、过滤、降级 | 定向回归通过 | 由论文 discovery/search/API 测试覆盖；未执行真实外部源完整链路。 |
| A7–A9 单篇、批量、幂等 | 离线回归通过，真实 UI 未执行 | 导入/批次/身份/下载安全定向测试通过；未在浏览器实际下载并检查知识库页面。 |
| A10 ACM 登录 | 阻塞 | `.venv` 中 `import playwright` 为 `ModuleNotFoundError`；无可核验合法账户；CUA 返回 Mac locked，无法进行 GUI。 |
| A11 IEEE 登录 | 阻塞 | 同 A10。 |
| A12 命名兼容 | 定向回归通过 | 身份、导入和下载定向测试通过。 |
| A13 安全异常 | 定向回归通过 | URL/SSRF、伪 PDF、超限、认证错误脱敏等定向测试通过。 |
| A14 排序质量 | 未执行 | 本轮没有冻结的 12+ 查询人工标注集与 nDCG 复测，不作通过声明。 |
| A15 回归交付 | **不通过** | 定向回归通过，但全量 pytest 有 3 项失败，且未能完成服务启动、GUI、窄屏和真实外站登录验收。 |

## 五、后续放行条件

1. 由实现方提供服务端首屏 `paper_discovery_enabled`（或等效静态注入）并补关闭状态回归，且对已发出的批次响应增加 enabled/serial 守卫。
2. 明确多会议结果的服务端/客户端责任；至少按 DOI、DBLP key、规范标题去重，并补齐 Spec015 tie-break 回归。
3. DBLP Venue Search 恢复后，补做 A3 搜索、选择、新增、修改、停用及内置删除保护；在此之前继续保留阻塞。
4. 在可用 Playwright、解锁 GUI 和合法账户环境执行 A1/A2/A7–A11 的真实 UI/登录验收；另行完成窄屏和排序质量集复测。
5. 诊断全量 pytest 的共享状态/顺序失败与沙箱 DNS 限制，再重跑全量门禁。

## 六、签字

- 测试（QA）：**通过上述证据执行；结论为整体验收不通过/部分阻塞**
- 开发主管（Tech Lead）：**待签字**
