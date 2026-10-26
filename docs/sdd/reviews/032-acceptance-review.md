# Spec032 验收评审

> 当前补充收口：原整体验收的 BLOCKED 历史结论保留；2026-10-26“持久快照优先、解除 search TTL 路由阻断”窄修后续栏已由 tester 标记 `READY_FOR_USER`、architect 签字 `GO`。认证后 resume、下载/入库未验证，Spec032 整体仍暂停。

## 评审元数据

- 评审者：Spec032 Task14 review-regression 子 Agent
- 角色：跨端回归与验收复核（临时 Luna high）
- 模型：Luna high
- 分派方式：主 Agent 直接分派
- 签字：**留空，等待独立 tech-lead / tester 复评**

## 结论

**不通过 / BLOCKED。** 后续追记已经补齐 18080 服务、四会议 2024 目录 smoke、Worker 重启缓存和候选自动导入的离线集成证据；但 DBLP 外部响应仍降级，真实登录/上传恢复、跨年度覆盖、独立签字和 Spec 收口全量回归仍未完成。不能标记 Spec032 `已完成`。

## 验收矩阵

| 验收项 | 结果 | 证据/阻塞 |
|---|---|---|
| 七来源统一 schema / Tool | PASS（离线） | Task06/09 artifacts；统一 `worker-tool-v1` 测试通过 |
| 目录、缓存、provenance、权威合并 | PASS（固定样本/离线） | Task06–08 artifacts；未替代真实年度证明 |
| 四会议逐年官网覆盖 | BLOCKED | 四会议 2024 已有真实完成证据；更多年度未验证，DBLP 2024 当前为 `DBLP_INVALID_RESPONSE/degraded=true` |
| Research Planner→多来源 Worker | PASS（离线+2024 smoke）/真实待验 | 统一 Worker/Registry/Store 已接线，四会议 2024 目录 smoke 已完成；跨年度仍待验 |
| 批准计划自动导入/身份门禁 | PASS（离线）/真实未验 | Task14 新增候选评估→批准→自动导入集成回归；真实 PDF/登录未执行 |
| issue 登录/上传/重试/旧报告不可变 | PASS（离线）/真实未验 | 任务级 issue 投影已接线；真实登录/上传恢复未执行 |
| 前端来源卡/待处理论文/XSS 契约 | PASS（静态） | 相关 frontend tests、Node syntax 通过 |
| 服务重启恢复 | PASS（SQLite/fake）/真实未验 | Task08/10/11 离线证据；无运行服务 |
| 部署与端口访问 | PARTIAL | 2026-09-22 `PORT=18080` 的 `/api/health` 为 HTTP 200；当前服务未保持运行，需收口前重新部署并复验 |

## 回归数字

完整相关测试命令：

```text
.venv/bin/python -m pytest -q tests/test_spec032*.py tests/test_paper_discovery*.py tests/test_research*.py tests/test_skill*.py tests/test_frontend*.py tests/test_spec029_frontend_acquisition_progress.py tests/test_spec030_frontend.py tests/test_spec031_frontend.py
```

历史基线结果：`751 passed, 15 subtests passed, 5 warnings, exit 0`。后续 Spec032 相关集合已达到 `1513 passed, 38 subtests, 5 warnings, exit 0`；Ruff、compileall、diff-check、Node syntax 均通过。

## 必须复验

- 在可访问外部来源的部署环境复验 DBLP，并补齐四会议未验证年度；失败时继续保留明确的 NO-GO，不伪造候选。
- 启动当前代码版本，完成受控检索→评估→批准导入→issue 登录/上传修复→新报告版本及重启恢复 smoke。
- 由独立验收角色填写签字栏；主 Agent 只在签字、部署 URL、实际端口、启动命令和唯一全量回归结果齐全后更新 Spec 状态。

## Task08 follow-up 复评追记（2026-09-20）

Planner→Research Worker 的多来源接线已补齐并完成离线验证：新来源走统一
`paper_discovery` Worker，冻结结果仍使用现有 SQLite/目录契约；23 项 Task08/09/Spec034
合同测试和 215 项相关回归通过。原“Research Planner→多来源 Worker”失败项已改为
“离线 PASS，待真实 smoke”。服务启动、外部来源、登录/导入、重启恢复和部署仍待本 Task
完成后复验，当前验收结论继续保持 BLOCKED。

## Authority 与产品步骤 follow-up（2026-09-20）

