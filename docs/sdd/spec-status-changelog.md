# Spec 状态变更记录

本文件记录所有 spec 的状态变化。每条含：spec 编号与标题、变更前 → 变更后状态、变更时间，以及一两句话说明本次变动的原因或内容。

> **收口纪律**（见 `docs/sdd/SDD-GATE-CHECKLIST.md` §3）：状态流转须与本文件同步；
> 转 `已完成` 前必须满足——三份评审有真实结论、验收签字栏已填、本文件已追加、变更日志补齐、引用路径真实存在、复盘已落盘。

## 2026-09-08

- **017 后端限界上下文彻底重构** ｜ 已完成 → 实施中 ｜ Luna xhigh 独立审计发现旧 `agents/article_agent.py`、`core/config.py`、`api/routes.py` 兼容转发和未接线 `PaperImportPort` 仍不符合原 Spec 的“旧结构清零/跨域 port 接线”要求；保留历史验收证据，退回修复与重新验收。
- **017 后端限界上下文彻底重构** ｜ 实施中 → 已完成 ｜ 完成旧 Agent/config/routes 清理、PaperImportPort factory 接线与回归；定向 `131 passed`，全量 `653 passed / 38 subtests`，修复轮验收见 `017-remediation-acceptance-review.md`。
- **018 知识文档切片检查器与双向原文定位** ｜ 新建 → 待确认 ｜ 用户要求在个人知识库新增切片检查 Tab；经 Grill with Docs 访谈确认 PDF + Markdown、文本块级双向映射、单版本切换、只读检查、旧文档零 embedding 自动补建和窄屏切换。Spec 与 Task 02–07 已落盘；用户产品方向确认已收到，仍待需求/技术评审门禁通过后转已确认。
- **018 知识文档切片检查器与双向原文定位** ｜ 待确认 → 已确认 ｜ 需求评审修订轮与技术复审最终通过；用户明确要求开始 Spec018。已补齐 provenance、迁移、Markdown、manifest/API、安全依赖和 A/B/C/D 交接门禁。
- **018 知识文档切片检查器与双向原文定位** ｜ 已确认 → 实施中 ｜ 启动 Task02 来源锚点 Go/No-Go；当前只允许固定样本和只读可行性验证，No-Go 自动停止后续任务，不修改业务代码。
- **015 Task15–17 继续开发** ｜ Task15/16 待执行 → 实施中 ｜ 用户明确要求接续已有部分实现并开发 Task15–17；已核对 Task13/14 落盘证据，分别分派 backend-dev 与 frontend-dev 实现异步目录检索、LangGraph/RAG、来源进度和分页。模型仅本轮临时使用 Luna high，不写入长期规则；Task17 将在实现完成后执行验收与部署。
- **015 USENIX-only 目录检索阶段** ｜ Task15/16 实施中、Task17 待执行 → Task15/16/17 已完成（USENIX-only） ｜ 完成 LangGraph/RAG、双源进度、固定分页、增量缓存、并发租约恢复、权威合并、失败释放和旧同步路由删除；QA 与后端复审通过，Spec 总状态保持实施中，ACM/IEEE、自定义会议、排序质量与真实 PDF/GUI 证据明确 deferred。
- **015 USENIX-only 本地部署** ｜ 实现完成 → 已部署验证 ｜ 8000 被沙箱外进程占用且无法停止，改用 8001 启动本版本；首页与 `/api/health` 返回 200，最小 USENIX 异步检索入口返回 202。Qdrant 并发占用按降级语义记录，未宣称 RAG 在线健康。

## 2026-09-06

- **017 后端限界上下文彻底重构** ｜ 待确认（评审打回） → 待确认（已修订，待复审） ｜ 需求评审与技术评审结论均为「打回」；已按需求 4 项必改与技术 7 项必改修订 Spec017 与 Task02/03/04/06：补齐对外契约基线（35 个端点、4 组公开别名、三类 SSE、两类错误体）、环境与数据兼容性矩阵（含配置四级优先级与 read-modify-write 要求）、旧目录逐文件迁移分类与四类 import 检查范围、跨上下文端口契约、静态边界检查规则，并补齐产品使用步骤与 13 项验收场景；执行顺序改为 02→03→05→04→06→07→08。状态仍为待确认，需复审通过后才进入用户确认。
- **015 USENIX accepted-papers 修复补丁** ｜ 评审结论 Warning → 整改闭环 ｜ 补齐 `_listing_for` 与显式 cycle 分支回归测试，并实现受控年份下界 `USENIX_MIN_YEAR = 2022`，消除默认窗口内 2021 年的常驻 `USENIX_UNAVAILABLE` 告警；全量回归 626 passed / 0 failed，提交 `8a26e29`。
- **017 后端限界上下文彻底重构** ｜ 待确认（复审通过） → **已确认** ｜ 用户明确授权开发顺序：先 017 → 全量回归 → 再 015。复审已通过（`docs/sdd/reviews/017-rereview.md`），按 `02→03→05→04→06→07→08` 执行，子 agent 与模型沿用 `AGENTS.md` 角色分配表。
- **017 后端限界上下文彻底重构** ｜ 待确认（已修订，待复审） → 待确认（复审通过，待用户确认） ｜ architect 复审（`docs/sdd/reviews/017-rereview.md`）判定需求 4 项与技术 7 项必改**全部闭环**（R3 原「部分闭环」已修正：`/health` 在 Ollama 不可达时恒返回 200 且 `models: []`，不产生错误体，见 `routes.py:280-291`）；抽查 4 项代码事实与 spec 描述一致。状态仍为 `待确认`，等待用户明确确认后进入实现。

