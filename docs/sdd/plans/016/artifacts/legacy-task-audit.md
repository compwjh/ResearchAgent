# Spec016 Task08 — Spec013–015 legacy task evidence audit

## 范围与基线

只审计现存的 31 个 legacy Task 文档：Spec013 Task02–08（7 项）、Spec014 Task02–09（8 项）、Spec015 Task02–17（16 项），并核对各 Spec、对应 plans README、明确引用的 reviews/retro/artifacts、少量相关代码存在性及路径限定的 Git 历史。未运行测试、未检查外部服务健康、未改动任何 legacy 文档或业务文件。

审计时所在 worktree 为 `feature/spec-016-portable-task-ledger@c9ae563673109fdf747732686fa3f4a2d1add90e`，审计前 `git status --short --branch` 干净；`git worktree list` 另显示 `main@5b1b1d918db8858e848a73da4cee2df54f513ea2`。未检查后台进程，因此不对其他 worktree 的活跃写入作结论。Git 提交只按任务/相关代码路径查询；未把相似代码自动归属给任务。

## 裁决摘要与机械迁移规则

| 分类 | 数量 | 迁移处理 |
|---|---:|---|
| `completed` | 22 | 可机械写入 completed 元数据和 `provenance=legacy` 摘要；不得把单个 Task 的完成扩大成整个 Spec 完成。 |
| `partial` | 7 | 保留原任务和证据，另建边界清楚的剩余工作 Task；不重做已验证的实现。 |
| `pending` | 1 | 可写 pending；按原 Task04 Prompt、依赖和验收范围补齐可领取协议。 |
| `migration_unverified` | 1 | 保持不可领取；解除条件写入 Task 元数据，不猜测或复用归属不明成果。 |

机械迁移应按 Spec 分批：先 013、再 014、最后 015；每批只改该 Spec 的权威 Task 元数据/镜像和对应 legacy 摘要。Spec015 的 Task15–17 只按 **USENIX-only** 范围记录完成，整体 Spec 仍保持 `实施中`。Task04、Task10 以及外部验收缺口不得因 Task15–17 完成而解除。spec-013 当前状态行和任务索引互相冲突时，以本矩阵列明的具体结果/评审证据迁移 Task；Task08 仍为 partial，不能据单个 Spec 状态行自动关闭。

所有任务的旧运行记录均没有可迁移的统一 SDD run 元数据：`unknown_metrics` 对每行均为 `{run_id:null, started_at:null, ended_at:null, model:null, input_tokens:null, output_tokens:null, tool_count:null, duration_seconds:null}`。表中出现的测试数、软件版本、HTTP 状态或业务测量值，均是原文已经记录的证据，不用于推算这些缺失指标。

## Spec013

