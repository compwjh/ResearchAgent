# Spec015 Task07 最后一轮 JavaScript 修复 QA Post-fix Signoff

- 评审者：测试（QA）
- 角色：tester 子代理
- 模型：当前执行 Agent（运行时模型标识未暴露）
- 分派方式：由主会话分派的只读 QA post-fix 复核
- 关联 spec：`docs/sdd/specs/015-security-paper-discovery.md`
- 关联任务：`docs/sdd/plans/015/task-07-paper-discovery-tab.md`
- 验收时间：2026-09-05 01:00（Asia/Shanghai）
- 进展日志：`.codebuddy/agent-logs/tester-spec015-task07-postfix-signoff-20260905-0100.md`
- 改动约束：未修改业务代码、测试、配置或 Git 历史；未执行 commit、push、reset、stash、clean

## 一、结论

**JavaScript 最后一轮修复：通过。Task07 整体验收：阻塞，不放行。**

本轮确认此前提出的两个 JS P2 已闭合：

1. 批次轮询响应在关闭功能开关后因 epoch/serial 失效，不再写入 `paperState.batches`、渲染批次或更新错误提示（`frontend/app.js:784-809`；Node 行为断言通过）。
2. 同分排序严格使用 `initial_rank asc → year desc → normalized_title asc → candidate_id asc`；旧 `rank` 不再参与 tie-break（`frontend/app.js:590-627`；Node 行为断言通过）。

去重、ARIA 和 XSS 静态/行为检查也通过。整体验收仍不能签署通过，原因是 GUI/窄屏、A3 自定义会议、真实 ACM/IEEE 合法登录续传及 A14 冻结排序质量集未具备可执行环境或证据；Tech Lead 签字仍待补。

## 二、执行证据

| 检查 | 命令 / 方法 | 结果 |
|---|---|---|
| JS 语法 | `node --check frontend/app.js` | 通过，退出码 0 |
| 前端契约 + 论文相关回归（默认环境） | `.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py tests/test_paper_*.py` | **120 passed、2 failed、9 subtests**；2 项为浏览器 fake 下载测试 DNS 解析失败 |
| DNS 隔离复跑 | 注入 `paper_download_security._default_resolver → 93.184.216.34` 后复跑同一组 | **122 passed、9 subtests**，退出码 0 |
| DNS 失败项单独复跑 | 同 resolver 注入，两个 `test_authenticated_pdf_request_*` | **2 passed** |
| 在途响应竞态 | Node mock fetch：请求挂起后关闭开关并递增 serial，再释放响应 | 通过；旧响应不改状态、不渲染 |
| tie-break | Node 提取真实 comparator，覆盖 initial rank、年份、规范标题、candidate ID | 通过；`rank` 不抢先 |
| 去重 | Node 覆盖 DOI URL/前缀规范化、DBLP key、标题/年份/会议回退、不同 DOI 隔离 | 通过；与后端强身份语义一致 |
| ARIA/XSS | Node 静态断言 + `test_frontend_paper_contract.py` | 通过；论文 renderer 无 `innerHTML`，动态字段使用 `textContent`；ARIA role/state/label 存在 |
| 差异检查 | `git diff --check -- frontend/app.js frontend/index.html frontend/styles.css` | 通过，退出码 0 |

默认环境的 2 项失败是测试 fake 请求尚未执行到 fake 403/PDF 响应，而是在安全层解析 `dl.acm.org` 或 `ieeexplore.ieee.org` 时被当前沙箱 DNS 映射为 `DOWNLOAD_BLOCKED`。注入 resolver 后同一实现和同一测试通过；该环境 workaround 不代表真实外网或真实登录已验收。

## 三、关键修复复核

### 1. 功能开关与在途响应

`setPaperEnabled(false)` 会递增 `searchSerial` 与 `batchPollSerial`、abort 搜索、清理轮询定时器并隐藏论文视图（`frontend/app.js:412-428`）。每个轮询闭包捕获 `pollSerial`，在 fetch 前、fetch 返回后和异常提示前均检查 `paperState.enabled && pollSerial === paperState.batchPollSerial`（`frontend/app.js:784-809`）。Node mock 已证明：关闭后释放原请求响应，不会写入 map 或调用 renderer。

### 2. 稳定排序