## 2026-09-05

- **015 安全顶会论文检索与知识库导入** ｜ 待确认 → 已确认 ｜ Task13–17 需求/技术复审已落盘（结论通过，见 `docs/sdd/reviews/015-catalog-requirement-review.md` / `015-catalog-tech-review.md`）；用户明确"调用子 agent 进行开发"，授权实现 Task14–17；Task14 由 junior-dev（qwen3.8:27b-mlx）启动。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 待确认 ｜ 用户将当前检索调整为 USENIX 官网优先、DBLP 辅助、SQLite 增量目录、LangGraph 并行工作流、独立目录 RAG、来源进度卡片和每页 10 篇冻结结果。已完整更新 Spec015 并新增 Task13–17；按用户要求本轮只落盘文档，暂停代码实现，等待后续安排。
- **015 Task13–17 增量目录流程** ｜ 新建 → 待执行 ｜ 已把现有代码复用清单固化为实现硬约束，写明 schema v2、接口、工作流节点、缓存/租约/恢复、固定样本、完整子 Agent Prompt、返回字段、评审验收和回滚；需求/技术复审与用户再次确认前不得执行。
- **015 Task12 USENIX Skill** ｜ 单一混合版 → 下载版 + 目录元数据检索版 ｜ 为避免搜索阶段误触发 PDF 探测，拆分 `.agents/skills/usenix-accepted-papers`（下载/验证/导入）与 `.agents/skills/usenix-paper-catalog-search`（目录/增量/LangGraph/RAG），并让 Task13–17 全部指向目录版；两个 CodeBuddy 适配器同步落盘。
- **017 后端限界上下文彻底重构** ｜ 新建 → 待确认 ｜ 用户要求彻底整理整个后端：按论文发现、知识库、文章助手、聊天和平台能力重组；明确不保留旧内部 import 兼容层，对外 HTTP/JSON/环境变量与数据位置保持不变。已建立 Spec017 与 Task02–08，等待评审与确认门禁。
- **015 Task06 浏览器运行时依赖** ｜ 环境阻塞 → 条件解除 ｜ 因项目目录由 `PyCharmMiscProject` 改名为 `ResearchAgent`，`.venv` 脚本指向旧绝对路径；已修复 Python 3.11 虚拟环境，安装并锁定 Playwright 1.52.0 与对应 Chromium，运行时浏览器健康接口恢复 `available=true`。真实 ACM/IEEE 登录仍需用户合法账号参与。

## 2026-09-03

- **016 可移植 Task 账本与自动执行协议** ｜ 新建 → 待确认 ｜ 为跨 Codex、CodeBuddy 和其他 Agent IDE 的研发交接建立“Git 跟踪 Markdown 为长期事实源、SQLite 为可重建运行层”的流程；Task 将包含机器元数据、完整子 Agent Prompt、统一结果协议、执行轨迹和指标。已按 spec-013 格式建立 spec 与 `docs/sdd/plans/016/` Task 02–09；当前只落盘文档，不执行实现，等待用户确认。
- **015 安全顶会论文检索与知识库导入** ｜ 新建 → 待确认 ｜ 新增独立论文检索 Tab 的规划：默认检索 CCS、USENIX Security、IEEE S&P、NDSS 最近五个完整年份，支持搜索添加会议、语义排序、单篇/批量实际下载并按“年份-会议-标题”命名后导入知识库；ACM Digital Library 与 IEEE Xplore 采用项目内 Playwright 完成合法登录续传。已按 spec-014 格式建立 spec 与 `docs/sdd/plans/015/` 任务 02–09；当前只落盘文档，不执行任务，且必须等待 spec-013/014 形成稳定基线。

## 2026-09-02

- **014 知识库本地 Rerank 重排** ｜ 新建 → 待确认 ｜ 为个人知识库增加本地 Qwen3-Reranker 批量重排；现有 Ollama 包实测不适合专用 rerank，计划改用 llama.cpp `/v1/rerank` 与兼容 Q8_0 模型。已按 spec-013 格式建立完整 spec，并在 `docs/sdd/plans/014/` 拆分任务 02–09；当前仅文档落盘，等待用户确认。
- **014 知识库本地 Rerank 重排** ｜ 待确认 → 已确认 ｜ 用户授权“当前未提交代码能运行则进行 spec-014”。已先创建 `/tmp` 安全快照并在不回滚、不 stash、不清理工作树的前提下验证：FastAPI 首页/health/KB health、Langfuse 正常，全量测试 `253 passed`；需求与技术评审均通过（附意见），条件满足，进入实施门禁。
- **014 知识库本地 Rerank 重排** ｜ 已确认 → 实施中 ｜ 已在隔离 worktree 完成 Task 02 的兼容模型与排序质量 Go/No-Go，并继续实现本地 reranker 生命周期、客户端、检索和健康状态；等待与 Spec 013 的观测整合和最终验收。
- **012 知识库召回质量与切分 v2** ｜ 状态不变（已完成） ｜ **交付后缺陷修复**（同功能范围，不新建编号）：用户反馈论文卡片「标题展示不完全、重建/删除按钮看不到」。根因是纯前端布局——标题 `nowrap+ellipsis` 被截断；卡片因 spec-012 新增双版本徽章与进度条而增高，在固定高度侧栏的滚动区里把 `actions` 裁掉。修复：标题独占一行完整换行、meta 独立成行、侧栏 320→360px；`actions` 移入徽章行右对齐、进度条独占一行，单卡高度 110px→约 80px；按钮补边框。静态资源 `?v=13`，全量回归 `253 passed`。复盘见 `docs/sdd/retro/2026-09-02-kb-card-layout-retro.md`（教训：固定高度容器内新增内容须核算容量；DOM 契约校验需升级为可见性校验）。

