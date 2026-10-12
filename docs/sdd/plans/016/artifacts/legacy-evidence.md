# Spec 013–015 legacy 任务事实审计

审计点：当前 `main` 内容快照 `5b1b1d918db8858e848a73da4cee2df54f513ea2`（本 worktree 的 `main` / `origin/main` 指向该提交）。本报告只整理现存证据，不修改 013–015 文档或任务状态。

## 判定规则

- **原状态**取各 spec 任务表为主；若 README、Task 执行记录或更新的评审记录不同，逐项指出，不把表格占位直接当执行事实。
- **事实判断**相对于任务原始验收范围；注明“收窄范围”或“USENIX-only”的，代表只完成该明确子范围。
- **可领取**本轮一律 `false`。这是迁移事实底稿，不是给业务代码派工的队列。
- 对 `partial` / `unverified` 项，只能把已证明成果作为只读历史输入；具体缺口应先对齐当前 main 与后续 spec，建立新的、窄范围、经授权的任务，不能照旧任务表重做。

## Spec 013 — 本地 LLM 调用观测与性能评估

| Task | 原状态 | 事实判断 | 当前 main 证据 | 可领取 | 后续迁移建议 |
|---|---|---|---|---|---|
| 01 编写 spec | 完成 | completed | [Spec 013](../../../specs/013-llm-observability-platform.md:186) 自身即任务产物，当前 spec 状态为 `已完成`（L3–5）。 | false | 仅迁移为已完成历史记录。 |
| 02 Langfuse v4 非 Docker 部署 | 完成（Go） | completed | [Task02](../../013/task-02-deploy-langfuse.md:137) 记录 ClickHouse 26.9.1、PostgreSQL/Redis/MinIO、Langfuse 4.27.0 健康和启停脚本验收通过（L141–148）。 | false | 沿用已完成的部署证据；不重新安装或启动基础设施。 |
| 03 Python 3.11 升级 | 完成 | completed | [Task03](../../013/task-03-upgrade-python.md:129) 记录 Python 3.11.16、SDK 4.15.1、253 passed 及 API 冒烟通过（L133–139）。 | false | 只迁移结果与回滚信息。 |
| 04 直连采集器和观测封装 | 完成（events_only 已验证） | completed | [Task04](../../013/task-04-ollama-direct.md:132) 记录采集器、观测封装、28 项定向测试及真实 `events_full/events_core` 写入（L136–143）。 | false | 保留 v4 events_only 的真实表口径；勿把旧 traces/observations 空表当成未开发。 |
| 05 聊天和 KB 埋点 | 完成 | completed | [Task05](../../013/task-05-instrument-chat-kb.md:91) 记录 `kb.rerank`、故障隔离、322 passed 和真实 chat/KB 阶段事件（L93–116）。 | false | 只迁移已有实现及故障隔离验收。 |
| 06 原生 Dashboard + numeric score | 完成 | **partial** | Task 文件后续声称样本、7 项指标和配置已完成（[Task06](../../013/task-06-stats-native.md:84)–98）；但独立验收仍判“不通过/部分完成”，明确缺少已保存 Dashboard ID/截图/导出配置，且 Tech Lead 复核要求重新验收签字（[tester review](../../../reviews/013-stats-native-review.md:7)–10, 71–80, 82–113；[Tech Lead review](../../../reviews/013-task06-tech-review.md:8)–20, 105–128）。README 后续摘要称已补配置（[README](../../013/README.md:25)–32），但未找到独立复验关闭该签字/原生视图证据缺口的记录。 | false | 保留既有 fixture/指标证据；标记原生 UI 配置验收未闭环。若新需求仍要求可保存、可复现的 Langfuse 看板，先只补该验收证据，不重做 score/埋点。 |
| 07 Ollama Insights 视图 | spec 表：实施中，待构建与验收；README：完成 | completed（主模型代行验收） | [Task07](../../013/task-07-stats-custom-view.md:219)–242 记录依赖环境修复、5 项缺陷闭环、6 个前端测试文件/37 用例通过；结论明确为“通过（主模型代行，非独立 tester）”。Task08 也复述 Task01–07 完成（[Task08](../../013/task-08-review-retro.md:111)–114）。Spec 任务行 L192 和 README 早期进度 L31 未同步。 | false | 按现有代码/37 用例迁移为完成并保留“非独立验收”属性；不要再重做视图。 |
| 08 评审、验收、部署、提交、复盘 | spec 表：待执行；README/Task 文件：完成 | **partial** | [Task08](../../013/task-08-review-retro.md:107)–128 记录了部署、复盘和主模型代行验收，但同一记录明确“未做 git commit”（L116–118）、建议独立 tester 复验（L126–128）。完成清单仍包含稳定 commit（L76–105）；Spec 的产品使用步骤仍是占位，评审记录仍写待评审（[Spec 013](../../../specs/013-llm-observability-platform.md:165)–167, 195–201）。因此不能仅凭状态字段或 README 判整个收口门禁完成。 | false | 迁移业务验收/部署/复盘为已发生；把产品步骤、独立签字、可追溯稳定集成点和 Spec/README 状态对齐保留为收口缺口。不要重新实施 Task01–07。 |