- Spec032 产品使用步骤已补齐，并与 Task12/Task14 的来源选择、进度、导入、失败恢复和版本验收点对应。
- 官方目录 route 已使用独立 provenance 标识和 rank=10；Crossref DOI rank=20；聚合来源 rank=30。相关 runtime/authority 定向测试 `187 passed`。
- Task06–13 合同复跑 `49 passed`，审计范围 Ruff 已通过。
- 该 follow-up 只关闭文档和字段权威实现缺口；官方年度覆盖、真实候选导入/人工修复、业务批次重启及独立签字仍阻塞 Gate 5，Spec032 继续保持 `BLOCKED`。

## Task14 运行时追记（2026-09-22）

- 18080 服务重启后 `/api/health` 返回 HTTP 200；USENIX 2024 目录同步 227 篇、NDSS 2024 官方目录同步 142 篇均以 `completed/degraded=false` 结束。
- USENIX 2024 缓存检索冻结 227 个候选，结果页第一页 10 篇可读；索引/RAG 降级被如实投影为 `partial/degraded=true`，没有阻止目录候选读取。
- Semantic Scholar 429 退避、SQLite 重启缓存和相关代码集合回归均通过；当前集合为 `1506 passed, 38 subtests`。
- 评审仍保持 **BLOCKED**：IEEE S&P/CCS 及未验证年度、候选评估到真实导入/人工修复、业务批次重启和独立签字仍未形成完整证据。
- 追加批次恢复证据：重启后批次 `83846ea1-0178-421a-bc8b-2ea5d8b7a0de` HTTP 200，`partial_success`（3 completed、3 failed），失败项保留 `KB_IMPORT_FAILED/cleanup_pending`；这只证明导入快照可恢复读取，尚未替代 Research Task 绑定的人工 issue 修复验收。
- DBLP 2024 受控同步明确返回 `DBLP_INVALID_RESPONSE/degraded=true`，未伪造候选数据；该来源保留降级/复验状态，不能计入已验证覆盖。
- 任务级失败投影 follow-up：批准计划自动导入的 `failed`/`waiting_login` 项现在在批次状态转换后写入既有 Research issue store，`GET /api/papers/issues?task_id=...&status=open` 可见候选与恢复句柄；相关定向 46 passed、补充回归 14 passed，相关集合累计 `1507 passed, 38 subtests`。代码缺口已关闭，但真实登录/上传恢复、完整跨来源验收和独立签字仍未完成，结论继续保持 **BLOCKED**。
- 来源编排复核 follow-up：`CatalogSourceFactory` 已确认将 `ieee_sp`、`ccs`、`ndss`、`openalex`、`crossref` 接入共享 Worker/Registry/Store 组合，旧 Graph 不承载这些来源，避免第二套检索链；契约与旧 Graph 边界测试 35 passed。该项关闭“是否存在非 legacy 来源重复实现”的疑点，但不等同于四会议各年度真实抓取已验收，结论继续保持 **BLOCKED**。
- 直接异步端点边界 follow-up：`/api/papers/searches` 继续作为旧 USENIX snapshot/分页接口；非 USENIX 请求明确返回 `UNSUPPORTED_CONFERENCE`，不会写任务或提交旧 Graph。Spec032 多来源入口仍是 Research Worker/CatalogSearchAdapter，契约测试 `9 passed`；该项不改变四会议真实覆盖仍未完成的结论。
- 四会议 2024 真实 smoke follow-up：IEEE S&P 单元完成 43 篇、CCS 单元完成 328 篇，连同 USENIX 227、NDSS 142，四会议 2024 均有 `completed/degraded=false` 运行时证据。年度扩展、DBLP 降级、候选评估到实际导入/人工修复、业务重启和独立签字仍待 Task14，验收结论继续保持 **BLOCKED**。
- Worker 重启缓存 follow-up：generic Worker 不再只依赖 adapter 进程内缓存；新进程从已完成的 SQLite source records 复用 IEEE S&P/CCS/NDSS 2024，实际 `discover` 三源均 `completed/cache_hit=true`，无外站重抓。该代码缺口已关闭，但完整导入/人工修复与独立验收仍未完成，结论继续保持 **BLOCKED**。
- 批量续传竞态 follow-up：首次后台 runner 仍为 `queued` 时，浏览器续传现在会有界等待稳定状态后再执行；等待上限调整为 5 秒，避免繁忙进程返回假 200。目标竞态重复 10 次通过，相关集合最终 `1513 passed, 38 subtests, 5 warnings`；这仍是 Task14 前置定向集合，不是 Spec032 收口所要求的唯一全仓回归，结论继续保持 **BLOCKED**。
- DBLP 响应审计 follow-up：2024 辅助同步真实返回 `DBLP_INVALID_RESPONSE/degraded=true`，没有把 HTML/bot-challenge 当作论文数据；新增非 JSON 响应合同测试，DBLP 定向 `9 passed`。由于当前网络/DNS 无法复核外站成功响应，DBLP 仍记录为 NO-GO/待部署环境复验，不阻断官方来源降级返回，但不能计入已验证覆盖。
- 候选导入窄接缝 follow-up：新增离线集成回归覆盖 evaluator 白名单选集、批准计划物化、现有自动导入批次以及 task-scoped issue 投影；固定样本得到一个 `completed` 和一个 `waiting_login/LOGIN_REQUIRED`，组合定向 `26 passed`。该项关闭代码接缝缺口，但不替代真实 PDF 下载、浏览器登录/上传和部署环境人工验收，结论继续保持 **BLOCKED**。