## 2026-09-01

- **012 知识库召回质量与切分 v2** ｜ 新建 → 已完成 ｜ 验收通过 + 开发主管签字（`tech-lead` 子代理，27B，已成功；任务收窄后 27B 可用）。三项需求全部实现：参考文献入库但默认不召回（仅自动意图识别）、PDF 排版噪声清洗（断词合并 + 软换行转空格）、切分 v2（规则预筛 + `qwen3.8-27b-q4` 结构分析 + 固定上限，异步带百分比进度、提问时可选版本）。全量回归 `253 passed`（新增 `test_kb_normalize.py`/`test_kb_chunkers.py`/`test_kb_tasks.py`）。验收中发现并修复 3 项：R1 显存竞争未落实、跨页引用未显示 `p.3-4`、旧记录状态误标 failed；另补做旧索引点迁移（345 点补齐 `chunker` 字段）。前端 `?v=12`。
- **子代理可用性（跨 spec 流程风险）** ｜ 记录 ｜ `junior-dev`（27B 量化）与 `tester`（9b）在本次长流程任务中均中途失效：前者两次分派零产出且超时后仍在后台写文件覆盖他人代码，后者 18 分钟仅跑完测试即中断。编码与验收最终由主会话承担。详见 `docs/sdd/retro/2026-09-01-subagent-model-naming.md`。

## 2026-08-30

- **011 本地个人论文知识库（RAG）** ｜ 新建 → 实施中 ｜ 实现已完成（后端 kb 服务包 + `/api/kb/*` + 知识库前端视图 `?v=6`；150 用例全绿、覆盖率 90%；端到端实测上传 20 页 PDF→125 片段→混合检索→带引用生成→删除全链路通过），验收报告结论通过但**开发主管签字栏为空**，按 `AGENTS.md` 硬规则第 6 条**保持 `实施中`，不转 `已完成`**。同日做流程复盘：本轮存在需求评审缺失、`pm`/`junior-dev`/`tester` 未分派、技术/验收评审由主模型代行等流程退化，已新建 `SDD-GATE-CHECKLIST.md`、修订模板与 `AGENTS.md`、回填 007/008/010 共 6 处「结论：/」占位；复盘见 `docs/sdd/retro/2026-08-30-spec-011-process-retro.md`。
- **007 / 008 / 010** ｜ 状态不变（已完成） ｜ 回填各自 spec「评审记录」中残留的「结论：/」占位（共 6 处），统一为评审文档中的真实结论；纯台账校正，无代码改动。

## 2026-08-29

- **010 后端测试覆盖率提升至 80%** ｜ 新建 → 已完成 ｜ 起因：spec-008/009 的 PR 合并门禁中"覆盖率 ≥80%"未通过（当前 69%）。经用户拍板选「B 先补测试」，另开 spec-010 补后端测试；实测覆盖 routes.py（49%→94%）、graphs/chat.py（25%→100%），TOTAL 69%→87%，85 passed，零业务改动，离线可重复（已停 Ollama 验证）。验收通过。

## 2026-08-28

- **008 模型别名展示与设置** ｜ 已完成 → 实施中 ｜ 用户反馈 v1"列表外统一编辑弹层"不符合预期，要求别名**在模型自己的卡片内**修改。spec-008 交互重做为卡片内行内编辑（✎ 图标触发、原地变输入框、Enter/失焦保存、Esc 取消），展示改为"别名大标题 + 真实名灰色小字（仅设别名时显示）"；移除顶部"编辑别名"按钮与"重置全部"批量入口。属同一功能范围变更，不新建编号。
- **008 模型别名展示与设置** ｜ 实施中 → 已完成 ｜ 行内编辑实现完成，首次以**新建的 tester 子代理（带 tools + sdd-acceptance skill + 本地模型 local-qwen38-27b-tools）**执行验收评审，A1–A9 全部通过；子代理发现的 R1（隐私模式未降级内存 Map，§5 强制约束）、R2（✎ 默认不可见）、R3（innerHTML 清空）三项风险已由架构师修复并复验，静态资源升 `?v=4`，服务在 8000 端口运行时验证通过。本地模型 function call 实测结论见 `docs/sdd/TOOLCALL_BENCHMARK.md`。

## 2026-08-27

- **006 修复左侧"模型库"Tab 点击无反应** ｜ 已确认 → 实施中 ｜ 子模型 oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU 产出草稿（为占位骨架，未直接采用）；架构师基于真实文件做最小增量实现：index.html 加 data-view/nav 与 #models-view 容器，app.js 加 showView/renderModelList（用 hidden toggle 防抖、不重建 #chat）。JS 语法校验通过，无 lint 错误。待验收评审。

## 2026-08-26

