# Spec015 Task07 修复后最终验收与 QA 签字

- 执行角色：测试（QA）
- 关联 spec：`docs/sdd/specs/015-security-paper-discovery.md`
- 关联计划：`docs/sdd/plans/015/task-07-paper-discovery-tab.md`
- 验收时间：2026-09-05 00:48（Asia/Shanghai）
- 复核范围：Task07 最新健康开关、会议搜索、跨响应去重/排序修复，以及论文 Tab 的批次、ARIA、XSS 和论文 API/导入回归
- 进展日志：`.codebuddy/agent-logs/tester-spec015-task07-signoff-20260905-0048.md`
- 改动约束：未修改业务代码、测试、配置或 Git 状态；仅新增本报告与进展日志；未执行 commit、push、reset、stash、clean

## 一、结论

**Task07 最终验收不通过，暂不建议放行。**

本轮已确认健康接口字段、受控会议搜索 GET、跨会议 DOI/DBLP 去重、批次独立渲染、导航 `aria-current`、opaque ID 导入边界和论文动态文本安全渲染均已落地；前端语法、前端契约、论文定向回归和全量 pytest 均通过。

仍有以下验收阻塞：

1. **功能开关存在在途批次响应竞态（P2）。** `setPaperEnabled(false)` 会中止搜索、停止定时器并清理待发导入，但 `schedulePaperBatchPoll()` 的已发出请求在 `await fetch()` 返回后直接写入状态并调用 `renderPaperBatch()`，没有再次检查 `paperState.enabled`（`frontend/app.js:801-806`）。关闭开关后仍可能渲染一笔已在途响应；严格“关闭时不再产生论文 UI/业务效果”尚未闭合。首屏入口还依赖异步 `/api/health` 回填，未注入值时 `readPaperFeatureFlag()` 默认开启，真实首屏不闪现无法在无浏览器环境中证明。
2. **稳定排序 tie-break 顺序仍与 Spec015 不完全一致（P2）。** `comparePaperCandidateRecords()` 在同分时先比较 `rank`，再比较 `initial_rank`（`frontend/app.js:595-603`）；规范要求同分使用 `initial_rank asc → year desc → normalized_title asc → candidate_id asc`。Node 复核样本中 `rank=1, initial_rank=2` 的候选仍排在 `rank=2, initial_rank=1` 候选之前，未满足冻结的 tie-break 顺序。当前回退身份键还包含会议身份，跨会议同标题/年份且缺少 DOI/DBLP key 时不会合并，需由实现方明确是否符合身份契约。
3. **A3 自定义会议仍受前置条件阻塞。** 当前仅提供搜索服务端既有会议的 `GET /api/papers/conferences/search?q=`；`POST /api/papers/conferences` 不存在（实测 405），且 DBLP Venue Search 成功样本仍受 Task02 外部依赖阻塞。因此不能宣称搜索、新增、别名编辑及自定义会议完整闭环通过。
4. **真实 GUI、窄屏和 ACM/IEEE 登录续传未执行。** 本地服务未运行（`curl http://127.0.0.1:8000/api/health` 连接失败），无法进行像素布局、实际 Tab 切换、批次交互和窄屏验收；`.venv` 未安装 Playwright，也没有可核验的 ACM/IEEE 合法账号/SSO 样本。

## 二、执行证据

| 检查 | 命令/事实 | 结果 |
|---|---|---|
| JavaScript 语法 | `node --check frontend/app.js` | 通过，退出码 0 |
| 前端契约 | `.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py` | 通过，3 passed |
| 论文检索/导入定向回归 | `tests/test_paper_discovery_api.py tests/test_paper_import_batch_api.py tests/test_paper_discovery_search.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_store.py tests/test_paper_import.py tests/test_paper_import_identity.py tests/test_paper_download.py tests/test_paper_download_security.py` | 通过，99 passed、9 subtests |
| 全量回归 | `.venv/bin/python -m pytest -q` | 通过，511 passed、38 subtests、5 warnings，退出码 0 |
| Python/差异 | 目标后端可编译；`git diff --check` 覆盖 Task07 文件 | 通过 |
| 健康开关 | `PAPER_DISCOVERY_ENABLED=false` 下 TestClient `GET /api/health` | 200，`paper_discovery_enabled: false` |
| 会议搜索 | TestClient `GET /api/papers/conferences/search?q=ccs`；OpenAPI | 200；GET 已注册，返回服务端配置安全字段 |
| 自定义会议边界 | TestClient `POST /api/papers/conferences` | 405；按当前收窄范围不提供新增 |
| 去重/排序算法 | Node 提取真实函数并用 DOI、DBLP、标题元数据及同分样本复核 | DOI/DBLP/元数据去重样本通过；同分 `rank` 优先于 `initial_rank` 的规范顺序缺陷复现 |
| 运行服务 | `curl -sS http://127.0.0.1:8000/api/health` | 连接失败，未启动服务 |
| Playwright | `.venv/bin/python -c 'import importlib.util; ...'` | `None`，未安装 |

