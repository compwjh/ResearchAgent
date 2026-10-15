# 角色上手指南（Role Onboarding）

> 目的：让每个角色 Agent **只加载自己该看的少量文档**就开始工作，避免全项目扫描、挤占上下文窗口与 token。
> 用法：启动时先读本文件里自己那一段（标题里的反引号名即 `.codebuddy/agents/<name>.md`），只打开「重点读」列出的文件；`忽略` 里的不要主动读取，除非当前任务确实需要。
> 完整流程见 `AGENTS.md`；spec 模板见 `00-sdd-spec-template.md`。
> **本文件不复述模型型号**：档位唯一真源是 `.codebuddy/agents/<name>.md` 的 `model` 字段，清单见 `docs/sdd/MODEL_REGISTRY.md`。
> **（2026-09-20 修正）** `PM` / `Tech Lead` / `Junior Dev` 在 `.codebuddy/agents/` 下**没有对应文件**，已改为真实 agent 名。

---

## CLI Task 的最小入口

收到 CLI 渲染的 Task Prompt 时，先读该 Prompt 的 `Read:` 清单和对应角色段；
完整 Task/结果协议见 `docs/sdd/TASK-PROTOCOL.md`。不得扩展读取为全仓扫描。
按 `Result:` 指定路径交付结果，终态由协调者通过 CLI 校验；通用分派纪律见 `AGENTS.md`。

## 架构师（Architect）— `architect`

- **何时接手**：收到新需求 / 需求变更，spec 处于 `待确认` 之前。
- **重点读**：
  - `AGENTS.md`（强制流程、多角色与 RACI、评审门禁）
  - `docs/sdd/00-sdd-spec-template.md`（按模板写 spec）
  - `docs/sdd/MODEL_REGISTRY.md`（填执行配置用）
  - 同功能域已有 spec（`docs/sdd/specs/`）以复用约定
- **产出**：`docs/sdd/specs/NNN-kebab-case.md` + 执行配置段
- **忽略**：`reviews/` 历史、`backend/`/`frontend/` 实现代码（除非需确认接口现状）
- **上下文建议**：64k–200k（旗舰推理模型）

## 文档更新（Doc Updater）— `doc-updater`（历史称 PM）

- **何时接手**：spec 已 `已确认`，补「产品使用步骤」段。
- **重点读**：
  - 对应 spec 的「一句话目标 / 数据模型 / 端点接口 / 边界」段
  - `docs/sdd/00-sdd-spec-template.md` 的「产品使用步骤」段说明
- **产出**：spec 的「产品使用步骤 / 用户旅程 / 验收场景」
- **忽略**：模型选型、CI 配置、后端实现细节
- **上下文建议**：32k–64k（中等推理/写作模型，可本地）

## 架构师（评审/合并）— `architect`（历史称 Tech Lead）

- **何时接手**：评审门禁节点；PR 合并裁决。
- **重点读**：
  - 对应 spec（全文）
  - `docs/sdd/reviews/NNN-requirement-review.md`、`NNN-tech-review.md`（待写/已写）
  - `docs/sdd/pr-template.md`（审 PR 用）
- **产出**：三份评审文档、`reviews/` 结论、PR approval
- **忽略**：模型库细节（除非预算异常）、前端样式实现
- **上下文建议**：64k–200k（强推理/代码模型）

## 跨端 / 归属不确定的改动（**不存在 `junior-dev`**）

- **本项目没有 `junior-dev`**（`.codebuddy/agents/` 下无此文件），历史文档里的「初级开发」一律按下面方式落地：
  - 纯 `backend/**` → 见「后端开发」段，分派 `backend-dev`
  - 纯 `frontend/**` → 见「前端开发」段，分派 `frontend-dev`
  - 跨端 → **拆成两个任务分别分派**，不要派一个 agent 通吃两端
- 分支：spec `已确认` 后在 `feature/spec-NNN-*` 或 `fix/spec-NNN-*` 分支编码（见 `AGENTS.md`「Git 规范」）。

