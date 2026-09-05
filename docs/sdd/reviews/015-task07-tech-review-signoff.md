# Spec015 Task07 修复后最终技术复核与签字

- 评审角色：独立开发主管（Tech Lead）
- 评审者：当前协作 Agent
- 评审时间：2026-09-05 00:49–00:53（Asia/Shanghai）
- 复核范围：Spec015、Task07 计划与最新修复记录；`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`、`backend/app/api/routes.py`、论文相关测试，以及 Task02/Task06 阻塞证据
- 评审约束：只读复核；未修改业务代码、测试或配置；未执行 commit、push、reset、stash、clean
- 进展日志：`.codebuddy/agent-logs/tech-lead-spec015-task07-signoff-20260905-004949.md`

## 最终结论

**阻塞，不签署 Task07 技术放行。**

本轮修复已闭合健康接口开关字段、受控会议搜索 GET、DOI/DBLP key/规范标题身份判断、批次容器隔离、结果选择控件可访问名称、会议结果键盘语义和论文动态文本 XSS 边界；定向及全量自动化回归均通过。

仍有两项代码契约未闭合，且有两项外部验收阻塞，故不能把 Task07 标记为通过：

1. 功能开关的服务端字段已存在，但首屏与在途请求的关闭语义仍不严格满足“入口和请求均不出现”。`frontend/app.js:351-358` 在健康响应到达前把开关缺省为 `true`，`frontend/index.html:19` 的入口也未初始隐藏；健康请求异步返回 `false` 前存在入口闪现/点击竞态。`setPaperEnabled(false)` 会 abort 搜索并停止定时器（`frontend/app.js:411-426`），但批次轮询的已发出请求在 `frontend/app.js:801-806` 返回后没有再次检查 `paperState.enabled`，仍会写入状态并渲染。健康 API 的布尔值回归通过，不等于首屏关闭闭环已通过。

2. 跨会议比较器仍不满足 Spec015 要求的完整稳定 tie-break。`frontend/app.js:595-633` 先比较 `rank`，再比较 `initial_rank`；而规范要求在最终分数相同后按 `initial_rank asc → year desc → normalized_title asc → candidate_id asc`。独立 Node 复核构造 `a={rank:1,initial_rank:5}`、`b={rank:2,initial_rank:0}`（其余分数相同）得到顺序 `a,b`，按规范应为 `b,a`。当前还按 `rerank_score/retrieval_score` 逐级补比，无法证明严格采用服务端单一排名快照。

## 复核矩阵

| 项目 | 结论 | 证据与边界 |
|---|---|---|
| Health flag | 部分通过 | `backend/app/api/routes.py:253-264` 返回布尔 `paper_discovery_enabled`；`tests/test_paper_discovery_api.py` 覆盖默认 true 与显式 false。前端首屏异步默认 true，且在途批次响应缺少二次开关守卫，因此端到端关闭语义阻塞。 |
| 开关停止行为 | 部分通过/阻塞 | `setPaperEnabled(false)` 增加搜索序号、abort 搜索、清理轮询并清空在途导入；`schedulePaperBatchPoll()` 的 fetch 完成分支仍无 enabled/serial 检查。 |
| 会议 GET | 通过（收窄契约） | 前端 `frontend/app.js:948-974` 调用 `GET /api/papers/conferences/search?q=`；后端 `routes.py:269-299` 只匹配服务端已配置安全来源，不访问外部 URL。未注册 `POST /api/papers/conferences`，与 Task02 自定义会议阻塞一致。 |
| DOI/DBLP/title 去重 | 通过（当前收窄身份规则） | `frontend/app.js:536-565` 优先规范化 DOI、DBLP key；无强身份时回退规范化标题+年份+会议，不合并不同 DOI 的同标题候选。跨响应胜出记录保留自身 `search_id`（`app.js:707-723`）。 |
| 完整稳定排序 | 不通过 | 去重修复补齐多层键，但 `rank` 先于 `initial_rank`，与 Spec015 tuple 不一致；独立 Node 合成回归已复现。 |
| 批次隔离/等待登录 | 通过（静态+定向回归） | `renderPaperBatch()` 以 `data-batch-id` 建立独立容器并只替换自身；waiting-login、重试和登录/续传动作按批次/条目隔离。真实浏览器续传仍受 Task06 环境门禁限制。 |
| ARIA/键盘 | 通过（静态） | 结果 checkbox 有标题 `aria-label`；会议结果有 `role=option`、`aria-selected`、tabIndex 与 Enter/Space；`showView()` 同步所有导航项 `aria-current`。未执行真实读屏器。 |
| XSS/opaque ID | 通过（静态+契约） | 论文区域无 `innerHTML`；标题、作者、摘要、状态和错误使用 DOM API/`textContent`；导入、login/resume 只提交服务端 opaque ID。 |

## 自动化验证

| 检查 | 结果 |
|---|---|
| `node --check frontend/app.js` | 通过，退出码 0 |
| `.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py tests/test_paper_discovery_api.py tests/test_paper_discovery_search.py tests/test_paper_import_batch_api.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_store.py tests/test_paper_import.py tests/test_paper_import_identity.py tests/test_paper_download.py tests/test_paper_download_security.py` | 通过，102 passed、9 subtests（2.02s） |
| `.venv/bin/python -m compileall -q backend/app` | 通过，退出码 0 |
| `git diff --check` | 通过，退出码 0 |
| `.venv/bin/python -m pytest -q` | 通过，511 passed、5 warnings、38 subtests（124.40s） |
| Node 合成身份/排序复核 | DOI 相同 true、DBLP key 相同 true、规范标题+年份+会议相同 true、不同 DOI 同标题 false；排序反例 `a,b` 与规范期望 `b,a` 不一致 |

## 外部验收阻塞（如实保留）

### A3 自定义会议

A3 不伪造通过。`docs/sdd/reviews/015-task02-baseline-review.md` 记录 DBLP Venue Search 多次只得到 `429/503`，没有成功样本；Task02 技术结论仅条件放行内置会议，不放行 live Venue Search。当前实现没有自定义会议 `POST`/新增闭环，会议 GET 只搜索已有服务端配置。因此 A3 继续标记为 Task02 前置环境/数据源阻塞，而非已验收功能。

### 真实 GUI 与 ACM/IEEE

未执行桌面/窄屏 GUI、真实读屏器及 ACM Digital Library/IEEE Xplore 合法账号登录续传。既有 Task06 最终安全复核记录当前 `.venv` 未安装 Playwright，且无可核验合法账号；Task07 QA 还记录 GUI 环境不可用。A1/A2/A7–A11 的真实交互和认证站点验收不能用静态检查或离线 fake 测试替代。

## 放行前条件

1. 为首屏提供同步/注入的论文开关状态，或默认隐藏入口直到 health flag 成功解析；关闭时对所有在途批次响应增加 enabled/序列守卫，确保不再渲染或继续业务请求。
2. 将前端合并结果排序调整为规范 tuple（最终分数后先 `initial_rank`，再年份、规范标题、candidate ID），并补充前端跨响应 tie-break 回归；若坚持服务端排名，应改为消费单一多会议 snapshot。
3. DBLP Venue Search 获得可复现成功样本后，再实现/验收 A3 自定义会议搜索、新增、保存、修改、停用及内置删除保护。
4. 在可用 Playwright、解锁 GUI 和合法账户环境中完成真实桌面/窄屏及 ACM/IEEE 登录续传验收。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：阻塞**
- 签字时间：2026-09-05 00:53 +0800