`PAPER_CANDIDATE_TIE_BREAK_ORDER` 与 comparator 均明确列出四级顺序（`frontend/app.js:590-627`）。Node 样本覆盖同分但 `rank` 与 `initial_rank` 冲突、年份、规范化标题和 candidate ID，结果符合 Spec015；DOI/DBLP 只用于身份，不影响展示顺序。

### 3. 去重与身份边界

`paperCandidateIdentityMatches` 先比较规范 DOI，再比较 DBLP key，最后回退规范标题 + 年份 + 会议（`frontend/app.js:522-568`）。Node 断言确认 DOI 常见 URL/前缀共享身份、DBLP 大小写规范化共享身份、标题标点差异可回退合并，不同 DOI 不误合并。标题回退包含会议，符合后端 `paper_import_identity.py` 的会议作用域；跨会议且没有 DOI/DBLP 的同标题记录不会被强行合并。

### 4. ARIA / XSS

论文结果 renderer（`frontend/app.js:630-661`）与批次 renderer（`frontend/app.js:812-887`）没有 `innerHTML`；标题、作者/元数据、摘要、状态和错误均进入 `textContent`。结果 checkbox 带标题 accessible name；会议搜索结果使用 `role=option`、`aria-selected` 与 Enter/Space 键盘操作（`frontend/app.js:949-975`）；Tab 导航切换同步 `aria-current`（`frontend/app.js:1008-1018`）。论文导入继续只消费服务端 `search_id/candidate_id(s)`，未从候选数据拼接下载 URL。

## 四、仍然阻塞的验收项与环境限制

| 项目 | 结论 | 事实与影响 |
|---|---|---|
| GUI / 窄屏 | 未执行，阻塞 | 本轮仅做静态与自动化验证；无法在真实桌面浏览器检查 Tab 切换、首屏隐藏、长标题/批量卡片、窄屏按钮可见性和键盘焦点呈现。 |
| A3 自定义会议 | 阻塞 | 当前有 `GET /api/papers/conferences/search`，仅搜索服务端已有配置；没有注册 `POST /api/papers/conferences` 新增闭环。DBLP Venue Search 的成功外部样本仍未恢复，不能宣称搜索新增、别名编辑、停用完整通过。 |
| A10 ACM 登录 | 未执行，阻塞 | `.venv` 中 `playwright` 不可导入，且没有可核验的合法 ACM 账户/SSO 样本；fake Playwright 只覆盖安全 seam，不代表真实登录续传。 |
| A11 IEEE 登录 | 未执行，阻塞 | 同上；无合法账号和真实 headed 浏览器链路证据。 |
| A14 排序质量 | 未执行，阻塞 | 本轮没有冻结的至少 12 条查询人工标注集及 nDCG@10 结果，不能将 tie-break 通过扩大为质量验收通过。 |
| A15 回归交付 | 阻塞 | 论文相关自动化在 resolver 隔离后通过，但完整产品验收仍缺 GUI、窄屏、A3、真实 ACM/IEEE 和 A14 证据；本轮未启动服务，未声称运行时通过。 |

## 五、验收矩阵（本轮后）

| 验收点 | 本轮结论 |
|---|---|
| A1 入口/开关 | JS 竞态修复通过；真实 GUI 首屏和关闭入口未验 |
| A2 默认范围 | 自动化/静态可见；GUI 未验 |
| A3 自定义会议 | 阻塞，当前实现仅已有会议搜索 |
| A4–A6 检索/过滤/降级 | 论文相关定向自动化通过；真实外部源未验 |
| A7–A9 单篇/批量/幂等 | 论文相关自动化与静态批次逻辑通过；真实 UI 未验 |
| A10 ACM 登录 | 阻塞，环境/账号不可用 |
| A11 IEEE 登录 | 阻塞，环境/账号不可用 |
| A12 命名兼容 | 论文身份/导入定向回归通过 |
| A13 安全异常 | 论文安全定向回归通过；默认 DNS 两项需 resolver workaround 才可执行 |
| A14 排序质量 | 未执行，标注集/nDCG 缺失 |
| A15 回归交付 | 阻塞，缺真实 GUI/登录/服务运行证据 |

## 六、签字

- 测试（QA）：**已完成本轮 post-fix 复核；JS 修复通过，Task07 整体验收阻塞**
- 开发主管（Tech Lead）：**待签字**