| Task | document_status（Task / README / Spec） | evidence_files / commit | classification | remaining_work | unknown_metrics |
|---|---|---|---|---|---|
| 02 非 Docker 部署基础设施 | Task结果记 2026-09-02 Go 通过；README/Spec：完成（Go） | `docs/sdd/plans/013/task-02-deploy-langfuse.md`；`docs/sdd/specs/013-llm-observability-platform.md`；`deploy/langfuse/`；commit `33da46f`（部署脚本/配置入库） | `completed` | null；当时的健康/启动证据为历史运行记录，本审计未重启服务。 | 全部 null |
| 03 Python 3.11 升级 | Task结果记录 3.11.16、253 passed、API 冒烟；README/Spec：完成 | `docs/sdd/plans/013/task-03-upgrade-python.md`；`requirements.txt`、`requirements.lock.txt`；commit `33da46f` | `completed` | null；Task03 已记录恢复环境、依赖与当时回归结果。 | 全部 null |
| 04 Ollama 直连采集与埋点 | Task结果：28 项定向测试及真实 v4 events 写入通过；README/Spec：完成（events_only 已验证） | `docs/sdd/plans/013/task-04-ollama-direct.md`；commit `33da46f`（其中含历史路径 `tests/test_ollama_direct.py`、`tests/test_observability.py`） | `completed` | null；Task05 承接业务链路接入。 | 全部 null |
| 05 chat/KB 链路埋点 | Task结果：聊天与 KB 真实请求/事件已记；README/Spec：完成 | `docs/sdd/plans/013/task-05-instrument-chat-kb.md`；`docs/sdd/reviews/013-task05-current-review.md`；commit `33da46f`（含历史链路测试路径） | `completed` | null；Task05 的实际边界不含统计视图。 | 全部 null |
| 06 原生 Dashboard 与 numeric score | Task结果：固定样本、20 generations/140 scores、七项指标及 Dashboard 配置有复核记录；README/Spec：完成 | `docs/sdd/plans/013/task-06-stats-native.md`；`docs/sdd/reviews/013-stats-native-review.md`；`docs/sdd/reviews/013-task06-tech-review.md`；commit `33da46f` | `completed` | null；路径 A 的复杂可视化明确交给 Task07。 | 全部 null |
| 07 Ollama Insights 专用视图 | 原始 Task结果曾记开发中；后续 2026-09-04 修复轮次记录 37 个前端用例通过和验收更新为“通过（主模型代行）”；README：完成；Spec 表仍显示实施中 | `docs/sdd/plans/013/task-07-stats-custom-view.md`；`docs/sdd/reviews/013-task07-architecture-review.md`；`docs/sdd/reviews/013-task07-acceptance-review.md`；commit `07a3124`, `d0c4e0a`, `33da46f` | `completed` | null；实现和修复轮次有落盘证据，验收非独立 tester 由主模型代行这一事实须写入 legacy 摘要。 | 全部 null |
| 08 评审、验收、部署与复盘 | Task 头部/README：完成；Spec 任务表仍写待执行。Task结果称主模型代行收口，但其 DoD 要求的 Spec 级 `013-acceptance-review.md`、Tech Lead 验收签字、独立 A1–A10 验收和独立 Spec013 retro 文件没有落盘；存在的 `013-task07-acceptance-review.md` 仅覆盖 Task07 | `docs/sdd/plans/013/task-08-review-retro.md`；`docs/sdd/reviews/013-requirement-review.md`、`013-tech-review.md`、`013-task07-acceptance-review.md`；`docs/sdd/specs/013-llm-observability-platform.md`；commit `33da46f`（代码/文档提交，不等同于全部 Task08 DoD） | `partial` | 只补收口证据：形成 Spec013 范围的 A1–A10 验收报告并完成规定的 Tech Lead 签字；单独落盘 Spec013 retro；回填一致的验收状态。不要重新实现 Task02–07，也不要把 Task07 验收报告当成 Spec 级验收。 | 全部 null |

## Spec014