## 三、修复后验收矩阵

| 检查项 | 状态 | 证据与边界 |
|---|---|---|
| Health flag | 通过（接口） | 后端健康响应复用 `_paper_discovery_enabled()` 并返回布尔字段；关闭状态测试通过。 |
| 功能开关 | **部分通过/不放行** | 关闭会 abort 搜索、停止轮询和隐藏入口；但在途批次响应没有 enabled 二次守卫，首屏真实隐藏/无闪现未做 GUI 验证。 |
| 会议搜索 | 通过（受限契约） | 前端消费受控 GET；服务端只匹配已有配置的名称、简称和 ID，不访问外部 Venue Search。A3 新增会议仍阻塞。 |
| 跨响应去重 | 通过（静态与算法样本） | DOI、DBLP key 规范化优先，双方无强身份时回退标题/年份/会议元数据；不同 DOI 不误合并。跨会议无 DOI/DBLP 的同标题身份语义仍需明确。 |
| 稳定排序 | **部分通过/不放行** | 分数、年份、标题、身份和 candidate ID 均有确定比较；但同分时 `rank` 先于 `initial_rank`，违反 Spec015 明确顺序。 |
| 批次隔离/等待登录 | 通过（静态与定向回归） | `data-batch-id` 建立独立容器；批次状态、失败重试和 waiting-login 操作不再清空其他批次。真实浏览器动作未验。 |
| ARIA/键盘 | 通过（静态） | 导航切换同步 `aria-current`；结果 checkbox 有标题 accessible name；会议结果有 `role=option`、`aria-selected`、Enter/Space。未用真实读屏器。 |
| XSS/动态文本 | 通过（静态与契约） | 论文结果/批次渲染区不使用 `innerHTML`；标题、作者、摘要、错误和状态使用 `textContent`；导入仅提交服务端 opaque ID。 |

## 四、产品验收场景与环境限制

| 场景 | 结论 |
|---|---|
| A1 独立入口/关闭 | 接口和静态逻辑基本通过；首屏无闪现及关闭竞态未放行 |
| A2 默认四大会议与最近五个完整年份 | 初始化逻辑/接口定向测试通过；未做真实 GUI 首屏验收 |
| A3 自定义会议 | 阻塞：DBLP Venue Search 无可复现成功样本，新增 API 不存在 |
| A4–A6 检索、过滤、降级 | 论文 API/搜索定向回归通过；真实外部源链路未执行 |
| A7–A9 单篇、批量、登录等待、幂等 | 离线 API/服务/静态逻辑通过；真实 UI 未执行 |
| A10 ACM 登录 | 未执行：Playwright 未安装且无合法账号样本 |
| A11 IEEE 登录 | 未执行：同 A10 |
| A12 命名兼容 | 定向身份/导入/下载测试通过 |
| A13 安全异常 | 定向 URL、SSRF、伪 PDF、超限和错误脱敏测试通过 |
| A14 排序质量 | 未执行：Task08 冻结的查询及人工标注集/nDCG 尚未提供 |
| A15 回归交付 | 自动化回归通过；因开关竞态、排序契约、A3 和 GUI/真实登录阻塞，整体验收不通过 |

## 五、放行前条件

1. 在每个批次轮询响应写入/渲染前增加 enabled 或 serial/epoch 二次守卫，并补关闭开关在途响应回归；如要求首屏绝不闪现，提供页面启动时的服务端能力注入或等效机制。
2. 按规范固定同分排序为 `initial_rank asc → year desc → normalized_title asc → candidate_id asc`，并补跨会议 DOI、DBLP key、规范标题及同分 tie-break 测试。
3. DBLP Venue Search 恢复后补验 A3；在此之前继续明确自定义会议为阻塞，不将受控配置搜索误称为新增会议能力。
4. 服务启动后执行真实桌面/窄屏验收；具备合法 ACM/IEEE 账号和 Playwright 后再执行 A10/A11。

## 六、签字

- 测试（QA）：**已完成本轮验收；结论为不通过/部分阻塞**
- 开发主管（Tech Lead）：**待签字**
