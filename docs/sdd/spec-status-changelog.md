# Spec 状态变更记录

本文件记录所有 spec 的状态变化。每条含：spec 编号与标题、变更前 → 变更后状态、变更时间，以及一两句话说明本次变动的原因或内容。

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