| Task | document_status（Task / README / Spec） | evidence_files / commit | classification | remaining_work | unknown_metrics |
|---|---|---|---|---|---|
| 02 Reranker 运行时 Go/No-Go | Task：完成（Go）；README/Spec：完成；后续 benchmark/最终验收引用真实运行时探针 | `docs/sdd/plans/014/task-02-validate-reranker-runtime.md`；`docs/sdd/reviews/014-reranker-benchmark.md`；commit `aae28c0`, `e980cea` | `completed` | null | 全部 null |
| 03 Reranker 生命周期 | Task：完成；README/Spec：完成；Spec级最终验收和复盘纳入部署、启动/停止与健康证据 | `docs/sdd/plans/014/task-03-reranker-service-lifecycle.md`；`docs/sdd/reviews/014-acceptance-review.md`；`deploy/reranker/`；commit `aae28c0`, `e980cea` | `completed` | null | 全部 null |
| 04 Reranker 客户端 | Task：完成；README/Spec：完成；验收矩阵核对批量映射、错误降级与稳定排序测试 | `docs/sdd/plans/014/task-04-reranker-client.md`；`docs/sdd/reviews/014-acceptance-review.md`；`backend/app/knowledge_base/infrastructure/reranker.py`；commit `aae28c0`, `e980cea` | `completed` | null | 全部 null |
| 05 接入知识库检索 | Task正文曾写进行中；README/Spec：完成；最终验收证明真实请求、Reranker 成功/停服降级路径 | `docs/sdd/plans/014/task-05-integrate-retrieval-pipeline.md`；`docs/sdd/reviews/014-acceptance-review.md`；commit `aae28c0`, `e980cea` | `completed` | null | 全部 null |
| 06 健康状态与前端展示 | Task/README/Spec：完成；最终验收核对 enabled/disabled/degraded 状态及健康端点 | `docs/sdd/plans/014/task-06-reranker-health-status.md`；`docs/sdd/reviews/014-acceptance-review.md`；commit `aae28c0`, `e980cea` | `completed` | null | 全部 null |
| 07 测试与质量基准 | Task/README/Spec：完成；冻结集 benchmark 记录 MRR@5 由 0.225 到 0.495、覆盖率和后续 269 passed 复测；Spec最终验收另有 346 passed 记录 | `docs/sdd/plans/014/task-07-reranker-tests-benchmark.md`；`docs/sdd/reviews/014-reranker-benchmark.md`；`docs/sdd/reviews/014-acceptance-review.md`；commit `aae28c0`, `e980cea` | `completed` | null | 全部 null |
| 08 集成 Spec013 观测 | Task文档结果段仍是早期待填写；README/Spec：完成。最终验收已有四种开关组合、真实 `kb.rerank` 事件、SSE 收尾及停服/恢复路径的 tester 结论 | `docs/sdd/plans/014/task-08-integrate-spec013-observability.md`；`docs/sdd/reviews/014-acceptance-review.md`；`docs/sdd/reviews/014-tech-review.md`；commit `e980cea`, `550d1a4` | `completed` | null；不得把验收报告前半段的早期失败快照当作当前结论，最终 tester 结论与签字在后续补录章节。 | 全部 null |
| 09 评审、部署与复盘 | Task文档结果段保留早期待填写；README/Spec：完成。后续验收包含 tester 通过、Tech Lead 签字、retro 与完成状态提交 | `docs/sdd/plans/014/task-09-review-deploy-retro.md`；`docs/sdd/reviews/014-acceptance-review.md`；`docs/sdd/retro/2026-09-04-spec-014-reranker-retro.md`；commit `550d1a4`, `c17c7f4` | `completed` | null；接受 Tech Lead 签字由主会话代行且 retro 已记录该偏差，属于 provenance 事实，不构成未交付实现。 | 全部 null |

## Spec015

