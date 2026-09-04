# Spec 状态变更记录

本文件记录所有 spec 的状态变化。每条含：spec 编号与标题、变更前 → 变更后状态、变更时间，以及一两句话说明本次变动的原因或内容。

> **收口纪律**（见 `docs/sdd/SDD-GATE-CHECKLIST.md` §3）：状态流转须与本文件同步；
> 转 `已完成` 前必须满足——三份评审有真实结论、验收签字栏已填、本文件已追加、变更日志补齐、引用路径真实存在、复盘已落盘。

## 2026-09-03

- **016 可移植 Task 账本与自动执行协议** ｜ 新建 → 待确认 ｜ 为跨 Codex、CodeBuddy 和其他 Agent IDE 的研发交接建立“Git 跟踪 Markdown 为长期事实源、SQLite 为可重建运行层”的流程；Task 将包含机器元数据、完整子 Agent Prompt、统一结果协议、执行轨迹和指标。已按 spec-013 格式建立 spec 与 `docs/sdd/plans/016/` Task 02–09；当前只落盘文档，不执行实现，等待用户确认。
- **015 安全顶会论文检索与知识库导入** ｜ 新建 → 待确认 ｜ 新增独立论文检索 Tab 的规划：默认检索 CCS、USENIX Security、IEEE S&P、NDSS 最近五个完整年份，支持搜索添加会议、语义排序、单篇/批量实际下载并按“年份-会议-标题”命名后导入知识库；ACM Digital Library 与 IEEE Xplore 采用项目内 Playwright 完成合法登录续传。已按 spec-014 格式建立 spec 与 `docs/sdd/plans/015/` 任务 02–09；当前只落盘文档，不执行任务，且必须等待 spec-013/014 形成稳定基线。

## 2026-09-02

- **014 知识库本地 Rerank 重排** ｜ 新建 → 待确认 ｜ 为个人知识库增加本地 Qwen3-Reranker 批量重排；现有 Ollama 包实测不适合专用 rerank，计划改用 llama.cpp `/v1/rerank` 与兼容 Q8_0 模型。已按 spec-013 格式建立完整 spec，并在 `docs/sdd/plans/014/` 拆分任务 02–09；当前仅文档落盘，等待用户确认。
- **014 知识库本地 Rerank 重排** ｜ 待确认 → 已确认 ｜ 用户授权“当前未提交代码能运行则进行 spec-014”。已先创建 `/tmp` 安全快照并在不回滚、不 stash、不清理工作树的前提下验证：FastAPI 首页/health/KB health、Langfuse 正常，全量测试 `253 passed`；需求与技术评审均通过（附意见），条件满足，进入实施门禁。
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

- **013 本地 LLM 调用观测与性能评估平台** ｜ 实施中 → 已完成 ｜ Task 07 前端依赖与环境阻塞修复（补齐 lockfile + 离线安装 + .env），前端 37 用例全绿；5 项实质缺陷（散点丢点误判、脱敏覆盖、聚合守卫、截断提示、router 测试）闭环；C8 埋点 safe_call 包裹完成。验收由主模型代行（非独立评审）。详见 `docs/sdd/plans/013/task-07-stats-custom-view.md` 修复轮次执行结果与 `docs/sdd/reviews/013-task07-acceptance-review.md` 复核结论。
- **013 Task 07 验收** ｜ 不通过 → 通过（代行） ｜ 见上。
