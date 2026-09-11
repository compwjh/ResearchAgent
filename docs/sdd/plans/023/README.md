# 023 Skill 与 Tool 管理模块 · 任务索引

> 关联：[spec-023](../../specs/023-skill-tool-management.md)
> 状态：spec `待确认`；**确认前所有 task 保持 `待执行`，且不创建 task 文件**（避免产生无法跳转的占位链接）。

## 目标一句话

网页上管理 Skill / Tool（只读 + 启停），对话中点名 Skill 时由 Agent 读其正文自行编排并调用后端 Tool。

## 已冻结的决策（详见 spec「决策记录」）

| # | 结论 |
|---|---|
| Q1 | Skill = 编排层（SKILL.md 协议），Tool = 执行层（后端原子动作） |
| Q2 | 只管 `.agents/skills/`；迁移并废弃 `~/.codex/skills/download-paper` 硬编码；不管 `.codebuddy/skills/` |
| Q3 | 只读浏览 + 详情 + 启用/禁用；网页不 CRUD SKILL.md |
| Q4 | 规则匹配 + LLM 意图识别双触发；27B 实测 `GO/NO-GO` |
| Q5 | 通用编排：不改 SKILL.md 正文，Agent 自己分析怎么编排 |
| Q6/Q10 | 仅允许增/改 SKILL.md frontmatter 的 `tools:`，正文不动 |
| Q7 | UI 开关 → 落到 `data/kb/skill-state.json`；不改 SKILL.md 原件 |
| Q9 | C 混合：优先原生 function calling，不支持时降级"计划 JSON" |

## 任务清单

| 编号 | 任务 | 依赖 | 状态 |
|---|---|---|---|
| 02 | 验证本地 27B 的 tool call 与意图识别能力（Go/No-Go） | 01 | 待执行 |
| 03 | 后端 Skill 注册表与读写 API | 01 | 待执行 |
| 04 | 后端 Tool 注册表、状态文件与启停 API | 01 | 待执行 |
| 05 | 迁移 `download-paper` Skill 并废弃硬编码路径 | 03 | 待执行 |
| 06 | 对话链路：规则匹配 + LLM 意图识别 | 02,03 | 待执行 |
| 07 | 对话链路：Tool 执行（原生优先、降级计划 JSON） | 04,06 | 待执行 |
| 08 | 前端 Skill/Tool 管理页面 | 03,04 | 待执行 |
| 09 | 评审、部署与复盘 | 06,07,08 | 待执行 |

## 风险与阻塞

- **本地模型 tool call 支持参差**（AGENTS.md 实测：`deepseek-coder` 系列直接不支持）。Task02 必须先实测再决定 Q4/Q9 的最终形态。
- **thinking 模型**必须 `think:false`，否则输出为空。
- 两个 USENIX Skill 的正文含"严格边界/停止条件"，编排时**不得绕过**；Tool 参数必须白名单校验。
