# Spec015 Task07 最后一轮 JavaScript 修复后 Tech Lead 签核

- 评审角色：开发主管（Tech Lead）
- 评审者：当前协作 Agent
- 评审时间：2026-09-05 00:59–01:03（Asia/Shanghai）
- 关联 spec：`docs/sdd/specs/015-security-paper-discovery.md`
- 复核范围：最新 `015-task07-last-js-fix.md`、health flag 修复、`frontend/app.js`、`frontend/index.html`、`backend/app/api/routes.py`、Task07 QA/既有技术复核，以及论文相关自动化测试
- 评审约束：只读复核；未修改业务代码、测试或配置；未执行 commit、push、reset、stash、clean
- 进展日志：`.codebuddy/agent-logs/tech-lead-spec015-task07-postfix-signoff-20260905-0059.md`

## 一、结论

**阻塞（本轮两项 JS 修复通过；Task07 整体暂不放行）。**

本轮确认 QA 指出的两项代码缺口已经闭合：

1. 批次轮询的在途响应现在受 `paperState.enabled + pollSerial` 保护。功能开关关闭会递增序列并清理定时器；请求返回后在写入 `paperState.batches`、调用 `renderPaperBatch()` 或更新错误提示前再次检查守卫，因此旧响应不会在关闭后产生业务状态或论文 UI 效果。
2. 跨会议结果的同分 tie-break 现在按 `initial_rank asc → year desc → normalized_title asc → candidate_id asc` 执行；局部 `rank` 和 DOI/DBLP 身份键不再参与展示排序，身份键仍仅用于去重。

上述修复不能解除以下整体门禁：健康接口字段已闭合，但首屏导航仍在 health 异步响应前默认显示，`readPaperFeatureFlag()` 未获得注入值时默认 `true`；因此严格的“关闭开关后入口和请求均不出现、无首屏闪现”仍没有端到端闭环。A3 自定义会议以及真实 GUI/认证站点验收也继续保持真实阻塞，不能以离线测试替代。

## 二、修复项复核矩阵

| 项目 | 结论 | 证据 |
|---|---|---|
| Health flag 接口 | 通过（接口层） | `backend/app/api/routes.py:253-264` 返回布尔 `paper_discovery_enabled`；`tests/test_paper_discovery_api.py` 覆盖默认开启与 `PAPER_DISCOVERY_ENABLED=false`，并限制响应键不泄露内部配置。 |
| 在途批次响应 guard | 通过（代码/静态行为复核） | `frontend/app.js:784-807` 捕获 `pollSerial`，在请求前、`paperJson()` 返回后和异常更新前使用 `isCurrentPoll()`；`setPaperEnabled(false)` 在 `frontend/app.js:412-428` 递增序列、终止轮询并清理在途导入。 |
| 同分 tie-break | 通过（代码/Node contract） | `frontend/app.js:590-627` 先处理分数层级，随后严格使用 `initial_rank`、年份、规范化标题、`candidate_id`；`PAPER_CANDIDATE_TIE_BREAK_ORDER` 明确记录相同顺序。 |
| DOI/DBLP/标题身份 | 通过（本轮未回归破坏） | `frontend/app.js:538-568` 保留 DOI、DBLP key 和标题/年份/会议身份匹配；比较器不使用这些身份键改变展示顺序。 |
| 首屏关闭语义 | **阻塞** | `frontend/app.js:351-362` 无注入值时返回 `true`；`frontend/index.html:19` 论文导航初始未隐藏；health 请求在 `frontend/app.js:96-113` 异步完成后才回填服务端值。接口字段通过不等于首屏无闪现。 |

## 三、自动化验证

| 检查 | 结果 |
|---|---|
| `node --check frontend/app.js` | 通过，退出码 0 |
| Node 静态 guard/tie-break contract（读取真实 `frontend/app.js`） | 通过；确认 `pollSerial`/`isCurrentPoll`、响应后二次守卫、错误分支守卫及四项 tie-break 顺序存在 |
| `.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py tests/test_paper_discovery_api.py tests/test_paper_discovery_search.py tests/test_paper_import_batch_api.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_store.py tests/test_paper_import.py tests/test_paper_import_identity.py tests/test_paper_download.py tests/test_paper_download_security.py` | 通过，102 passed、9 subtests，1.57s |
| `.venv/bin/python -m compileall -q backend/app` | 通过，退出码 0 |
| `git diff --check` | 通过，退出码 0 |
| `.venv/bin/python -m pytest -q` | 通过，511 passed、5 warnings、38 subtests，71.82s |

## 四、仍然有效的外部与范围阻塞

### A3：DBLP Venue Search / custom conference

不宣称通过。既有 Task02 baseline 记录 DBLP Venue Search live 请求仅获得 `429`/`503`，没有可复现成功样本；当前路由只有 `GET /api/papers/conferences/search`、会议列表、`PATCH` 和 `DELETE`，没有 `POST /api/papers/conferences` 新增闭环。当前 GET 只搜索服务端已配置会议，属于明确收窄后的安全边界，不等同于“搜索并新增自定义会议”。在获得成功 live 样本及用户确认前，A3 继续阻塞。

### 真实 GUI、窄屏与 ACM/IEEE 登录续传

不宣称通过。既有 Task06/Task07 证据显示当前 `.venv` 未安装 Playwright，也没有可核验的 ACM/IEEE 合法账号/SSO 权限样本；真实桌面/窄屏布局、实际 Tab 操作、headed 登录、认证 PDF 下载和续传均未执行。离线 API、静态 DOM 和 fake browser 测试不能替代 A1/A2/A7–A11 的真实验收。

### A14 排序质量

本轮只复核实现级稳定 tie-break，不代替 Task08 冻结查询/人工标注集的 nDCG 验收；未提供标注集前不作 A14 通过声明。

## 五、放行条件

1. 补齐首屏功能开关注入，或在 health flag 成功解析前默认隐藏论文入口，并保留本轮在途响应 guard。
2. DBLP Venue Search 恢复后取得成功 live 样本，再实现/验收自定义会议搜索、新增、保存、修改、停用与内置删除保护。
3. 在安装并固定 Playwright、解锁 GUI、提供合法 ACM/IEEE 权限样本后，完成真实桌面/窄屏及 A10/A11 登录续传验收。
4. 按 Task08 计划提供冻结排序质量数据集并完成 A14 nDCG 复测。

## 六、签字

- 开发主管（Tech Lead）：**本轮 JS 修复项通过；Task07 整体签字：阻塞**
- 签字时间：2026-09-05 01:03 +0800
