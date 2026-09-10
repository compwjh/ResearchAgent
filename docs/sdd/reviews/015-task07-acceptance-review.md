# 验收评审：Spec015 Task07 论文检索 Tab 修复后独立复核

- 评审角色：测试（tester）
- 关联 spec：`docs/sdd/specs/015-security-paper-discovery.md`
- 关联计划：`docs/sdd/plans/015/task-07-paper-discovery-tab.md`
- 复核实现：`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`、`backend/app/api/routes.py`、`backend/app/api/schemas.py`
- 进展日志：`.codebuddy/agent-logs/tester-spec015-task07-acceptance-20260905-001714.md`
- 评审时间：2026-09-05（Asia/Shanghai）
- 变更约束：未修改业务代码、测试、配置或 Git 状态；仅新增本报告与进展日志；未执行 commit/push/reset/stash/clean。

## 固定字段

- 结果状态和摘要：**自动化回归通过；Task07 整体验收不通过（仍有 P1/P2 功能与环境阻塞）**。上一轮多批次容器、结果 checkbox accessible name、会议搜索 405 的前端臆造调用已部分修复；但自定义会议 A3 尚未实现，多会议结果未按 DOI/DBLP key/规范标题去重，功能开关关闭时首屏仍显示入口并发起请求，导航 `aria-current` 未随视图更新。未执行桌面/窄屏 GUI 和真实 ACM/IEEE 登录，不能伪造通过。
- 改动文件：**无业务改动**（仅新增本报告与 `.codebuddy/agent-logs/tester-spec015-task07-acceptance-20260905-001714.md`）。
- 测试命令/退出码/结果：`node --check frontend/app.js` 退出码 0；`tests/test_frontend_paper_contract.py` 为 `3 passed`；论文检索/导入 API 定向测试为 `17 passed, 9 subtests passed`；全量 pytest 为 `509 passed, 5 warnings, 38 subtests passed`，退出码均为 0；前端/后端目标文件 `git diff --check` 退出码 0。
- 产物路径：`docs/sdd/reviews/015-task07-acceptance-review.md`、`.codebuddy/agent-logs/tester-spec015-task07-acceptance-20260905-001714.md`。
- 决策依据：自动化契约、API、全量回归和静态 DOM/XSS/opaque ID 检查均有证据；A3、开关首屏行为、全局去重/排序的缺口由当前代码和 TestClient 实测确认；GUI 与真实外站登录未执行，按验收规则保留阻塞。
- 风险与阻塞：
  - **P1：A3 自定义会议不满足。** `searchPaperConferences()`（`frontend/app.js:763-787`）只筛选已加载且已启用的 `paperState.conferences`，不调用后端 DBLP 搜索；服务端 `GET /api/papers/conferences/search` 也只搜索已有配置，`POST /api/papers/conferences` 实测为 `405 Method Not Allowed`。管理弹层只有启停 PATCH，没有新增/编辑别名流程。
  - **P1：多会议全局去重不满足。** `searchPapers()`（`frontend/app.js:518-555`）将多个单会议响应直接合并并按分数排序，但未按 DOI、DBLP key 或规范化标题去重；同一论文跨会议/来源重复时可能展示多次，`candidateSearchIds` 还会被后写入的同名 candidate 覆盖。
  - **P2：功能开关关闭时仍有首屏入口和请求。** HTML 初始论文导航没有 `hidden`（`frontend/index.html:19`），`paperState.enabled` 初始为 `true`，并在 `frontend/app.js:814` 无条件调用 `loadPaperConferences()`；只有请求返回 `PAPER_DISCOVERY_DISABLED` 后才隐藏。`setPaperEnabled(false)`（`frontend/app.js:399-403`）也未停止已有批次轮询。
  - **P2：导航可访问性语义未闭环。** `frontend/index.html:19` 固定 `aria-current="false"`，`showView()`（`frontend/app.js:817-830`）只切换 active/hidden，不设置当前导航项的 `aria-current="page"`。
  - **环境阻塞：**本轮未启动本地服务、未打开桌面/窄屏浏览器，因此未声称 A1/A2/A4/A8 的真实布局交互通过；未执行合法 ACM Digital Library / IEEE Xplore headed 登录、SSO/验证码、权限 PDF 续传，A10/A11 保持未执行。
- 主 Agent 后续动作：先修复/明确 A3 的真实契约并补新增会议 UI；对多会议结果做服务端 snapshot 或前端可靠去重并保留全局排序；将开关状态前置到页面引导并清理轮询；补 `aria-current`；随后由 tester 在可用浏览器与服务启动后重跑 Task07 A1–A9、A12–A15，并在具备合法账号时另行验收 A10/A11。
- 开始/结束/总耗时：约 2026-09-05 00:17 至 00:21（Asia/Shanghai），约 4 分钟（含定向测试、全量回归及静态复核；全量 pytest 运行约 70 秒）。
- 可用时模型/token/工具统计：模型为本回合 `gpt-5.6-luna`（high）；未提供可核验 token 计数；使用项目虚拟环境 pytest、Node 语法检查、FastAPI TestClient、文本/DOM 静态扫描与 Git 只读检查。未访问外部站点、未使用真实账号。

## 一、测试命令与结果

### 1. 前端语法与契约

```text
node --check frontend/app.js
.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py
```

结果：退出码均为 **0**；`3 passed`。前端论文结果/批次渲染区不使用 `innerHTML`；标题、作者/元数据、摘要、状态、错误均通过 `textContent`；论文区域没有 `pdf_url`、`login_url`、Cookie 或 Authorization 输入；动态论文结果 checkbox 有基于标题的 `aria-label`。

### 2. 论文检索与导入 API