## 测试（QA）

- **何时接手**：实现完成后做验收评审；或 Bug 复现。
- **重点读**：
  - 对应 spec 的「边界 / 产品使用步骤 / 验收场景」段
  - `docs/sdd/reviews/NNN-acceptance-review.md`（待写）
- **产出**：`NNN-acceptance-review.md`（报告 + 结论）、Bug 复现证据
- **忽略**：架构决策、模型预算、未涉及模块的代码
- **上下文建议**：32k（中等代码模型，优先本地 Ollama）

## 后端开发（Backend Dev）— `backend-dev`

- **何时接手**：spec `已确认` 后，改动**只涉及 `backend/**`**（API / 服务 / 数据层 / 迁移）。
- **重点读**：spec 的数据模型/接口/边界段 + `.codebuddy/skills/backend-patterns/SKILL.md` + `regression-guard`（第 5–9 条）
- **产出**：后端代码 + 自测结果（`py_compile` / `pytest`）
- **忽略**：`frontend/**`、前端测试、其他 spec（前端改动转派 `frontend-dev`）
- **上下文建议**：32k（模型档位读 `.codebuddy/agents/backend-dev.md` 的 `model` 字段，本文件不写死）

## 前端开发（Frontend Dev）— `frontend-dev`

- **何时接手**：改动**只涉及 `frontend/**`**（`index.html` / `app.js` / `styles.css`）。
- **重点读**：spec 的边界段 + `.codebuddy/skills/frontend-patterns/SKILL.md` + `regression-guard`（第 1–4 条）
- **产出**：前端代码 + 三项自查（class 与 CSS 对应 / `?v=N` 已升 / 无 `innerHTML`）
- **忽略**：`backend/**`、后端 pytest（后端改动转派 `backend-dev`）
- **上下文建议**：32k（模型档位读 `.codebuddy/agents/frontend-dev.md` 的 `model` 字段，本文件不写死）

## 后端评审（Backend Reviewer）— `backend-reviewer`

- **何时接手**：后端实现完成需评审，或对 `backend/**` 改动做代码审查。
- **重点读**：spec 全部 + 改动文件 + `backend-patterns` + `regression-guard`（第 5–9 条）
- **产出**：后端评审报告（`docs/sdd/reviews/`）
- **忽略**：前端改动（转 `frontend-reviewer`）
- **上下文建议**：32k（模型档位读 `.codebuddy/agents/backend-reviewer.md` 的 `model` 字段，本文件不写死）

## 前端评审（Frontend Reviewer）— `frontend-reviewer`

- **何时接手**：前端实现完成需评审。
- **重点读**：改动文件 + `frontend-patterns` + `regression-guard`（第 1–4 条）
- **产出**：前端评审报告（DOM 契约 / `?v=N` / XSS 三项必查逐项结论）
- **忽略**：后端改动（转 `backend-reviewer`）
- **上下文建议**：32k（模型档位读 `.codebuddy/agents/frontend-reviewer.md` 的 `model` 字段，本文件不写死）

## 后端回归（Backend Tester）— `backend-tester`

- **何时接手**：改动只涉及后端，需回归验证或按验收点做后端验收。
- **重点读**：验收点 + 相关后端测试 + `backend-patterns`
- **产出**：后端验收结论（命令 / 退出码 / 真实输出摘要）
- **忽略**：前端测试（转 `frontend-tester`）——**单端改动只跑该端回归，省资源**
- **上下文建议**：32k（模型档位读对应 agent 文件的 `model` 字段，本文件不写死）

## 前端回归（Frontend Tester）— `frontend-tester`

- **何时接手**：改动只涉及前端，需回归验证。
- **重点读**：改动文件 + `frontend-patterns`
- **产出**：前端验收结论（`node --check` / class 对应 / `?v=N` / XSS 四项）
- **忽略**：后端 pytest（转 `backend-tester`）
- **上下文建议**：32k（模型档位读对应 agent 文件的 `model` 字段，本文件不写死）