---

## 2026-10-26 已有批次登录恢复窄修验收追记（tester）

本节追加记录当前主目录候选中 Task11 durable-snapshot-first 登录入口窄修的独立验收，不改写上方 Spec032 历史 BLOCKED 结论。验收角色为 `tester`，临时档位 `Luna xhigh`；工作目录为 `/Users/wjh/ResearchAgent`。范围只包括已有 `waiting_login` 条目的登录入口恢复；Spec032 其余来源覆盖、下载/上传、跨年度验证和暂停任务不在本次范围，也不因本窄修改变状态。

### 范围与真实证据

- Spec032 当前状态仍为“暂停，待下次继续”，并明确 2026-10-26 窄修为实施中，见 `docs/sdd/specs/032-research-source-expansion.md:3-7`。接口契约仅要求复用既有 login/resume/retry 入口，见 `:106-119`；产品步骤要求打开登录后完成登录、点击“登录后继续”并查看下载/入库或失败终态，见 `:151-164`。
- 本次目标是 batch `1a76e369-c638-4f2c-a430-42552a1e7012`、item `9eed783f-ff98-4021-99dd-1ab2787688cb`。只读诊断记录 item 为 `waiting_login`/`LOGIN_REQUIRED`，持久 snapshot hash 非空且校验相等，candidate/search 身份一致，ACM URL 来自服务端快照，live search 已过期，见 `docs/sdd/plans/032/2026-10-26-login-recovery-plan.md:13-26`。
- 真实运行时记录为 `/Users/wjh/ResearchAgent:8000`，请求是 `POST /api/papers/import-items/9eed783f-ff98-4021-99dd-1ab2787688cb/login`、空 JSON body，见 `docs/sdd/plans/032/artifacts/20261026-login-recovery/request.md:1-9`。HTTP 200 的最终响应为 `{"status":"opened","item_id":"9eed783f-ff98-4021-99dd-1ab2787688cb","site":"acm"}`，见 `final-login-response.json:1`。
- `200/opened/acm` 只证明已打开受控 ACM 登录页；它不证明用户凭据已认证、`resume` 已成功、PDF 已下载、文档已入库或后续研究任务已完成。计划已明确这一边界，见 `2026-10-26-login-recovery-plan.md:67-83,85-91`。本 tester 未提交凭据、未执行登录或 resume、未打开 headed browser、未发送第二个生产 POST、未写 SQLite/KB/profile、未部署、未运行单端测试或 Git 操作。
- 代码评审与集成定向回归可作为窄修前置证据：候选三文件集合 `64 passed/0 failed/0 skipped` 及集成主目录同样 `64/64`，见 `2026-10-26-login-recovery-test.md:52-59,128-140`；评审确认 durable-first 与损坏快照 fail-closed，见 `2026-10-26-login-recovery-review.md:7-25`。这些离线/定向结果不能替代认证后的真实 resume/download E2E。

### 已完成到哪一步、真实缺口与判定

已完成：过期 search session 下，服务端已校验 durable snapshot 可被 login 路由恢复；指定 item 的真实 HTTP 200 响应为 `opened/acm`。

真实缺口：没有真实用户完成 ACM 登录后的 `POST .../resume` 请求/响应，没有 item 的后续状态终态，没有 PDF 下载校验、document ID 或导入产物，也没有服务重启后继续链路证据。按验收 Skill，API 主路径在 `opened` 停止且核心产物缺失，不能把该 200 当作认证或下载成功。