Spec 013 的状态字段写 `已完成`，但 spec 内 Task07/08 与评审记录仍留旧状态，README 的 2026-09-03 进度段也称 Task08 未完成；Task 文件记录了后续收敛，但 Task06/08 的独立验收与提交证据不完全一致（[Spec 013](../../../specs/013-llm-observability-platform.md:3)–5, 192–201；[README](../../013/README.md:25)–32；[状态台账](../../../spec-status-changelog.md:137)–138）。本审计不回写或改变上述状态。

## Spec 014 — 知识库本地 Rerank

| Task | 原状态 | 事实判断 | 当前 main 证据 | 可领取 | 后续迁移建议 |
|---|---|---|---|---|---|
| 01 编写 spec | 完成 | completed | [Spec 014](../../../specs/014-kb-reranker.md:198)–208。 | false | 只迁移已完成记录。 |
| 02 运行时 Go/No-Go | 完成（Go） | completed | [Task02](../../014/task-02-validate-reranker-runtime.md:81)–96 记录中英文质量探针、稳定性、20 候选和资源测试通过。 | false | 沿用模型与运行时结论。 |
| 03 服务生命周期 | 完成 | completed | [Task03](../../014/task-03-reranker-service-lifecycle.md:63)–76 记录启停脚本、动态端口、幂等及部署集成验证通过。 | false | 不重新建服务生命周期。 |
| 04 Reranker 客户端 | 完成 | completed | [Task04](../../014/task-04-reranker-client.md:62)–75 记录客户端/协议边界测试通过。 | false | 沿用已有客户端和测试。 |
| 05 检索接入 | 完成 | completed | [Task05](../../014/task-05-integrate-retrieval-pipeline.md:60)–72 记录 269 passed、之后转完成。 | false | 沿用现有检索接入，不重复接线。 |
| 06 健康状态与前端 | 完成 | completed | [Task06](../../014/task-06-reranker-health-status.md:71)–85 记录状态显示和 115 passed 回归。 | false | 迁移现有状态契约。 |
| 07 测试与质量基准 | 完成 | completed | [Task07](../../014/task-07-reranker-tests-benchmark.md:57)–61 记录真实 Q8_0、MRR@5 从 0.225 升至 0.495、20 候选时延/RSS 与降级证据；[retro](../../../retro/2026-09-04-spec-014-reranker-retro.md:5)–9 汇总 351 passed。 | false | 保留冻结集/指标作为已验证基准，不复制基准任务。 |
| 08 集成 Spec013 观测 | 完成 | completed | [Task08](../../014/task-08-integrate-spec013-observability.md:62)–75 记录四种 Langfuse/Reranker 组合、成功/disabled/degraded trace 和 346 passed。最终验收矩阵记录完整四组合真实 KB ask 及恢复（[014 acceptance](../../../reviews/014-acceptance-review.md:202)–219）。 | false | 迁移四组合的实测结论。 |
| 09 评审、部署、复盘 | 完成 | completed | [Task09](../../014/task-09-review-deploy-retro.md:87)–109 记录阻塞修复、351 passed、签字/复盘/本地原子 commit；[Spec 014](../../../specs/014-kb-reranker.md:3)–5、198–208 与 [README](../../014/README.md:15)–25 均标完成。Tech Lead 签字由主会话代行，报告明确非独立评审（[014 acceptance](../../../reviews/014-acceptance-review.md:261)–280；[retro](../../../retro/2026-09-04-spec-014-reranker-retro.md:50)–53）。 | false | 迁移为完成并附“主会话代行、非独立”评审属性；除非另有新要求，不重跑整项。 |