- **003 集成 download-paper Skill** ｜ 已确认 → 已完成 ｜ 补齐 `use_skill` 记录与 `skill` 状态（version/路径）读取，新增 `build_download_plan` 单测；本地服务验证公开 PDF 计划生成通过。
- **004 完全由 download-paper Skill 主导下载** ｜ 待确认 → 已完成 ｜ skill 主导下载编排与后端执行，放宽 003 约束允许 Cookie/浏览器/科研通；保留 Crossref/OpenAlex 发现链路；新增 `decide_download_method`/`fetch_cookies_via_opencli`/`download_under_skill`/`build_skill_plan`。
- **005 前端候选展示限制与 Skill 选取提示** ｜ 待确认 → 已完成 ｜ 后端候选过滤为 confidence>0.5 且 ≤3、intent 事件对 download_paper 携带 skill；前端在意图识别后显示灰色"已选取 download_paper 技能"提示。
- **001 文章检索与下载 Agent** ｜ 已完成（意图识别缺陷，Errata 待确认） → 已完成（意图识别修订 Errata 已实施） ｜ 19:37 确认；20:30 实施完成 ｜ 意图识别由脆弱的关键词匹配改为大模型判断（`classify_intent` LLM 路径 + `qwen3.5:9b`，强下载词短路跳过模型），`chat` 作为兜底分支，移除 `unsupported` 路由；修复"生成一个300字的小故事"被误判为"无法识别"的问题，已在运行时经 `/api/agent/run` 验证 chat 兜底与 download_paper+skill。
| 2026-09-03 | Spec 013 本地 LLM 调用观测与性能评估平台 | 待确认 → 已确认 | 用户明确要求修复阻塞并继续后续开发；MinIO/OTLP 上报阻塞已定位，采用 v4 events_only 验收口径。 |
| 2026-09-03 | Spec 013 本地 LLM 调用观测与性能评估平台 | 实施中 → 实施中 | Task 07 继续推进：补齐全量聚合、model/route/cold-hot 维度、chain_type 生产字段和默认折叠详情脱敏；前端依赖下的类型、组件测试和验收仍待执行。 |

## 2026-09-04