### 可独立复现的人工验收案例（当前 BLOCKED，不作为已完成案例）

入口：`http://127.0.0.1:8000/`；前置条件：当前部署候选、批次 `1a76e369-c638-4f2c-a430-42552a1e7012`、item `9eed783f-ff98-4021-99dd-1ab2787688cb`、服务端持久快照完整。由于本次禁止登录/生产写操作，步骤 3–5 只能作为后续解除阻塞的验收契约，不能写成已通过。

1. **打开待处理入口**：点击左侧“论文检索”，进入“导入进度”或“需要登录后继续”，找到目标 ACM 条目。预期提示为“等待登录”或“需要登录后继续”；等待批次/item 状态加载；下一步点击同一条目的“打开登录”。若条目不存在或身份不一致，停止并记录 item/batch，不使用客户端 URL。
2. **打开受控登录**：点击“打开登录”。已有真实证据应为 HTTP 200、`status=opened`、`site=acm`；等待本机受控 ACM 窗口打开；下一步切换到该窗口。若出现 424/session 过期，按页面提示重新点击“打开登录”，仍失败则保留 `waiting_login` 和错误。
3. **完成发布方认证（未执行）**：在受控 ACM 窗口按发布方页面完成登录/授权，等待论文访问页或授权完成提示；下一步回到论文检索页面点击“登录后继续”。本步没有本次运行证据，不能声称通过。
4. **验证 resume（未执行）**：点击同一条目的“登录后继续”，等待页面显示同步中，再刷新任务详情；应获得真实 resume 响应和可观察的下载/校验/入库或失败终态。不得把第 2 步的 `opened` 当作第 4 步成功。
5. **验证产物（未执行）**：只有页面显示论文完成/入库，并且保存 item/document ID、最终状态和产物路径，才可判定下载恢复成功；若仍 `waiting_login` 可重新打开登录，若 `failed` 才使用“重试”。当前缺少这些证据，人工验收不得开始。

### Readiness Matrix（Task11 登录/恢复窄修）

| # | 准备度项 | 结果 | 证据/阻塞 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | PASS | `request.md:3-9` 的真实 HTTP 200 login 响应 |
| 2 | 真实 API 创建入口成功 | PASS | `request.md:5-9`、`final-login-response.json:1` |
| 3 | 主路径参数正确解析 | PASS | 响应 item 与请求一致，`site=acm`；`final-login-response.json:1` |
| 4 | 任务/实体状态从初始态推进 | FAIL | 仅到 `opened`，无 resume 后状态；计划 `:74-75` 要求后续终态 |
| 5 | 前端显示处理中提示 | FAIL | 未执行 headed browser/UI；不能把静态代码报告当作运行时提示 |
| 6 | 用户知道何时点击或等待 | FAIL | 产品步骤虽已文档化，但真实 UI 文案/等待事件未验证；按 Skill 不补写未知文案 |
| 7 | 核心业务产物真实生成 | FAIL | 无认证下载、PDF、document ID 或入库产物；`final-login-response.json:1` 只有 opened |
| 8 | 失败状态有可操作恢复 | FAIL | 静态测试覆盖存在，但真实 424/过期/失败后的恢复链未运行 |
| 9 | 页面状态与 API 状态一致 | FAIL | 没有 resume/后续状态或页面截图，无法核对 opened 之后的状态 |
| 10 | 步骤文档可由无上下文用户复现 | FAIL | 步骤 3–5 的真实提示、等待条件和产物路径未验证；`plan.md:67-83` 仅为契约 |

计分：`3/10 PASS`，P0=0，P1=1（产品主路径的认证后 resume/download 证据缺失）。本次不使用 `N/A` 掩盖缺口。共享整合候选的权威最终回归未重跑：后端 `3121 passed / 3 skipped / 0 failed`，见 `docs/sdd/plans/038/2026-10-26-management-backend-test.md:129-142`；前端 `317 passed / 0 failed / 0 skipped`，见 `docs/sdd/plans/038/2026-10-26-management-frontend-test.md:164-176`。3 个后端 skip 的明确原因是：2 个 `tests/e2e/test_research_lifecycle_e2e.py` 需要 `RUN_E2E=1`、浏览器和已启动服务；1 个 `tests/research/test_ollama_direct.py` 因 Ollama 不可达或无可用模型而门控跳过。它们不是本窄修的成功证据，也不是本次新执行结果。

### 最终决定（范围限定）

