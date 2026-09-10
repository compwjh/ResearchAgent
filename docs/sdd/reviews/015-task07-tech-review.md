# Spec 015 Task07 论文检索 Tab 技术复核

- 评审者：当前协作 Agent
- 角色：独立开发主管（Tech Lead）
- 评审时间：2026-09-05 00:05:24 +0800
- 复核范围：Spec015、Task07 计划与实现记录、`frontend/index.html`、`frontend/app.js`、`backend/app/api/routes.py`、`backend/app/api/schemas.py` 及相关定向测试
- 评审约束：只读复核；未修改业务代码、测试或 Git，未提交、未 push、未 reset/stash/clean
- 进展日志：`.codebuddy/agent-logs/tech-lead-spec015-task07-20260905-000524.md`

## 结果状态和摘要

**打回。** 主搜索、服务端 `search_id/candidate_id` 导入边界、登录/续传请求的 opaque ID 使用和论文动态内容的安全 DOM 渲染基本成立；语法、后端定向测试和差异检查通过。但会议搜索调用了后端不存在的路径，且没有新增会议 API，导致 A3/Task07 的会议管理流程不可用。另有多会议结果排名与多批次状态展示缺陷，以及结果选择控件的可访问性缺口，不能按当前实现进入验收。

## 阻塞问题

| 编号 | 等级 | 代码事实 | 最小修复方向 |
|---|---|---|---|
| T7-1 | P1 | `frontend/app.js:708-718` 请求 `GET /api/papers/conferences/search?q=...`，但 `backend/app/api/routes.py:263-310` 只有会议列表、PATCH 启停和 DELETE 保护，没有会议搜索路由；同样没有 `POST /api/papers/conferences`。OpenAPI 缺少这两个方法，TestClient 实测 GET/POST 均为 405。脚本对搜索结果仅创建不可选的普通 `li`，没有新增/保存动作。 | 不得保留臆造 API。若本任务继续支持 A3，先由后端提供并在 schemas 中固定真实搜索/新增契约，再用服务端候选标识渲染可选项；若沿用 Task02 Venue Search blocked，则移除/明确禁用会议搜索与新增 UI，并将 A3 移出本任务验收，不能显示“搜索完成”。 |
| T7-2 | P1 | 后端搜索端点是单会议；前端 `frontend/app.js:511-537` 对多会议并行调用后直接拼接各响应，不按全局 `final_score/rank` 形成服务端定义的合并顺序，也没有跨响应去重。多会议时列表不保证“严格按服务端排名降序”。 | 固定真正的多会议搜索契约（推荐服务端生成单一 search snapshot、全局排序和去重），前端只按该响应顺序展示；或明确按会议分组显示，不能把各会议局部 rank 静默当作全局 rank。 |
| T7-3 | P1 | `frontend/app.js:556-590` 按 `search_id` 创建多个批次；`renderPaperBatch()` 在 `:617-619` 每次先清空共享 `#paper-import-items`，轮询 `:607-612` 又逐批渲染。因此多会议选择导入时，只有最后一个批次的逐项状态、失败重试和 waiting_login 项可见，其他批次无法操作。 | 为每个 batch 建立独立可持久渲染容器，或在前端把多个后端批次聚合为一个明确的 UI 状态模型；所有批次的状态、重试和登录动作必须可见且按 item 隔离。 |
| T7-4 | P1 | `frontend/app.js:472-475` 创建结果选择 checkbox 时没有 label/`aria-label`；读屏用户无法知道选择的是哪篇论文。`frontend/index.html:149` 将会议结果声明为 `listbox`，但 `app.js:714-716` 只生成没有 `role="option"`、`aria-selected` 或键盘选择行为的 `li`。 | 为每个结果 checkbox 提供包含标题的可访问名称；会议搜索结果若保留 listbox，补齐 option/选中/键盘交互，否则使用普通列表并提供真实的“添加”按钮。 |
| T7-5 | P2 | `frontend/index.html:19` 初始显示论文入口且 `paperState.enabled` 初始为 true；`frontend/app.js:745` 启动即请求会议配置，开关关闭只能在请求返回后隐藏入口。`setPaperEnabled(false)`（`:398-402`）也不停止已存在的批次轮询。Task07 验收明确要求开关关闭时入口和请求均不出现。 | 用服务端启动配置/页面引导状态在首屏决定入口；关闭时清理/停止 search、batch poll 和待发动作，并补开关关闭回归。若保留一次能力探测，需修订验收文字为“除能力探测外不发起业务请求”。 |
| T7-6 | P2 | `frontend/index.html:19` 的论文导航固定 `aria-current="false"`，`showView()`（`frontend/app.js:748-756`）只切换 `.active`，不更新 `aria-current`；当前视图对读屏用户不可感知。 | 切换视图时将当前导航项设为 `aria-current="page"`，其他项移除该属性或设为 false，并为现有导航保持一致语义。 |