## Spec 015 — 安全顶会论文检索与知识库导入

原范围与后续 USENIX 目录范围必须分开记录。当前 Spec015 明确为 `实施中`：USENIX-only 增量目录阶段已验收，但 ACM/IEEE 登录、自定义会议、A14 排序质量和 GUI/真实导入证据仍 deferred（[Spec 015](../../../specs/015-security-paper-discovery.md:3)–12）。下面 `13–17 completed` 只表示各自收窄后的 USENIX-only 子范围完成，不表示原始 A1–A15 全功能收口。

| Task | 原状态 | 事实判断 | 当前 main 证据 | 可领取 | 后续迁移建议 |
|---|---|---|---|---|---|
| 01 编写 spec | 完成 | completed | [Spec 015](../../../specs/015-security-paper-discovery.md:575)–578。 | false | 只迁移文档完成状态。 |
| 02 数据源与浏览器 Go/No-Go | 条件放行（内置会议；Venue Search blocked） | **partial** | 用户授权仅放行内置会议 publication search/OpenAlex；DBLP Venue Search 和自定义会议继续 blocked（[Task02](../../015/task-02-validate-baseline-and-sources.md:100)–109；[Spec 015](../../../specs/015-security-paper-discovery.md:625)–627）。Task06 后来安装 Playwright 1.52/Chromium 并恢复 health，但无合法账号，项目 profile 真实登录仍待验（[Task06](../../015/task-06-batch-import-and-login-resume.md:83)–97）。 | false | 只迁移内置会议/OpenAlex 条件放行证据。Venue Search 成功样本、自定义会议和受保护登录仍是未关闭缺口；不得把 Chrome 人工会话当成项目 profile 登录。 |
| 03 会议配置与论文召回 | 已完成（内置会议与 OpenAlex 收窄范围） | **partial（已完成收窄范围）** | 内置会议召回、OpenAlex、SQLite/API 最终验收 41 passed；Venue Search/custom conference blocked（[Task03](../../015/task-03-conference-registry-and-retrieval.md:6)–7, 70–82；[README](../../015/README.md:20)–23）。 | false | 已实现内置会议链路直接迁移；仅将自定义 Venue Search/会议创建作为未来缺口，不再重做内置会议。 |
| 04 语义排序与 Reranker | 待执行 | **unverified** | Task 文件仍为 `待执行` 且执行结果“待执行后填写”（[Task04](../../015/task-04-semantic-ranking-and-rerank.md:4), 59–66）；Task08 后续仍记缺 Task04 embedding/rerank 质量证据（[Task08](../../015/task-08-tests-ranking-and-security.md:78)–90）。 | false | 保留为明确未完成/不可领取的历史缺口；若重新启动，先核对目前其他 Spec 的实际排序接线与冻结标注集，作为新批准任务实施。 |
| 05 安全下载、命名和 KB 导入 | 已完成（单篇闭环） | completed（单篇；USENIX catalog 后续接线已实测） | Task05 记录 allowlist、补偿、单篇 API 和安全回归通过（[Task05](../../015/task-05-secure-download-and-kb-import.md:54)–78）。虽然 Task17 的 9/8 报告把真实公开 PDF 导入列为 deferred（[Task17](../../015/task-17-review-acceptance-deploy-retro.md:125)–131），随后 9/9 状态记录实测两篇 USENIX PDF 下载成功且批次 `25733b60` 两篇均完成落盘（[status changelog](../../../spec-status-changelog.md:202)–205）；9/10 Spec019 验收又实测新 USENIX PDF `HTTP 200/indexed`、文件落盘并可从 KB 列表读到（[019 acceptance](../../../reviews/019-acceptance-review.md:34)–52）。 | false | 已证实的公共 USENIX 单篇/批次导入接缝应作为完成证据复用；真实受保护站点登录和完整原始 UI 验收不由此推定完成。 |
| 06 批量导入与登录续传 | 实施中（离线安全复核通过；真实登录阻塞） | **partial** | SQLite 状态机、Playwright、ACM/IEEE parser、登录/resume API、212 定向/525 全量回归完成；当前路径下 Playwright health 可用。但记录明确真实 ACM/IEEE 登录续传仍需用户合法账号样本（[Task06](../../015/task-06-batch-import-and-login-resume.md:83)–97）；独立安全复核也明确真实登录未执行（[Task06 final review](../../../reviews/015-task06-acceptance-review-final-security-recheck.md:70)–79）。 | false | 迁移已完成的批次/浏览器/parser 离线能力；仅将用户授权账号下的真实登录、受保护 PDF 与续传验收保留为不可领取阻塞。 |
| 07 论文检索 Tab 与完整交互 | 实施中（离线通过；A3/真实环境阻塞） | **partial** | HTML/JS/CSS、API、Node/前端契约/511 全量回归证据存在；自定义会议受 Task02 阻塞，真实 GUI/窄屏和 ACM/IEEE 登录仍未验证（[Task07](../../015/task-07-paper-discovery-tab.md:60)–73；[final review](../../../reviews/015-task07-acceptance-review-final.md:50)–68）。后续 019 有实际 API 导入验收，但不等于原始 Task07 的 GUI 全旅程已验。 | false | 迁移离线 UI 与安全实现为已发生；保留自定义会议和用户可见 GUI/窄屏旅程缺口，避免重写 Tab。 |
| 08 测试、排序基准、安全回归 | 实施中（离线安全/回归通过；排序和真实环境阻塞） | **partial** | SSRF/PDF/错误处理/旧 KB fake 集成测试补齐，最终记 525 passed；Task 文件明确缺冻结排序集、nDCG/Recall、Task04 质量证据、真实 GUI/公开 PDF/ACM-IEEE 登录（[Task08](../../015/task-08-tests-ranking-and-security.md:78)–90）。Task17 USENIX-only QA 另有 650 passed，但范围明示不含 A14 排序（[Task17 acceptance](../../../reviews/015-task17-acceptance-usenix-only.md:1)–22）。 | false | 迁移安全矩阵/离线回归/USENIX-only QA 为完成证据；排序质量和原始宽范围的真实外部验收仍留作独立后续缺口。 |
| 09 评审、部署、复盘 | 实施中（离线回归与本地部署通过；外部验收阻塞） | **partial（Spec015 原范围）** | 原 Task09 要求公开导入、批量、ACM/IEEE 登录与 A1–A15 全项通过（[Task09](../../015/task-09-review-deploy-retro.md:8), 28–36, 55–66）。报告记录 Task04 rerank/nDCG、Venue Search/custom、GUI/窄屏、旧 KB 物理端到端和合法登录仍无证据（L80–91）。USENIX-only Task17 后续完成并通过独立范围 QA，但报告仍将 Spec015 总状态保持实施中（[Spec 015](../../../specs/015-security-paper-discovery.md:5)–7；[Task17](../../015/task-17-review-acceptance-deploy-retro.md:125)–138）。9/9 后续记录关闭了至少一条真实 USENIX→下载→索引链路，但没有取消上述宽范围缺口（[status changelog](../../../spec-status-changelog.md:202)–205；[019 acceptance](../../../reviews/019-acceptance-review.md:36)–52）。 | false | 不迁移为全范围完成；保留“USENIX 子范围已交付、Spec015 原范围未收口”的双层事实。公开 USENIX 导入记录应复用；后续只核验确实未覆盖的门禁。 |
| 10 论文发现限界上下文目录迁移 | 待确认 | **unverified** | Task 文件仍写待确认，执行结果待用户确认后填写，且明确未移动/修改业务代码（[Task10](../../015/task-10-paper-discovery-package-migration.md:4), 63–71）；Spec 的“架构重构（待确认）”仍说明现有代码分散在 `domain/` / `services/`（[Spec 015](../../../specs/015-security-paper-discovery.md:21)–63）。 | false | 不能领取旧 Task10。只有新授权后才作为路径/架构迁移任务复核现状；不得假设 `backend/app/paper_discovery/` 已成为唯一实现根。 |
| 11 USENIX accepted + arXiv 兜底 | 已完成 | completed（USENIX 范围） | [Task11](../../015/task-11-usenix-accepted-and-arxiv-fallback.md:105)–116 记录来源、严格匹配、迁移/安全、QA/Tech Lead 通过和 552 passed。 | false | 迁移为已完成 USENIX 来源能力；不外推为 ACM/IEEE 或自定义会议支持。 |
| 12 USENIX 双 Skill | 已完成（下载版/目录版） | completed（文档/协议） | [Task12](../../015/task-12-usenix-paper-skill.md:78)–90 记录下载版/目录版 Skill、CodeBuddy 薄适配器及静态/跨 IDE 验收。 | false | 只迁移协议与适配器存在证据；不把 Skill 文件等同于新业务流程实现。 |
| 13 全局目录协议与复用审计 | Spec 表：实施中约 60%；README/Task：完成 | completed | [Task13](../../015/task-13-catalog-contract-and-reuse-audit.md:136)–148 记录实现提交 `fe17e71`、审计通过、schema v2/迁移/仓储和 84 passed；[README](../../015/README.md:32) 标已完成。Spec 表 L589 是旧进度。 | false | 迁移为完成并带 commit/test 引用；不要再建 schema v2 或第二套 store。 |
| 14 USENIX 增量目录同步 | Spec/README：已完成；Task 文件仍有待执行占位 | completed（USENIX-only） | README 标增量同步和 `/accepted` 端点已完成（[README](../../015/README.md:33)）；Spec 顶部也明确 Task13/14 已落地、Task15–17 USENIX-only 已验收（[Spec 015](../../../specs/015-security-paper-discovery.md:5)–11）。后续台账记录 9/7 已完成及 slug 评审后续整改闭环（[status changelog](../../../spec-status-changelog.md:155), 64）。Task 文件 L136–144 的“待执行”是未回填旧占位，不能当未开发。 | false | 以当前 main 实现/README/状态台账/下游验收迁移为完成；若修文档只补事实，不重复写 parser/source。 |
| 15 LangGraph、目录 RAG、冻结结果 | spec 表：待执行；README/Task：已完成（USENIX-only） | completed（USENIX-only） | [Task15](../../015/task-15-langgraph-catalog-rag.md:145)–157 记录 9 节点图、独立 collection、冻结分页/恢复、105 定向与 650 全量通过；后端最终复审 PASS（[review](../../../reviews/015-task15-backend-review-final.md:8)–14）。README L34 与 Spec 顶部 L7、L11 为当前范围记录；Spec 表 L591 为旧状态。 | false | 仅迁移 USENIX-only 的异步目录/RAG 结果；不把 rerank 排序质量标注集缺口误记为 Task15 未做。 |
| 16 来源进度与十条分页 | spec 表：待执行；README/Task：已完成（USENIX-only） | completed（USENIX-only） | [Task16](../../015/task-16-search-progress-and-pagination.md:138)–150 记录异步创建/轮询、独立来源卡、10 条分页、旧路由删除及前端/API 定向测试通过；README L35、USENIX-only QA L14–18。Spec 表 L592 是旧状态。 | false | 迁移 UI/API 实现与验收；不要重新实现分页/来源卡。 |
| 17 复用审计、验收、部署、复盘 | spec 表：待执行；README/Task：已完成（USENIX-only） | completed（USENIX-only 阶段） | [Task17](../../015/task-17-review-acceptance-deploy-retro.md:125)–138 与 [QA review](../../../reviews/015-task17-acceptance-usenix-only.md:8)–22 证明 USENIX-only 通过：650 passed、同步 fixture、异步入口 202、部署/健康证据；明确列出 ACM/IEEE、自定义会议、A14、GUI/窄屏 deferred。README L36 和 Spec 顶部 L5–11 与之吻合；Spec 表 L593 是旧状态。后续真实 USENIX PDF/KB 导入至少已在 9/9–9/10 主记录补证（Task05 行）。 | false | 迁移为“USENIX-only 阶段已收口”，不要据此把 Spec015 改为全范围完成；补充延期项目时先核对后续 main/Spec019+证据。 |