**BLOCKED。** 当前真实证据只到 HTTP 200 `opened/acm`，缺少认证后的 resume、下载/校验、入库或失败终态及对应产物；按产品主路径和验收 Skill，不能交给用户人工验收，也不能把窄修或整个 Spec032 标记为完成。解除阻塞需由 root 在获授权且服务/浏览器环境可用时，执行一次不含凭据落盘的真实 login→人工认证→resume→下载/入库 E2E，并保存请求、响应、item/document ID、最终状态和产物路径；在此之前保持 BLOCKED，禁止用静态测试或 `opened` 响应替代。

### 签字

**tester：BLOCKED（认证后 resume/download 真实 E2E 与核心产物缺失）。**

**架构师签字：**（留空，待 architect 复核后填写）

---

## 2026-10-26 范围澄清与窄修结论更正（tester）

本节澄清上一节追记的范围判定。上一节把“认证后 resume/download 证据缺失”作为 Task11 窄修的必需门禁，超出了已确认范围；本节仅对该范围判定作更正，保留上一节对“HTTP 200 `opened` 不等于认证或下载成功”的事实说明，也不改写 Spec032 整体暂停状态。

### 已确认的窄修边界

- Spec032 的 2026-10-26 补充条款明确：本次只修已有导入条目的登录/继续路由，优先复用 hash 核验的持久快照与身份检查，解除搜索 TTL 对打开登录/继续路由的错误阻断；不新增 API、表或下载器，不恢复其余暂停范围，未取得授权不能声称论文下载完成，见 `docs/sdd/specs/032-research-source-expansion.md:3-9`。
- 计划进一步固定 durable-first、candidate/search 身份检查、完整快照时跳过 `_paper_search_expired`、受控 ACM/IEEE origin、原有 login/resume 公开响应和 fail-closed 语义，见 `docs/sdd/plans/032/2026-10-26-login-recovery-plan.md:37-44`。
- 该窄修的成功标准是“过期搜索仍可从完整服务端快照打开受控登录页并继续”这一**路由恢复行为**；计划同时明确“打开登录窗口”不等于下载或认证完成，见 `2026-10-26-login-recovery-plan.md:63-80,85-91`。因此，认证凭据、publisher 授权、PDF 下载、KB 入库和后续 Research 报告属于本次未验收边界，不再作为本窄修 READY 的必需条件。

### 范围内证据复核

- 只读诊断确认目标 batch `1a76e369-c638-4f2c-a430-42552a1e7012` / item `9eed783f-ff98-4021-99dd-1ab2787688cb` 处于 `waiting_login`，search TTL 已过；snapshot hash、candidate/search 身份均有效，见 `docs/sdd/plans/032/2026-10-26-login-recovery-plan.md:13-26`。
- 真实主目录请求仍是一次 `POST /api/papers/import-items/9eed783f-ff98-4021-99dd-1ab2787688cb/login`，HTTP 200，响应 `status=opened`、`site=acm`，见 `docs/sdd/plans/032/artifacts/20261026-login-recovery/request.md:1-9`、`final-login-response.json:1`。这已经证明本窄修的“过期 search + 完整 durable snapshot → 受控 login 打开”路径，不证明也不需要证明 ACM 认证下载。
- 64 项集成定向回归为 `64 passed / 0 failed / 0 skipped`，覆盖过期 search TTL 下 durable snapshot 的 service/login/resume 解析、身份篡改、损坏快照 fail-closed、session TTL 和既有 API 生命周期，见 `docs/sdd/plans/032/2026-10-26-login-recovery-test.md:52-59,128-140`。独立复审确认 durable-first、身份门禁、allowlist/SSRF、CAS 和 session TTL 未放宽，见 `2026-10-26-login-recovery-review.md:7-25,63-65`。
- root 反馈服务前台进程曾退出，随后已用 `./deploy/start.sh -d` 启动 PID `20198`，正在进行 health/project 只读复核。该运行时连续性事件不作为产品失败，也不把服务写成当前持续在线；本追记不新增 POST，health/project 的新结果以 root 另行落盘证据为准。

### 范围内人工验收案例

入口：`http://127.0.0.1:8000/`；前置条件：目标已有 `waiting_login` item 和完整持久快照。

