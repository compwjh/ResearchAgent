# Task 14：最终评审、回归、部署与复盘

> 关联：[Spec 032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task06–13、Task15–17 真实完成；当前状态：`实施中`

## 一句话目标

完成七来源复用、安全、字段 provenance、四会议逐年覆盖、Worker 自动导入、人工修复与 032.1 余项验收，运行本 Spec 唯一全量回归并部署收口。

## 完整分派 Prompt

```text
角色：双端 reviewer/tester、跨端 tester、architect；读取 Spec032、Task06–13 报告、资产审计、fixtures 和真实 diff。
允许修改：reviews/032-*.md、plans/032/artifacts/task-14/**、对应 retro；P0/P1 修复退回对应开发 Task。
禁止无边界批量抓取、伪造外部成功、自动 push/merge/reset/stash/clean；真实 PDF smoke 仅选受控小样本且复用安全链。
验证：四会议逐年官方目录/摘要/缺失/下载正确性、增量缓存、provenance、单源失败、多 Skill 同一 Tool schema、计划内自动导入、登录或上传人工修复、重启恢复、旧报告不可变；随后唯一全量回归、受控 live smoke 和部署。
完成状态：三评审和签字齐全，受控真实成功案例与用户操作步骤可复现；不可用来源诚实记录 NO-GO/复验路径。
返回固定交接字段、命令/退出码/通过数与部署 URL。
```

## 主 Agent 校验、风险与产出

- 字段覆盖错误、错误 PDF 入库、任意 URL、缓存清空、假 queued、失败项无法操作或重复实现均阻塞。
- 产出评审、验收、复盘和部署证据；执行结果待填写。

## 变更日志

- 2026-10-06：当前版本真实自然语言 E2E 创建会话和计划成功，但“最多5篇/目标论文数5”约束未保留，计划预算静默回落为12。记录 P1 并在批准前停止，未触发超额下载；证据见 `artifacts/task-14/current-research-e2e-report.md`。修复复用现有 Intake constraints 与计划预算，不新增来源或第二套编排。Semantic Scholar autocomplete/citations/references 当前真实 API 已通过，见 `current-semantic-live-report.md`；不以 API slice 代替全流程验收。

- 2026-09-12：原 Task06 创建最终收口要求。
- 2026-09-20：随新版 Spec032 顺延为 Task14，保留原评审/回归/部署目的并增加多来源自动导入与人工修复验收。
- 2026-09-20：Task08 P1 多来源 Worker bridge 已完成离线修复；Task07 补齐 NDSS 2024 固定样本与 CCS 2021–2025 bounded NO-GO 审计；相关回归 760 passed。18080 服务已由真实浏览器加载，API health/外部来源/导入与重启 smoke 仍待可用网络环境复验，Task14 保持实施中。
- 2026-09-20：Task11 recovery bridge follow-up 完成；waiting_login/failed/resolved 动作与人工恢复审计定向通过，Spec032 相关回归更新为 765 passed。真实 headed-browser/远程上传和重启 smoke 仍待可用网络环境复验。
- 2026-09-20：18080 沙箱外 health/ready 均 HTTP 200；USENIX 2024（227）与 NDSS 2024 official（142）目录同步完成，重启后句柄可读；IEEE S&P 2024 外站同步失败并按 degraded 记录。完整四会覆盖、登录/导入和业务批次恢复仍阻塞收口。
- 2026-09-21：新增 Semantic Scholar OA 回退调研与最小接入。适配器仅按 DOI/ArXiv ID读取 Academic Graph API 的 `openAccessPdf.url`；Worker 在主下载失败后复用既有导入链重试，固定 allowlist 外的 PDF 主机返回 `SEMANTIC_SCHOLAR_UNSUPPORTED_PDF_HOST`。本环境 `api.semanticscholar.org` DNS 不可解析，真实外部成功案例留部署环境复验，不伪造成功。
- 2026-09-22：Task15–17 最小实现继续落地：批量元数据补全与字段 provenance、有界 bulk recall 的 completed fetch-unit 缓存、autocomplete/citations/references metadata-only API。Semantic Scholar 相关定向回归 66 passed、12 subtests，Ruff/py_compile 通过；当前环境对官方 API 的 DNS smoke 仍失败，Task14 保持实施中，未宣称 Spec032 完成。
- 2026-09-22：补强 Semantic Scholar 429 合同与 SQLite 持久化收口检查；paper_discovery/research/skills 集合回归 `1506 passed, 38 subtests`，测试布局、Ruff、`git diff --check` 通过。该回归仅证明代码与本地 SQLite 合同，四会议年度覆盖、真实候选导入/人工修复、重启业务批次和独立签字仍需 Task14 继续完成。
- 2026-09-22：受控真实来源 smoke：`POST /api/papers/sources/usenix/sync` 请求 2024 年，sync `sync-usenix-2f71bd0968624480` 终态 HTTP 200/completed，缓存并完成 summer/fall 两个页面单元，共 227 篇，`degraded=false`。该证据只覆盖 USENIX 2024，不代表四会议逐年覆盖或 Spec032 收口。
- 2026-09-22：受控真实来源 smoke：`POST /api/papers/sources/ndss/sync` 请求 2024 年，sync `sync-ndss-6a4e6e04bb1641b5` 终态 HTTP 200/completed，official 单元共 142 篇，`degraded=false`。该证据只覆盖 NDSS 2024，其他年度和 CCS/IEEE S&P 仍按现有 NO-GO/未验证记录处理。
- 2026-09-22：应用重启后以 `PORT=18080 RERANKER_ENABLED=false ./deploy/start.sh` 重新启动，进程完成 startup，沙箱外 `GET /api/health` 返回 HTTP 200，`paper_discovery_enabled=true`；已完成的 USENIX/NDSS SQLite 状态继续可读取。该次重启只证明服务恢复，不替代完整业务批次恢复验收。
- 2026-09-22：受控真实检索 smoke：`POST /api/papers/searches` 查询 USENIX Security 2024，search `8b2944b58b994a00bdc02011a5e7ff48` 终态 HTTP 200/`partial`，USENIX 缓存命中 227 篇，DBLP 明确 `SOURCE_SKIPPED`；结果页 HTTP 200，第一页冻结 10 篇，`total_pages=23`。`degraded=true` 仅记录当前索引/RAG 环境降级，目录候选仍可读，未触发 PDF 下载。
- 2026-09-22：重启后读取既有导入批次 `83846ea1-0178-421a-bc8b-2ea5d8b7a0de` 返回 HTTP 200，`partial_success`，3 项成功、3 项 `KB_IMPORT_FAILED`；成功项文档句柄和失败项 `cleanup_pending` 均保留。该证据补齐批次快照恢复读取，失败项的人工修复闭环仍待单独绑定 Research Task 的 issue 流程验收。
- 2026-09-22：受控 DBLP 2024 辅助同步 `sync-dblp-9df36fe7786646f2` 终态 HTTP 200/`failed`，稳定错误码 `DBLP_INVALID_RESPONSE`、`degraded=true`，未写入假数据；该来源失败按降级语义保留，USENIX/NDSS 官方目录结果不受影响。
- 2026-09-22：补齐批准计划自动导入的任务级失败投影。批次项完成 `failed`/`waiting_login` CAS 转换后，通过现有 `ResearchAcquisitionService.record_acquisition_issue` 写入 Research issue store；`GET /api/papers/issues?task_id=...&status=open` 可读取候选、稳定错误码、批次与导入项句柄。相关定向测试 46 passed，补充回归 14 passed；本轮 Spec032 相关集合最终为 `1507 passed, 38 subtests`，Ruff、测试布局检查和 `git diff --check` 通过。该证据关闭“后台失败不进入待处理队列”的代码缺口，但仍不替代真实浏览器人工登录/上传恢复和独立签字。
- 2026-09-22：来源编排复核确认：`CatalogSourceFactory` 对 `ieee_sp`、`ccs`、`ndss`、`openalex`、`crossref` 统一返回同一 `PaperDiscoveryToolFacade/SourceRegistry/Store` 组合，旧 `CatalogSearchGraph` 明确只保留 USENIX/DBLP；新增契约测试 10 passed，连同研究事件和旧 Graph 回归共 35 passed。未新增抓取或缓存实现；四会议真实年度覆盖仍按 Task07/Task14 的证据矩阵处理。
- 2026-09-22：直接异步端点边界复核：`POST /api/papers/searches` 保持 Spec015 的 USENIX 快照/分页契约；Spec032 多来源研究主链使用 `SearchWorker → CatalogSearchAdapter → PaperDiscoveryToolFacade`，不把非 USENIX 来源塞入旧 Graph。新增 `ieee-sp` 拒绝契约测试，定向 `9 passed`，避免形成第二条多来源检索链。
- 2026-09-22：受控真实来源 smoke 补齐 2024 年：`ieee_sp` sync `sync-ieee_sp-3832cae3abac4953` 完成 43 篇，`ccs` sync `sync-ccs-5cdac45217d4400a` 完成 328 篇，均 HTTP 200、`degraded=false`；与此前 USENIX 227、NDSS 142 一起形成四会议 2024 单年度真实成功证据。该证据不扩展到未验证年度，也不替代候选评估、导入/人工修复、重启业务批次和独立签字。
- 2026-09-22：修复并验证 generic Worker 的重启缓存接缝：新进程对已完成的 IEEE S&P、CCS、NDSS 2024 fetch unit 从 SQLite source records 读取，三次 `discover` 均 `completed`、`cache_hit=true`、各返回 3 个候选且未触发外站同步；同时保留 `sp` conference ID 与 `ieee_sp` source kind 的区分。相关定向回归 34 passed，Ruff、测试布局和 diff-check 通过。
- 2026-09-22：修复批量导入浏览器续传的 queued 初始竞态：`resume_item` 现在在首次 runner 尚未完成时有界等待其 CAS 转换到 `waiting_login/failed`，再执行一次续传；等待上限调整为 5 秒，避免繁忙进程把未完成的 queued 快照投影成 200 成功。目标竞态重复 10 次、批量/Research 定向回归均通过；随后 `tests/paper_discovery tests/research tests/skills` 集合 `1513 passed, 38 subtests, 5 warnings`，Ruff、测试布局和 `git diff --check` 通过。
- 2026-09-22：DBLP 辅助同步继续保持真实降级语义：受控 2024 请求返回 `DBLP_INVALID_RESPONSE/degraded=true`，未写入假数据；新增非 JSON/bot-challenge 响应合同测试（定向 `9 passed`），确认适配器会把外站 HTML 稳定映射为结构化错误而不是误当论文数据。当前网络/DNS 无法提供可复核的 DBLP 成功响应，因此该来源保留 NO-GO，待部署环境复验。
- 2026-09-22：新增候选评估→批准计划→自动导入→任务级 issue 投影离线集成回归，复用既有 `PlanApprovalService`、`Orchestrator._persist_agent_selections`、`ApprovedPlanAutoImporter`、`ResearchAcquisitionService` 与 `PaperImportBatchService`。固定 SQLite 样本验证一个候选 `completed`、一个候选 `waiting_login`，仅产生对应任务的 `LOGIN_REQUIRED` issue；定向组合 `26 passed`，Ruff、测试布局与 diff-check 通过。真实 PDF/浏览器登录仍留部署环境验收。