## Spec015 跨期证据边界

- **ACM/IEEE**：解析器、浏览器管理、API 和离线安全测试已经存在；当前可证明浏览器依赖/health 修复与站点导航尝试，但无用户合法账号下项目 Playwright profile 的登录续传和受保护 PDF 导入。Task06 仍明确 `实施中`，不能因外站 Chrome 登录观察、parser 单测或 USENIX 导入而标完成（[Task06](../../015/task-06-batch-import-and-login-resume.md:83)–97；[final security review](../../../reviews/015-task06-acceptance-review-final-security-recheck.md:70)–79）。
- **自定义会议 / DBLP Venue Search**：Task02 条件放行和 Task03 最终测试均明确 blocked；后续 Spec032 有 IEEE S&P/CCS/NDSS 固定会议来源的实现/测试，但那不是用户添加任意自定义会议，也未关闭 Spec015 的 Venue Search 门禁（[Task02](../../015/task-02-validate-baseline-and-sources.md:100)–109；[Task03](../../015/task-03-conference-registry-and-retrieval.md:70)–82）。
- **排序 benchmark**：Spec015 Task04 仍待执行；Task08 缺冻结查询标注、nDCG/Recall 与 rerank 质量证据。USENIX-only 目录 QA 有 650 passed，不包含排序质量判定（[Task04](../../015/task-04-semantic-ranking-and-rerank.md:4), 59–66；[Task08](../../015/task-08-tests-ranking-and-security.md:78)–90；[USENIX-only QA](../../../reviews/015-task17-acceptance-usenix-only.md:5), 20–22）。不要把 Spec014 自身的 reranker benchmark 冒充论文排序质量 benchmark。
- **端到端**：Task17 USENIX-only QA 当时把公开 PDF 导入列为 deferred；之后 main 的 9/9 状态记录与 9/10 Spec019 验收确有两篇/单篇公开 USENIX PDF 下载并成功索引、KB 文件可见，故“公开 USENIX PDF 从 API 到索引完全没跑过”已被新证据推翻（[status changelog](../../../spec-status-changelog.md:202)–205；[019 acceptance](../../../reviews/019-acceptance-review.md:36)–52）。Task17 部署记录还显示 Qdrant 数据目录被另一实例占用，目录检索按降级语义运行（[Task17](../../015/task-17-review-acceptance-deploy-retro.md:131)），所以真实“来源同步→目录 RAG→UI 检索→知识库导入”的完整线上链路仍未一次性证明。公开 USENIX API 导入/索引已补证，但这不证明 ACM/IEEE 真实登录、完整 GUI/窄屏旅程、每个批次/失败恢复场景或 Spec015 原始 A1–A15 全部通过；Spec015 状态仍为 `实施中`。