```text
.venv/bin/python -m pytest -q tests/test_paper_discovery_api.py tests/test_paper_import_batch_api.py
```

结果：退出码 **0**；`17 passed, 9 subtests passed`。覆盖稳定错误体、会议查询参数边界、功能关闭、服务端 search snapshot/candidate 解析、单篇/批量导入、重试、登录/续传以及重复/过期边界。

补充 TestClient 事实检查：`GET /api/papers/conferences/search?q=ccs` 返回 200 的既有安全会议配置；`POST /api/papers/conferences` 返回 **405**，确认新增会议接口不存在。`PAPER_DISCOVERY_ENABLED=false` 时，会议列表、会议搜索和合法论文搜索均返回 `503 PAPER_DISCOVERY_DISABLED`。

### 3. 全量回归

```text
.venv/bin/python -m pytest -q
```

结果：退出码 **0**；`509 passed, 5 warnings, 38 subtests passed in 69.72s`。警告为既有 PyMuPDF/Swig 依赖弃用警告。

### 4. 静态一致性

```text
git diff --check -- frontend/index.html frontend/app.js frontend/styles.css \
  backend/app/api/routes.py backend/app/api/schemas.py tests/test_frontend_paper_contract.py
```

结果：退出码 **0**。CSS 静态检查确认论文结果、批次、会议搜索、长文本换行、滚动容器、focus-visible 以及 760px/430px 断点规则存在；但未进行浏览器像素级/实际窄屏布局验收。

## 二、Task07 验收矩阵

| 验收点 | 状态 | 证据与限制 |
|---|---|---|
| A1 独立入口 | 部分通过 | `论文检索` Tab、`#papers-view` 和互斥 `showView` 存在；但关闭开关时初始入口仍可见并会先请求会议配置，未满足“入口和请求均不出现”。 |
| A2 默认范围 | 静态/契约通过，运行时未验 | `loadPaperConferences()` 按 `paper_discovery_default_years` 设置年份，当前年份 2026 时计算 2021–2025；未启动服务/浏览器核验首屏真实呈现。 |
| A3 自定义会议 | **不通过（P1）** | 只能筛选已有配置并启停；无 DBLP 外部搜索和新增 POST，新增接口实测 405。 |
| A4 语义检索 | 部分通过 | 前端使用服务端 `/api/papers/search` 的 opaque `search_id/candidate_id`，合并后按分数排序；未做浏览器或真实源检索，且多会议去重缺失。 |
| A5 主会过滤 | 未执行于 UI | 过滤逻辑在后端服务/测试范围，未启动真实 DBLP 源并查看四会样本。 |
| A6 降级 | API/静态部分通过 | 错误码与 degraded/warnings 文案路径存在；未在 UI 运行时注入 OpenAlex/Reranker/Playwright 故障。 |
| A7 单篇导入 | API 契约通过，端到端未验 | 前端只提交服务端 search/candidate ID，批次状态可渲染；未实际下载 PDF 并在 GUI 中核验知识库跳转。 |
| A8 批量导入 | 静态/API 部分通过 | 每个 batch 有独立 `data-batch-id` 容器，失败重试和 waiting-login 操作按批次隔离；未启动服务做真实轮询。 |
| A9 去重幂等 | 后端回归通过，前端多会议展示不通过 | 服务端导入契约/幂等测试通过；前端多会议结果未按 DOI/DBLP key/规范标题去重。 |
| A10 ACM 登录 | 未执行（环境阻塞） | 未启动 headed Playwright、无可核验合法账号/权限；不得伪造登录续传通过。 |
| A11 IEEE 登录 | 未执行（环境阻塞） | 同上。 |
| A12 命名兼容 | 后端回归通过，Task07 UI 未端到端验 | 相关全量测试通过；未实际导入并在浏览器核验旧记录重建/删除。 |
| A13 安全异常 | 后端回归通过，Task07 UI 未端到端验 | 服务端安全下载/导入测试包含在全量回归；前端不接受任意 URL，动态论文字段采用安全 DOM API。 |
| A14 排序质量 | 未执行 | 本轮未运行冻结标注集/nDCG 评估；多会议全局去重/排序边界仍需先修复。 |
| A15 回归交付 | **不通过** | 自动化测试和语法均通过，但未完成实际启动、健康检查、GUI、窄屏与完整检索导入链路；开关/A3/去重/aria-current 仍有缺口。 |

## 三、静态可访问性与安全检查

- 论文结果 checkbox 使用 `aria-label="选择论文：标题"`；会议搜索结果使用 `role="option"`、`aria-selected`、`tabIndex=0`，并为 Enter/Space 提供选择行为，上一轮 T7-4 的核心缺口已修复。
- `renderPaperResults()` 与 `renderPaperBatch()` 不含 `innerHTML`；论文标题、作者元数据、摘要、批次标题、错误和状态使用 `textContent`。导入、登录、续传 URL 均由固定路径加 `encodeURIComponent` 的服务端 opaque ID 构造，不读取候选 `pdf_url`、Cookie 或凭证。
- 论文结果、批次、登录队列、会议管理和长文本样式具备 `overflow-y: auto`/`overflow-wrap: anywhere` 与 focus-visible 规则，存在 760px/430px 媒体断点；这些仅为静态证据，不替代桌面/窄屏视觉验收。
- 导航 `aria-current` 仍固定为 `false`，`showView()` 未在切换时更新；功能开关也没有在首屏决定入口，故可访问性和开关项不能判定通过。

## 四、签字

- 测试（tester）：**自动化回归通过；Task07 整体验收不通过（P1/P2 与环境阻塞）**。
- Tech Lead 签字：待签字。
- 签字时间：2026-09-05。