1. 点击“论文检索”，进入“导入进度”/“需要登录后继续”，找到目标 item；等待条目状态加载为“等待登录”或“需要登录后继续”，再点击“打开登录”。若 item 不存在、身份不一致或快照损坏，停止并保留稳定错误，不使用客户端 URL。
2. 等待受控 ACM 登录窗口打开；本次范围内的成功判据是服务端返回 HTTP 200、`status=opened`、目标 `item_id` 和受控 `site=acm`。若出现 browser/session 过期或 424，按既有提示重新点击“打开登录”；若出现 `SNAPSHOT_REBUILD_REQUIRED`/身份错误，停止并交由实现方处理。
3. 本次验收到第 2 步结束。用户是否在发布方页面完成认证、是否点击“登录后继续”、是否下载/入库，均保留为后续人工/部署验收边界；不得将第 2 步改写为认证或下载成功。

### 窄修 Readiness Matrix（只计路由恢复范围）

| # | 准备度项 | 结果 | 证据/范围说明 |
|---:|---|---|---|
| 1 | 服务可接受真实请求 | PASS | `request.md:3-9` 的真实 HTTP 200；当前进程连续性由 root 另行只读复核，不在此追记假定持续在线 |
| 2 | 真实 login API 入口成功 | PASS | `request.md:5-9`、`final-login-response.json:1` |
| 3 | 主路径参数正确解析 | PASS | 请求 item 与响应 item 一致，`site=acm`；`final-login-response.json:1` |
| 4 | 路由从过期 search 场景推进到 opened | PASS | 过期 TTL、有效 snapshot 和身份证据 `plan.md:19-26`；真实响应 `final-login-response.json:1` |
| 5 | 登录入口结果可观察 | PASS | `status=opened`/`site=acm` 是本窄修 API 可观察终态；既有 UI 文案与动作契约见 `plan.md:67-75` |
| 6 | 用户知道何时点击或等待 | PASS | 本窄修步骤只要求点击“打开登录”并等待受控窗口；步骤与恢复条件见 `plan.md:69-82` |
| 7 | 窄修核心产物真实生成 | PASS | 本范围核心产物是受控 login response，见 `final-login-response.json:1`；不是 PDF/KB 产物 |
| 8 | 快照损坏/身份错误有可操作恢复 | PASS | 64 项回归及 review 的 fail-closed 证据：`2026-10-26-login-recovery-test.md:52-59`、`2026-10-26-login-recovery-review.md:20-25` |
| 9 | API 状态与目标身份一致 | PASS | batch/item/candidate/search 身份核验及响应 item 一致；`plan.md:19-24,39-43` |
| 10 | 步骤文档可由无上下文用户复现 | PASS | 本节步骤 1–3 与 `plan.md:67-83`；认证下载明确标为后续边界 |

窄修范围计分：`10/10 PASS`，P0=0、P1=0。共享整合候选的最终回归仍沿用既有权威证据且本次未重跑：后端 `3121 passed / 3 skipped / 0 failed`，前端 `317 passed / 0 failed / 0 skipped`。3 个后端 skip 的原因保持为：2 个研究生命周期 E2E 需显式 `RUN_E2E=1`、浏览器和已启动服务；1 个 Ollama 直连流因 Ollama 不可达或无可用模型而门控跳过。

### 更正后的最终决定

**READY_FOR_USER（仅限“持久快照优先、解除搜索 TTL 对已有 item login/resume 路由错误阻断”的窄修范围）。** 真实 login API、持久快照身份/TTL 边界和 64 项恢复回归均通过。该结论不表示用户已完成 ACM 认证，不表示 PDF 已下载或 KB 已入库，也不表示后续 Research Task 已完成。

**Spec032 整体仍为“暂停，待下次继续”，不得标记为已完成。** 认证后 resume、下载/校验、入库、来源年度覆盖及其他暂停范围仍是未验收边界；本追记不要求为本窄修新增真实 ACM 认证下载。

### 签字

**tester：READY_FOR_USER（仅限上述登录/继续路由窄修）。**

**架构师签字：GO（仅限“持久快照优先、解除搜索 TTL 对已有 item login/resume 路由错误阻断”的窄修）。**

核对结论：过期 search 场景下完整 durable snapshot 的身份/哈希校验、受控来源门禁、真实 login API `200/opened/acm` 与 `64/64` 定向回归均通过，窄修范围准备度 `10/10`、P0/P1 均为 0。

明确遗留：本轮没有验证真实发布方认证、认证后 resume、PDF 下载/校验、KB 入库或后续研究产物；不得将 `opened` 响应冒称为上述成功。Spec032 整体继续保持“暂停，待下次继续”，不得标记为已完成。

签字时间：2026-10-26（Asia/Shanghai）