## 本审计读取的输入路径

**指定主输入**

- `docs/sdd/specs/013-llm-observability-platform.md`
- `docs/sdd/specs/014-kb-reranker.md`
- `docs/sdd/specs/015-security-paper-discovery.md`
- `docs/sdd/plans/013/README.md`
- `docs/sdd/plans/014/README.md`
- `docs/sdd/plans/015/README.md`

**Task 计划与执行记录**

- `docs/sdd/plans/013/task-02-deploy-langfuse.md`
- `docs/sdd/plans/013/task-03-upgrade-python.md`
- `docs/sdd/plans/013/task-04-ollama-direct.md`
- `docs/sdd/plans/013/task-05-instrument-chat-kb.md`
- `docs/sdd/plans/013/task-06-stats-native.md`
- `docs/sdd/plans/013/task-07-stats-custom-view.md`
- `docs/sdd/plans/013/task-08-review-retro.md`
- `docs/sdd/plans/014/task-02-validate-reranker-runtime.md`
- `docs/sdd/plans/014/task-03-reranker-service-lifecycle.md`
- `docs/sdd/plans/014/task-04-reranker-client.md`
- `docs/sdd/plans/014/task-05-integrate-retrieval-pipeline.md`
- `docs/sdd/plans/014/task-06-reranker-health-status.md`
- `docs/sdd/plans/014/task-07-reranker-tests-benchmark.md`
- `docs/sdd/plans/014/task-08-integrate-spec013-observability.md`
- `docs/sdd/plans/014/task-09-review-deploy-retro.md`
- `docs/sdd/plans/015/task-02-validate-baseline-and-sources.md`
- `docs/sdd/plans/015/task-03-conference-registry-and-retrieval.md`
- `docs/sdd/plans/015/task-04-semantic-ranking-and-rerank.md`
- `docs/sdd/plans/015/task-05-secure-download-and-kb-import.md`
- `docs/sdd/plans/015/task-06-batch-import-and-login-resume.md`
- `docs/sdd/plans/015/task-07-paper-discovery-tab.md`
- `docs/sdd/plans/015/task-08-tests-ranking-and-security.md`
- `docs/sdd/plans/015/task-09-review-deploy-retro.md`
- `docs/sdd/plans/015/task-10-paper-discovery-package-migration.md`
- `docs/sdd/plans/015/task-11-usenix-accepted-and-arxiv-fallback.md`
- `docs/sdd/plans/015/task-12-usenix-paper-skill.md`
- `docs/sdd/plans/015/task-13-catalog-contract-and-reuse-audit.md`
- `docs/sdd/plans/015/task-14-usenix-incremental-catalog.md`
- `docs/sdd/plans/015/task-15-langgraph-catalog-rag.md`
- `docs/sdd/plans/015/task-16-search-progress-and-pagination.md`
- `docs/sdd/plans/015/task-17-review-acceptance-deploy-retro.md`