## 已通过或基本通过项

| 复核项 | 结论 | 证据 |
|---|---|---|
| `search_id/candidate_id` 归属 | 通过（局部） | 搜索响应中的服务端 `search_id` 被保存，`candidate_id -> search_id` 映射用于导入；导入请求只提交 `search_id/candidate_id`，不接受前端 URL、标题或作者作为导入依据（`frontend/app.js:556-577`；后端请求模型为 `extra="forbid"`）。多会议合并后的排序/批次可见性仍见 T7-2/T7-3。 |
| 轮询与离开 Tab | 部分通过 | 批次状态保存在页面内 `Map`，切换到其他视图不会清除状态；轮询不依赖当前 Tab，满足同一页面离开再返回的基本意图。多批次共享容器导致状态呈现不完整；开关关闭时轮询未停止，见 T7-3/T7-5。 |
| 登录续传 | 通过（客户端契约） | `frontend/app.js:662-677` 使用 `/api/papers/import-items/{item_id}/login|resume`，请求体为空对象；没有客户端 `login_url`、Cookie 或凭证。真实性能和合法账户验收仍受 Task06 外部环境阻塞，不由本次 UI 复核伪造放行。 |
| 知识库跳转 | 通过 | `frontend/app.js:680-686` 以服务端 `paper_id` 切换 KB、加载列表，并通过 `data-paper-id` 定位和聚焦；没有拼接下载 URL。 |
| XSS/`innerHTML` | 通过（论文区域） | 论文标题、作者、摘要、批次标题、错误和状态均使用 `textContent`；论文区域没有把服务端文本传入 `innerHTML`。聊天既有 Markdown 渲染不属于 Task07 论文动态字段。 |
| 错误与加载语义 | 部分通过 | 搜索和批次有 `aria-live`/`aria-busy`/`role="alert"` 及按钮禁用；但会议搜索 405 被映射成泛化错误，且不可访问的 listbox/结果选择控件仍影响键盘和读屏验收。 |

## 验证命令与结果

`node --check frontend/app.js`：退出码 `0`。

`.venv/bin/python -m pytest -q tests/test_paper_discovery_api.py tests/test_paper_import_batch_api.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_store.py`：`37 passed, 4 subtests passed`，退出码 `0`。

`.venv/bin/python -m compileall -q backend/app/api/routes.py backend/app/api/schemas.py`：退出码 `0`。

`git diff --check -- frontend/index.html frontend/app.js backend/app/api/routes.py backend/app/api/schemas.py`：退出码 `0`。

OpenAPI 静态契约检查仅发现会议搜索、新增两个方法缺失；TestClient 实测 `GET /api/papers/conferences/search` 与 `POST /api/papers/conferences` 返回 `405 Method Not Allowed`。本轮未启动服务，也未执行真实 ACM/IEEE 账号验收；不将其伪造为通过。

## 放行前最小修订清单

1. 解决 T7-1：落地真实会议搜索/新增 API，或依据 Task02 blocked 决策移除未实现的 UI 与 A3 声明。
2. 解决 T7-2/T7-3：明确多会议搜索的全局排序/去重和单一 search snapshot，或提供独立可见的分组列表与批次面板；补多会议导入回归。
3. 解决 T7-4/T7-6：补结果选择的 accessible name、会议结果 listbox 语义/键盘操作、导航 `aria-current`。
4. 解决 T7-5：补首屏功能开关和关闭时停止轮询的可验证契约。
5. 由 tester 重新执行 Task07 A1–A9、A12–A15；Task06 的 A10/A11 仍需真实合法权限环境，不得由静态检查替代。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：打回**
- 签字时间：2026-09-05 00:05:24 +0800
