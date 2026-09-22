# Spec032 验收评审

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