- **015 安全顶会论文检索与知识库导入** ｜ 待确认 → 已确认 ｜ 用户明确要求“spec014 已由其他 Agent 收尾后继续开发 spec015”；当前 `main@c17c7f4` 已包含 Spec014 收口提交，开始执行 Task02 Go/No-Go。
- **015 安全顶会论文检索与知识库导入** ｜ 已确认 → 实施中 ｜ 创建并切换至 `feature/spec-015-security-paper-discovery`，启动 tester 执行 Task02 基线、数据源、Reranker 与 Playwright 验证；业务代码暂不修改。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中 ｜ 用户授权跳过 Spec013/014 基线核对与 Reranker 判断，Task02 收窄为 DBLP/OpenAlex 数据源、降级策略与 Playwright 桥接验证；跳过项记录为 deferred，不阻塞后续。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中 ｜ Task02 tester/tech-lead 条件放行内置会议 publication search 与 OpenAlex 补全；DBLP Venue Search 因 429/503 无成功样本保持 blocked，Task03 收窄启动内置会议与 OpenAlex 实现。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中 ｜ Task03 内置会议召回、OpenAlex 补全、SQLite 持久化和搜索 API 已完成并通过最终验收/技术签核（41 个定向测试通过）；Venue Search/custom conference 保持 blocked，导入 FK/TTL 移交 Task05。
- **015 Task05 安全下载、规范命名与知识库导入** ｜ 实施中 → 已完成 ｜ 固定服务端 allowlist、失败补偿、DBLP key 和 Content-Type 安全修复通过 Tech Lead 复核与 tester 验收；定向回归 150 passed，修复项精确回归 11 passed，并发幂等 10/10 轮，批量/登录续传移交 Task06。
- **015 Task06 批量任务与登录续传** ｜ 待执行 → 实施中 ｜ Task05 收口后启动批次/条目 SQLite 状态机实现，先建立可条件迁移、可租约恢复的持久化基础。
- **015 Task06 批量状态机切片** ｜ 实施中 → 实施中 ｜ 批次/条目持久化、批量编排、登录项隔离、租约恢复和并发幂等通过 Tech Lead/tester 最终切片复核；指定测试连续 3 次均 22 passed，继续进入浏览器与站点解析切片。
- **015 Task06 浏览器管理器切片** ｜ 实施中 → 实施中 ｜ headed persistent profile、单 profile/站点锁、ACM/IEEE exact origin allowlist、敏感产物禁用和健康契约完成；10 项 fake Playwright 测试通过，继续实现 ACM/IEEE 解析与登录续传 API。
- **015 Task06 ACM/IEEE 解析切片** ｜ 实施中 → 实施中 ｜ ACM 解析 7 passed、IEEE 解析 10 passed；均拒绝非受控 origin、认证参数和 Cookie/Authorization，登录/resume API 继续实现。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中 ｜ Task05 已启动：安全 URL 校验切片完成并通过 6 项安全边界测试，开始规范命名与论文身份去重；实际下载和知识库导入尚未开始。
- **015 安全顶会论文检索与知识库导入** ｜ 实施中 → 实施中 ｜ Task05 规范命名与论文身份去重已完成，开始实际 HTTP 安全下载适配；知识库导入、批量任务和登录续传仍待执行。
- **014 知识库本地 Rerank 重排** ｜ 实施中 → 实施中 ｜ 收口验收补充了四组合运行对账、真实成功/降级 `kb.rerank` 事件、`--ubatch-size 1024` 长输入修复和禁用组合真实问答尝试；tester 仍判定不通过，tech-lead 尚不可签字，故保持实施中。
- **014 知识库本地 Rerank 重排** ｜ 实施中 → 实施中 ｜ 定位收口 Bug：`/api/kb/ask` 未关闭回答模型 thinking，导致 qwen3.5 真实 SSE 长时间无 `done`；已补入 Spec014 的复现、根因和修复验收条件，进入窄范围代码修复。
- **013 本地 LLM 调用观测与性能评估平台** ｜ 实施中 → 已完成 ｜ Task 07 前端依赖与环境阻塞修复（补齐 lockfile + 离线安装 + .env），前端 37 用例全绿；5 项实质缺陷（散点丢点误判、脱敏覆盖、聚合守卫、截断提示、router 测试）闭环；C8 埋点 safe_call 包裹完成。验收由主模型代行（非独立评审）。详见 `docs/sdd/plans/013/task-07-stats-custom-view.md` 修复轮次执行结果与 `docs/sdd/reviews/013-task07-acceptance-review.md` 复核结论。
- **013 Task 07 验收** ｜ 不通过 → 通过（代行） ｜ 见上。
- **014 知识库本地 Rerank 重排** ｜ 实施中 → 实施中 ｜ 修复 `8c1c3ae`（KB ask 显式 `think=False`、LangChain `reasoning=False`）后，四组合真实 KB ask 均以完整 SSE `done` 收口，tester 最终判定通过；仍缺 tech-lead 签字与复盘，故暂不转完成。
- **014 知识库本地 Rerank 重排** ｜ 实施中 → 已完成 ｜ 发现并修复 `8c1c3ae` 引入的回归：`create_chat_model` 默认 `reasoning=True`，使所有仅传模型名的调用方（`article_agent`、`download_paper_skill`、`kb/retrieve.py`、langchain 聊天链路）被强制下发 `think=true`；`6daa498` 将默认值改回 `None` 并补 2 条契约测试，全量 `351 passed`。以 `deepseek-coder-v2:16b` 复测：KB ask HTTP 200 且 SSE 完整到 `done`（259 token、0 error），普通聊天同样完整收口，关键阻塞第 2 项（citations 后 HTTP 400）解除。Task 08/09 全部完成，tech-lead 签字已填（主会话代行，非独立评审，已在验收报告与复盘中标注），复盘落盘 `docs/sdd/retro/2026-09-04-spec-014-reranker-retro.md`。
- **014 Task 08 / Task 09** ｜ 部分完成 / 阻塞 → 完成 ｜ 见上。
- **015 Task06 真实登录验收** ｜ 实施中 → 实施中 ｜ 最新离线安全复核通过（Tech Lead/tester；定向 212、全量 502），但当前虚拟环境未安装 Playwright 且无合法 ACM/IEEE 账号样本，真实 headed 登录续传暂保持环境阻塞；继续推进不依赖真实账号的 Task07。
- **015 Task07 论文检索 Tab** ｜ 实施中 → 实施中 ｜ HTML/JS/CSS、会议搜索 API、开关竞态、稳定去重排序与批次隔离已完成；Tech Lead/QA 离线复核通过。A3 自定义会议仍受 DBLP Venue Search 前置阻塞，真实 GUI/窄屏和 ACM/IEEE 登录需受控环境，继续推进 Task08。
- **015 Task08 测试与安全回归** ｜ 待执行 → 实施中 ｜ QA 盘点完成；已补齐 SSRF/PDF 安全矩阵、加密 PDF 拒绝和回归稳定性，当前全量 521 passed。冻结排序集/nDCG、Task04 质量证据及真实 GUI/公开 PDF/ACM-IEEE 登录仍待受控环境。
- **015 Task09 收口与部署** ｜ 待执行 → 实施中 ｜ 本地服务在受控权限下启动并验证首页/健康/会议接口成功，Reranker 按既定策略降级；全量回归通过。外部数据源、自定义会议、真实 GUI/登录和排序质量证据仍阻塞，等待 QA/Tech Lead 收口报告。
- **015 Task09 收口复核** ｜ 实施中 → 实施中 ｜ Tech Lead 与 QA 报告已落盘，离线回归和受控部署证据通过；A3/A4/A10/A11/A14、真实 GUI/公开 PDF/旧 KB 端到端仍无可复核证据，Spec015 保持实施中并完成阶段复盘。
- **015 Task08 旧 KB 兼容补测** ｜ 实施中 → 实施中 ｜ 新增真实旧 JSON/PDF/FakeQdrant 集成测试，覆盖列表、检索、重建、删除及异常隔离；全量回归升至 525 passed，排序质量与真实外部证据仍阻塞。
- **015 论文发现目录架构变更** ｜ 实施中 → 待确认 ｜ 用户指出论文相关实现散落在 `domain/` 与 `services/`；已提出统一迁移到 `backend/app/paper_discovery/` 的限界上下文方案，暂停代码移动和后续实现，等待确认。
- **015 USENIX accepted papers 第二来源** ｜ 待确认 → 待确认 ｜ 用户要求不新建 Spec，将 USENIX Security accepted-papers 官网检索、USENIX PDF/prepublication PDF 和 arXiv 严格匹配兜底纳入 Spec015；已完成官方页面/API 调研并新增 Task11–12，等待用户确认补充范围。
- **015 USENIX accepted papers 第二来源** ｜ 待确认 → 实施中 ｜ 用户确认按补充后的 Spec015 执行；Task11/12 开始实现，主 Agent 与子 Agent 临时使用 gpt-5.6-luna high。
- **015 Task11 USENIX accepted + arXiv** ｜ 待执行 → 已完成 ｜ 来源解析、严格匹配、缓存/节流、PDF 安全探测、候选字段/SQLite、搜索/API 接线和跨来源去重均通过 Tech Lead 最终复评与 QA 验收；全仓回归 552 passed。
- **015 Task12 项目级 USENIX Skill** ｜ 待执行 → 已完成 ｜ 创建 `.agents/skills/usenix-accepted-papers/SKILL.md`、CodeBuddy 适配器，并将适用角色明确为 ResearchAgent 主 Agent、项目 Agent、PM、Tech Lead、QA、调度器和执行 Agent；静态与跨 IDE 验收通过。
- **015 Task12 Skill 适用范围澄清** ｜ 已完成 → 已完成 ｜ 用户明确“项目的 agent”指 ResearchAgent 本身；已在 Skill 与 `AGENTS.md` 中固定主 Agent/项目级 Agent 的触发和执行协议，保持本次临时 Luna high 模型选择不进入长期模型规则。
- **015 Task13 全局目录协议与复用审计** ｜ 待执行 → 实施中（约 60%）｜ 2026-09-07 收口回填：`search_source_progress`、`search_results` 表与 `get_search_results_page()` 已落地（见 `reviews/015-task13-store-implementation.md`）；协议固化与复用审计未收口。此前任务表长期写「待执行」，与代码脱节，本次一并修正。
- **015 Task14 USENIX 增量目录同步** ｜ 待执行 → 已完成 ｜ 2026-09-07 收口回填：USENIX 增量目录同步与 `/accepted` 只读端点已落地；按年份解析 slug 的修复经 `reviews/015-backend-review.md` 评审，结论 WARNING（1 项 HIGH：`_listing_for` 新正则无回归测试，列为下一提交强制项）。
- **015 安全顶会论文检索与知识库导入** ｜ 已确认 → 实施中（收口核对，维持实施中）｜ 2026-09-07 收口核对：验收评审（`reviews/015-acceptance-review.md`）结论为「整体验收不通过（阻塞）」且 Tech Lead 待签字，Task15–17 从未分派、无实现（A17 来源进度卡、A18 RAG 分页、A16 增量目录端到端均无证据），Task04 待执行，A3/A10/A11/A14 仍受外部与环境阻塞。**不满足转 `已完成` 的 DoD，保持 `实施中`**。按用户既定顺序：先完成 Spec017 后端重构与全量回归，再回来做 Task15/16。
- **017 Task02 建立迁移清单与契约基线** ｜ 待执行 → 已完成 ｜ 2026-09-07 收口回填：`plans/017/migration-inventory.md` 与 `openapi-baseline.json` 已冻结落盘，此前任务表长期写「待执行」，与代码脱节。
- **017 Task03 拆分 API 与平台装配** ｜ 待执行 → 已完成 ｜ 2026-09-07：路由拆分两批（system/chat/kb、paper/article）完成，`routes.py` 缩为 37 行纯注册入口；设置拆分、跨域 port（`platform/ports.py`）、composition root（`platform/bootstrap.py`）已落地；路由依赖改经注册表解析，3 处死 `TaskStore` 单例已删并新增架构测试锁定。端点归属清单落盘 `plans/017/api-module-inventory.md`。OpenAPI 与基线逐项一致（35 个 /api 操作，0 差异），全量 628 passed。
- **017 Task05 迁移知识库限界上下文** ｜ 待执行 → 已完成 ｜ 2026-09-08：10 个实现模块迁入 `knowledge_base/infrastructure/`；受控入口 `knowledge_base/application.py` 以显式 `__all__` 承接全部对外契约；`services/kb` 包（含 43 成员 facade）已删除，跨层 facade 通道不复存在。消费方按边界分流：api/脚本/论文发现走 application 入口，测试走 infrastructure。OpenAPI 与基线逐项一致，全量 629 passed。
- **017 Task06 迁移文章助手与聊天** ｜ 待执行 → 已完成 ｜ 2026-09-08：article_assistant/ 与 chat/ 建立；ollama*.py 迁 platform；run_chat 因依赖 graphs.chat（业务模块）下沉到 chat/application/chat_runner.py。
- **017 Task07 删除旧结构并验证模块边界** ｜ 待执行 → 已完成 ｜ 2026-09-08：observability 迁 platform、chat graph 迁 chat/application；删除 services/domain/graphs/observability 四个旧包；架构测试扩到 5 条可执行断言。
- **017 Task08 评审、部署与复盘** ｜ 待执行 → 已完成 ｜ 2026-09-08：验收评审通过（QA 与 Tech Lead 签字均由主模型代行，用户临时要求）；服务实际启动，首页/health/kb-health/conferences/kb-papers 均 200；复盘落盘。
- **017 后端限界上下文模块化** ｜ 已确认 → 已完成 ｜ 2026-09-08：Task02–08 全部完成。全量 631 passed；OpenAPI 与基线逐项一致；ruff 与迁移前持平。遗留：Reranker 降级运行、PaperImportPort 未实现、knowledge_base 受控入口待收窄。
- **018 知识文档切片检查器与双向原文定位** ｜ 实施中 → 待确认 ｜ 2026-09-08：Task02 只读 Go/No-Go 完成，严格结论 `NO-GO`。现有 PDF parser 仅返回 `(page, text)`，无法证明同源 bbox/line/word provenance DTO；hostile PDF 浏览器零网络请求证据未建立。固定 fixture、expected JSON、schema、审计报告和层级日志已落盘，Task03–07 暂停，待修订契约后重新确认。
- **018 知识文档切片检查器与双向原文定位（自动重建修订）** ｜ 待确认 → 待确认 ｜ 2026-09-08：经 Grill with Docs 确认旧 PDF 首次打开自动重建已有 v1/v2、原地替换前保存完整 point/vector 快照、失败恢复、首次失败后仅手动重试、块级 bbox、partial 可切换及 v2 不降级；hostile 浏览器网络硬门移至 Task05。新增 Task02A/02B，上一版评审不覆盖本修订，等待重新评审与确认；未修改业务代码。
- **018 知识文档切片检查器与双向原文定位（自动重建修订）** ｜ 待确认 → 已确认 ｜ 2026-09-08：独立需求复审通过；独立技术复审首轮打回四项 P0，补齐 hybrid_search 排除、文档级 operation/恢复、snapshot schema 和 bundle→manifest 边界后复审通过。用户明确要求开始执行。
- **018 知识文档切片检查器与双向原文定位（自动重建修订）** ｜ 已确认 → 实施中 ｜ 2026-09-08：仅放行 Task02A 生产级来源定位与旧索引安全升级基础；Task02B `GO` 前继续阻塞 Task03–07。
- **018 知识文档切片检查器与双向原文定位（全库索引替换修订）** ｜ 实施中 → 待确认 ｜ 2026-09-09 03:43 +0800：用户确认旧 Qdrant vectors 与旧 manifest 可丢弃，改为停服期间构建独立候选 Collection、严格验证、alias 切换和 finalize；原件、元数据和 ID 保留且原件不可原位修改。Task02A-A～C 保留，未提交 D1 snapshot 草稿废弃；业务代码暂停，等待重新需求/技术评审及用户确认。
- **018 知识文档切片检查器与双向原文定位（全库索引替换修订）** ｜ 待确认 → 已确认 ｜ 2026-09-09 10:50 +0800：独立需求评审通过；技术复审确认 P0-1～P0-7 和 upload-closure baseline 设计门全部关闭。用户明确要求“继续开发…开始执行”，确认本修订；Task04/06 的实际实现门仍保持未放行。
- **018 知识文档切片检查器与双向原文定位（全库索引替换修订）** ｜ 已确认 → 实施中 ｜ 2026-09-09 10:50 +0800：仅放行 Task02A-D 的候选索引重建基础实现与固定样本/FakeQdrant 验证；不操作真实用户索引，Task02B `GO` 前继续阻塞 Task03–07。
- **018 功能优先与生产安全债务分层** ｜ 实施中 → 实施中 ｜ 2026-09-09：用户要求先完成功能，安全问题记录后续完善。Task02A/02B 改为功能门与生产切换安全门双结论：功能通过可继续 Task03–05；候选删除授权、恢复拓扑、防篡改与 fsync 等债务全部转为 Task06 前置硬门，关闭前禁止真实 Qdrant 与任何真实 Collection 写删。
- **018 Task02A 生产级 provenance 与候选重建基础** ｜ 实施中 → 已完成（功能门） ｜ 2026-09-09：CandidateIndexPort、rebuild CLI/FSM、拓扑与验证 schema 完成四轮加固；候选测试 37 passed、独立探针 16/16 passed，tester/reviewer 均给出功能 GO。真实 Qdrant 与生产切换结论保留为 `DEFERRED_TO_TASK06`。
- **018 Task02B 来源锚点与候选协议重验证** ｜ 待执行 → 实施中 ｜ 2026-09-09：Task02A 功能门通过，开始以首轮固定样本和正式入口重放 PDF/Markdown block/chunk/anchor oracle；本 Task 仍禁止真实数据和真实 Qdrant。
- **018 Task02B 来源锚点与候选协议重验证** ｜ 实施中 → 已完成（功能 GO） ｜ 2026-09-09：修复 PDF-v2 同页 block 拼接导致 LLM 未调用的问题后，22/22 证据哈希、7/7 固定样本与 100 项联合测试通过；bbox 误差 0、Markdown 行号 100%。tester/Tech Lead 放行 Task03–05，生产切换仍延期至 Task06。
- **018 Task03 通用文档、Manifest 与迁移协议** ｜ 待执行 → 实施中 ｜ 2026-09-09：Task02B 功能 GO 后开始冻结 KnowledgeDocument/InspectionManifest/FinalizeBundle 契约与旧 metadata 迁移边界。
- **018 Task03 通用文档、Manifest 与迁移协议** ｜ 实施中 → 已完成（功能 GO） ｜ 2026-09-09：四份 schema、CONTEXT/ADR、幂等迁移与 canonical application 边界完成；30 项定向、370 项回归和 8/8 独立探针通过。旧 upload/delete/durability 问题留账转 Task04/06。
- **018 Task04 后端文档 Manifest 与检查接口** ｜ 待执行 → 实施中 ｜ 2026-09-09：Task03 功能门通过，开始实现通用文档 API、只读 source、真实索引 manifest、旧上传入口迁移与 generation/finalize 门禁。
- **018 Task04 后端文档 Manifest 与检查接口** ｜ 实施中 → 已完成（功能门） ｜ 2026-09-09 19:14 +0800：两轮修复后，检查、上传、原件读取、reindex 与删除的功能契约获 backend-reviewer `GO` 与 backend-tester `PASS`；定向 54 passed、相关回归 394 passed。closure matrix 仍为 baseline_frozen，生产切换债务继续阻塞 Task06。
- **018 Task05 前端双栏切片检查器** ｜ 待执行 → 实施中 ｜ 2026-09-09 19:14 +0800：Task04 功能门双签通过，放行本地 PDF.js、Markdown 块渲染、切片分页与双向定位实现；不触发全库重建或真实 Qdrant 变更。
- **018 Task05 前端双栏切片检查器** ｜ 实施中 → 已完成（功能门） ｜ 2026-09-10：四套 Node 前端契约测试、Schema/资源版本/vendor hash/path 检查和真实浏览器 hostile fixture（Markdown/PDF PASS、remoteRequests=0、Console 为空）通过；frontend-tester `PASS`、frontend-reviewer `GO`。worker 运行时 hash 加固、真实索引替换和恢复仍移交 Task06，Spec018 整体继续实施中。
- **018 Task06 真实全库索引替换、恢复与性能验收** ｜ 待执行 → 实施中（06-A 完成；06-B 前置门禁阻塞） ｜ 2026-09-10：FakeQdrant/临时目录故障矩阵 32/32、定向 pytest 44 passed，dry-run 写入 spy=0；真实 Qdrant、用户索引、原件和服务均未触碰。Task04 closure matrix 仍为 baseline/open/pending，生产切换保持 NO-GO。
- **018 Task06-B 前置审计与 FinalizeBundle 主链修复** ｜ 实施中 ｜ 2026-09-10：审计确认 closure matrix 17 open/12 pending，生产门继续 NO-GO；默认 rebuild 已接入 run-scoped FinalizeBundle stage、marker-last commit 与新进程 resume，相关定向测试 47 passed。弱 retire capability、legacy closure 测试和真实 Qdrant 行为仍阻塞 06-C。
- **018 Task06-B Retire fail-closed 修复** ｜ 实施中 ｜ 2026-09-10：旧 Collection 删除后新增 fresh-topology 后置条件，no-op 返回 `RETIRE_EFFECT_NOT_OBSERVED`、拓扑未知返回 `ACTION_RESULT_UNKNOWN`，均不得继续 finalize；49 项定向回归、9/9 独立探针、backend-tester `PASS` 与 backend-reviewer `GO`。真实 Qdrant 和 closure matrix 仍未放行。
- **018 Task06-B Closure-core 旁路收口** ｜ 实施中 → 实施中 ｜ 2026-09-10：修复旧固定 Collection 写入旁路、候选绑定、generation marker 绕过、reindex digest 漂移、paper-import 默认索引旁路与启动边界证据；8 个 core 门禁、378 项 KB 回归通过，独立 tester/reviewer 判定隔离 GO/PASS。论文导入、浏览器边界和真实生产切换仍未放行。
- **018 Task06-B 论文导入、批量补偿与浏览器边界** ｜ 实施中 → 实施中 ｜ 2026-09-10：批次 attempt owner/token、资源补偿、重启快照、immutable adapter composition 和 browser 零知识库写入边界完成；独立 reviewer/tester 对 T-IMMUTABLE-CREATE、T-PAPER-IMPORT、T-IMPORT-COMPENSATION、T-BROWSER-BOUNDARY 给出 GO/PASS，closure matrix 更新为 `implementation_ready`。真实 Qdrant、真实登录、generation topology 和生产维护窗口仍 NO-GO。
- **018 Task06-B generation-bound 补偿与导入** ｜ 实施中 → 实施中 ｜ 2026-09-10：补偿 ledger 纳入 `destination_collection`，默认 indexer/deleter 对缺绑定 capability fail-closed，marker drift 不会错误标记 `indexed`；独立 tester 63 项通过，首轮 reviewer 的问题已由下一轮修复。
- **018 Task06-B generation refresh/commit TOCTOU** ｜ 实施中 → 实施中 ｜ 2026-09-10：refresh 与 FinalizeBundle commit 共用 manifest-store 锁，expected collection 在锁内 compare-before-write；独立 reviewer 给出 generation-bound 隔离门 GO。真实 Qdrant、跨进程锁和生产切换仍未放行。
- **018 Task06-B 浏览器会话生命周期** ｜ 实施中 → 实施中 ｜ 2026-09-10：首轮 reviewer 发现请求期间 TTL 过期导入、并发 reopen/idle cleanup 两个 P1；已通过 daemon TTL 回收、import boundary 最终检查和 state-lock 注册边界修复，85 项隔离测试通过，独立 reviewer v2 判定 browser 子门禁 GO。真实浏览器、跨进程与生产 Qdrant 仍未验收。
- **018 Task06-B 历史旧索引测试迁移** ｜ 实施中 → 实施中 ｜ 2026-09-10：3 项历史失败测试已迁移到 canonical document/generation-bound API，未恢复退休入口；历史文件 5 passed、相关集 30 passed、全量回归 902 passed，独立 reviewer 判定迁移范围 GO。真实 Qdrant、跨进程和生产切换仍未验收。
- **018 Task06-B rebuild 锁与 stale recovery** ｜ 实施中 → 实施中 ｜ 2026-09-10：首轮 stale unlink/recreate 与 token TOCTOU 评审为 NO-GO；改为固定 inode + POSIX flock 持有式协议并补齐跨进程/异常退出接管测试，candidate+CLI 50 passed、全量回归 905 passed/1 skipped，独立 reviewer v2 判定隔离门 GO。真实 Qdrant、生产维护窗口和多机边界仍未验收。
- **018 Task06-B 真实源文件解析与 ID 安全门** ｜ 实施中 → 实施中（隔离 GO；真实 dry-run 阻塞） ｜ 2026-09-10：复用既有 `resolve_paper_path` 兼容旧 metadata 展示名与 `{document_id}.pdf` 原件布局，并收紧 basename/Unicode 控制字符校验；独立复评 GO，候选重建 59 passed、全量回归 916 passed/1 skipped。真实 dry-run 继续发现 4 个 42-byte `PDF_EMPTY` 原件；按 Spec018 权威 metadata 全集规则未执行 Qdrant 切换，等待数据处置决定。
- **018 Task06-B 空壳失败原件清理授权** ｜ 实施中 → 实施中 ｜ 2026-09-10：用户明确授权一次性删除已核对的 4 条 `status=failed`、42-byte、`PDF_EMPTY` 原件及对应 metadata 行；执行前需生成可恢复备份并逐项核对固定 ID/大小/hash，其他原件、metadata、Qdrant 和代码范围不变。
- **018 Task06-B 单文档 metadata 迁移与上传验证** ｜ 实施中 → 实施中 ｜ 2026-09-10：对当前保留的 1 条旧格式 metadata 完成 `018-document-v1` 原子迁移并生成备份；服务重启后健康/文档列表 HTTP 200，使用现有 PDF 做去重式上传返回 HTTP 201。真实 Qdrant 代际切换仍未放行。