| Task | document_status（Task / README / Spec） | evidence_files / commit | classification | remaining_work | unknown_metrics |
|---|---|---|---|---|---|
| 02 基线、数据源与浏览器桥接 | Task/README/Spec：条件放行（内置会议；Venue Search blocked）；评审支持有限放行，不支持把 DBLP Venue Search 或项目 Playwright 登录记为通过 | `docs/sdd/plans/015/task-02-validate-baseline-and-sources.md`；`docs/sdd/reviews/015-task02-baseline-review.md`；`docs/sdd/reviews/015-task02-tech-review.md`；Spec015 Task03 final signoff；commit `b76cda1`（检查点） | `partial` | 补齐 DBLP Venue Search 的稳定真实样本/限流退避结论及项目 Playwright profile 的浏览器桥接/登录续传证据；若这些仍 deferred，保持本项 partial 与下游门禁，不能把条件放行写成完整 Go。 | 全部 null |
| 03 会议配置与论文召回 | Task/README/Spec：完成（内置会议与 OpenAlex 收窄范围）；Tech Lead最终签核明确标注仅适用于收窄范围，41 项目标测试通过 | `docs/sdd/plans/015/task-03-conference-registry-and-retrieval.md`；`docs/sdd/reviews/015-task03-tech-review-final-signoff2.md`；`docs/sdd/reviews/015-task03-acceptance-review.md`；commit `b76cda1`（检查点） | `completed` | null；DBLP Venue Search/custom conference 的已知缺口属后续扩展，不扩大 Task03 的已签范围。 | 全部 null |
| 04 语义排序与 Reranker 集成 | Task/README/Spec：待执行；未见此 Task 的执行/验收报告。Task15 的 RRF/可选 reranker 代码不构成 Task04 自动完成归属 | `docs/sdd/plans/015/task-04-semantic-ranking-and-rerank.md`；`docs/sdd/plans/015/README.md`；`docs/sdd/specs/015-security-paper-discovery.md`；commit：null（未定位到 Task04 专属提交） | `pending` | 按 Task04 原范围实现语义排序与 Spec014 Reranker 接入；明确冻结质量集、排序指标/门槛、失败降级与定向/回归验收。Task03、Spec014 的既有完成结果作为依赖证据，不复做。 | 全部 null |
| 05 安全下载、规范命名与 KB 导入 | Task/README/Spec：完成（单篇闭环）；最终 QA 与 Tech Lead 签字通过，明确批量/真实登录留给后续 Task | `docs/sdd/plans/015/task-05-secure-download-and-kb-import.md`；`docs/sdd/reviews/015-task05-acceptance-review-final.md`；`docs/sdd/reviews/015-task05-tech-review-recheck-final.md`；commit `b76cda1`（检查点） | `completed` | null；只篇级安全下载/导入闭环属于本 Task 已验范围。 | 全部 null |
| 06 批量任务与登录续传 | Task/README/Spec：实施中（离线安全复核通过；真实登录环境阻塞）；已记录项目 Playwright profile 对 ACM PDF 仍为 `LOGIN_REQUIRED`，未复用用户 Chrome 凭证 | `docs/sdd/plans/015/task-06-batch-import-and-login-resume.md`；`docs/sdd/reviews/015-task06-acceptance-review-final-security-recheck.md`；`docs/sdd/reviews/015-task06-tech-review-final-security-recheck.md`；`docs/sdd/reviews/015-real-browser-session-20260905.md`；commit `b76cda1`（检查点） | `partial` | 在项目隔离的 Playwright profile 和合法用户授权下完成 ACM/IEEE 登录后续传真实闭环；核对续传任务的批次状态与导入结果。外部登录条件未满足前不可标 completed。 | 全部 null |
| 07 论文检索 Tab 与交互 | Task/README/Spec：实施中（离线通过；A3/真实环境阻塞）；最终旧范围验收仍有功能/GUI/ACM/IEEE/A14 缺口 | `docs/sdd/plans/015/task-07-paper-discovery-tab.md`；`docs/sdd/reviews/015-task07-acceptance-review-final.md`；`docs/sdd/reviews/015-task07-tech-review-signoff.md`；`docs/sdd/reviews/015-acceptance-review.md`；commit `b76cda1`（检查点） | `partial` | 先完成依赖 Task04 后，补齐 A3 自定义会议/完整交互、真实 GUI 与受控外站验收及关闭 flag 的用户界面证据；不把 Task16 的 USENIX-only 页面范围当成原完整 UI 验收。 | 全部 null |
| 08 测试、排序基准与安全回归 | Task/README/Spec：实施中（离线安全/回归通过；排序质量与真实环境阻塞）；Task08 QA明确不通过且 Tech Lead 待签字 | `docs/sdd/plans/015/task-08-tests-ranking-and-security.md`；`docs/sdd/reviews/015-task08-acceptance-review.md`；`docs/sdd/reviews/015-task08-security-matrix.md`；`docs/sdd/reviews/015-task08-quality-recheck.md`；commit `b76cda1`（检查点） | `partial` | 冻结人工相关性标注集并完成 A14 的 nDCG/Recall 排序基准；补真实公开 PDF、真实 KB 物理文件/索引对账、GUI、ACM/IEEE 登录与全范围回归证据；取得 Tech Lead 复核。离线安全用例不需重做。 | 全部 null |
| 09 评审、部署与复盘 | Task/README/Spec：实施中（离线回归与本地部署通过；外部验收阻塞）；Spec级旧范围验收仍明确不通过/阻塞 | `docs/sdd/plans/015/task-09-review-deploy-retro.md`；`docs/sdd/reviews/015-acceptance-review.md`；`docs/sdd/retro/2026-09-05-spec-015-retro.md`；`docs/sdd/retro/2026-09-07-spec015-closure-branch-mixup-and-ruff.md`；commit `b76cda1`（检查点） | `partial` | 在 Task04/06/07/08 阻塞解除后完成全范围 A1–A20验收、Tech Lead最终签字、部署/运行记录和此范围的收口复盘；不得把 Task17 的 USENIX-only tester 报告提升为全 Spec 通过。 | 全部 null |
| 10 论文发现限界上下文目录重构 | Task执行结果明确“未移动或修改业务代码”、待架构确认；README/Spec：待确认。之后 Spec017 有 `232d7c4` 明确迁移论文发现上下文，但与 Task10 完成标准的对应关系没有回填确认 | `docs/sdd/plans/015/task-10-paper-discovery-package-migration.md`；`docs/sdd/plans/015/README.md`；`docs/sdd/specs/015-security-paper-discovery.md`；Spec017 commit `232d7c4` | `migration_unverified` | CLI 不得自动领取。解除条件：只读对比 Task10 验收标准与 Spec017 commit `232d7c4`/当前目录结构，由权威维护者明确标记“被满足/被取代”或写出未满足的不同工作；在此之前不归属 Spec017 代码、不重复重构。 | 全部 null |
| 11 USENIX accepted 与 arXiv 兜底 | Task/README/Spec：完成；验收报告记录 QA、Tech Lead通过 | `docs/sdd/plans/015/task-11-usenix-accepted-and-arxiv-fallback.md`；`docs/sdd/reviews/015-task11-acceptance-review.md`；`docs/sdd/reviews/015-task11-tech-review-final.md`；commit `b76cda1`（包含当时 Spec015 检查点） | `completed` | null | 全部 null |
| 12 USENIX Skill 与跨 IDE 协议 | Task/README/Spec：完成（下载版/目录版）；验收报告确认静态与跨 IDE 协议落盘，并区分搜索元数据与用户导入 | `docs/sdd/plans/015/task-12-usenix-paper-skill.md`；`docs/sdd/reviews/015-task11-acceptance-review.md`；Spec015 skills 调整 commit `a037250`；检查点 `b76cda1` | `completed` | null | 全部 null |
| 13 全局目录协议与复用审计 | Task结果：完成，具名提交 `fe17e71`；README：完成；Spec任务表仍显示约60%/实施中，但 Task 结果与报告更晚且具体 | `docs/sdd/plans/015/task-13-catalog-contract-and-reuse-audit.md`；`docs/sdd/reviews/015-task13-reuse-audit.md`；`docs/sdd/reviews/015-task13-schema-implementation.md`；`docs/sdd/reviews/015-task13-store-implementation.md`；commit `fe17e71`（前置检查点 `b76cda1`） | `completed` | null | 全部 null |
| 14 USENIX 增量目录同步 | Task文档仍是待执行且“执行结果待填写”；README/Spec表：完成。固定 parser 报告有 fixture/12 passed；后续 feature commit和USENIX-only验收证明空库同步、缓存/accepted 查询路径。Spec表引用的 `015-backend-review.md` 当前实际是 Spec017 memory 审查，不能当 Task14 证据 | `docs/sdd/plans/015/task-14-usenix-incremental-catalog.md`；`docs/sdd/reviews/015-task14-usenix-parser.md`；`docs/sdd/reviews/015-task17-acceptance-usenix-only.md`；`docs/sdd/reviews/015-task15-backend-review-final.md`；commit `f7ca599` | `completed` | null；迁移摘要必须保留 Task14 任务正文过期及错误 review 引用的审计注记。 | 全部 null |
| 15 LangGraph、目录 RAG 与冻结结果 | Task/README：完成（USENIX-only）；Spec任务表仍写待执行。后端最终评审 PASS；定向 105 passed、后端全量 650 passed 等结果已记录 | `docs/sdd/plans/015/task-15-langgraph-catalog-rag.md`；`docs/sdd/reviews/015-task15-backend-review-final.md`；`docs/sdd/reviews/015-task17-acceptance-usenix-only.md`；commit `f7ca599` | `completed` | null；只迁移 USENIX-only 完成范围；外部会议、A14排序和真实登录仍归其他 partial Task。 | 全部 null |
| 16 来源进度与十条分页 | Task/README：完成（USENIX-only）；Spec任务表仍写待执行。执行结果记录异步状态轮询、固定分页、来源卡片和旧同步路由移除；Task17验收包含前端契约及语法检查 | `docs/sdd/plans/015/task-16-search-progress-and-pagination.md`；`docs/sdd/reviews/015-task17-acceptance-usenix-only.md`；commit `f7ca599` | `completed` | null；只确认 USENIX-only 页面/进度交付。 | 全部 null |
| 17 复用审计、验收、部署与复盘 | Task/README：完成（USENIX-only）；Spec任务表仍写待执行。Task17 QA报告确认 USENIX-only通过、整Spec保持实施中；Task执行结果记部署 smoke，但报告没有 Tech Lead签字，也未找到本轮指定的 USENIX catalog retro | `docs/sdd/plans/015/task-17-review-acceptance-deploy-retro.md`；`docs/sdd/reviews/015-task17-acceptance-usenix-only.md`；`docs/sdd/reviews/015-task15-backend-review-final.md`；`docs/sdd/reviews/015-acceptance-review.md`；commit `f7ca599` | `partial` | 保留已通过的 USENIX-only QA/部署证据；补 Task17 范围的复盘和 Tech Lead 对 USENIX-only 收口的明确签字。Spec015 全范围 A1–A20 的阻塞继续由 Task02/04/06–09 跟踪，不能由本项单独关闭。 | 全部 null |