**核对评审、复盘与状态证据**

- `docs/sdd/reviews/013-requirement-review.md`
- `docs/sdd/reviews/013-tech-review.md`
- `docs/sdd/reviews/013-stats-native-review.md`
- `docs/sdd/reviews/013-task06-tech-review.md`
- `docs/sdd/reviews/013-task07-architecture-review.md`
- `docs/sdd/reviews/013-task07-implementation-review.md`
- `docs/sdd/reviews/013-task07-acceptance-review.md`
- `docs/sdd/reviews/014-requirement-review.md`
- `docs/sdd/reviews/014-tech-review.md`
- `docs/sdd/reviews/014-acceptance-review.md`
- `docs/sdd/reviews/014-reranker-benchmark.md`
- `docs/sdd/retro/2026-09-04-spec-014-reranker-retro.md`
- `docs/sdd/reviews/015-task02-baseline-review.md`
- `docs/sdd/reviews/015-task02-tech-review.md`
- `docs/sdd/reviews/015-task03-acceptance-review.md`
- `docs/sdd/reviews/015-task03-tech-review-final-signoff2.md`
- `docs/sdd/reviews/015-task05-acceptance-review-final.md`
- `docs/sdd/reviews/015-task06-acceptance-review-final-security-recheck.md`
- `docs/sdd/reviews/015-task07-acceptance-review-final.md`
- `docs/sdd/reviews/015-task08-acceptance-review.md`
- `docs/sdd/reviews/015-task08-quality-recheck.md`
- `docs/sdd/reviews/015-catalog-requirement-review.md`
- `docs/sdd/reviews/015-catalog-tech-review.md`
- `docs/sdd/reviews/015-task13-reuse-audit.md`
- `docs/sdd/reviews/015-backend-review.md`
- `docs/sdd/reviews/015-task14-usenix-parser.md`
- `docs/sdd/reviews/015-task15-backend-review-final.md`
- `docs/sdd/reviews/015-task17-acceptance-usenix-only.md`
- `docs/sdd/reviews/019-acceptance-review.md`
- `docs/sdd/spec-status-changelog.md`