## 需要保留的跨任务事实

- Spec013：Task07 后续修复与主模型代行验收的证据晚于原始“实施中”记录，因此 Task07 迁移为 completed；Task08 的 Spec 级验收/签字/retro 产物仍缺，迁为 partial。不要据此重做 Task02–07，也不要把当前 Spec 状态行当作 Task08 完整完成的证据。
- Spec014：虽 Task08/09 的任务正文仍留早期占位，但 `014-acceptance-review.md` 后续记录四组合 tester 通过并有 Tech Lead签字；`2026-09-04-spec-014-reranker-retro.md`、`550d1a4`/`c17c7f4`及最终 README/Spec 状态共同支持 8 项 completed。较早的“不通过/不可签字”记录是被后续复核替代的历史快照。
- Spec015：Task02–09旧范围中仍有被报告明确列出的外部/质量验收缺口；Task15–17 的 USENIX-only通过不能改变 Spec015 总状态。Spec15 README 与 spec任务表有明显时间错位，应迁移 Task 时保留来源和范围；不批量把 Spec表中的旧 pending 覆盖到新任务记录。
- Task14 的 `015-backend-review.md` 文件名仍被旧 Spec015 Task表引用，但该文件当前标题和主体属于 Spec017；禁止将此错误引用作为 015 Task14 的评审签核。
- Task10 与 Spec017 `232d7c4` 只做关联提示，不做自动代码归属或自动 completed 判决；维持 migration_unverified 直到解除条件满足。
