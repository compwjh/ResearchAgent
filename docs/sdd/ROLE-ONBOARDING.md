# 角色上手指南（Role Onboarding）

> 目的：让每个角色 Agent **只加载自己该看的少量文档**就开始工作，避免全项目扫描、挤占上下文窗口与 token。
> 用法：启动时先读本文件里自己那一段，只打开「重点读」列出的文件；`忽略` 里的不要主动读取，除非当前任务确实需要。
> 完整流程见 `AGENTS.md`；spec 模板见 `00-sdd-spec-template.md`。

---

## 架构师（Architect）

- **何时接手**：收到新需求 / 需求变更，spec 处于 `待确认` 之前。
- **重点读**：
  - `AGENTS.md`（强制流程、多角色与 RACI、评审门禁）
  - `docs/sdd/00-sdd-spec-template.md`（按模板写 spec）
  - `docs/sdd/MODEL_REGISTRY.md`（填执行配置用）
  - 同功能域已有 spec（`docs/sdd/specs/`）以复用约定
- **产出**：`docs/sdd/specs/NNN-kebab-case.md` + 执行配置段
- **忽略**：`reviews/` 历史、`backend/`/`frontend/` 实现代码（除非需确认接口现状）
- **上下文建议**：64k–200k（旗舰推理模型）

## 产品经理（PM）

- **何时接手**：spec 已 `已确认`，补「产品使用步骤」段。
- **重点读**：
  - 对应 spec 的「一句话目标 / 数据模型 / 端点接口 / 边界」段
  - `docs/sdd/00-sdd-spec-template.md` 的「产品使用步骤」段说明
- **产出**：spec 的「产品使用步骤 / 用户旅程 / 验收场景」
- **忽略**：模型选型、CI 配置、后端实现细节
- **上下文建议**：32k–64k（中等推理/写作模型，可本地）

## 开发主管（Tech Lead）

- **何时接手**：评审门禁节点；PR 合并裁决。
- **重点读**：
  - 对应 spec（全文）
  - `docs/sdd/reviews/NNN-requirement-review.md`、`NNN-tech-review.md`（待写/已写）
  - `docs/sdd/pr-template.md`（审 PR 用）
- **产出**：三份评审文档、`reviews/` 结论、PR approval
- **忽略**：模型库细节（除非预算异常）、前端样式实现
- **上下文建议**：64k–200k（强推理/代码模型）

## 初级开发（Junior Dev）

- **何时接手**：spec `已确认` 后，在 `spec/NNN-*` 或 `fix/NNN-*` 分支编码。
- **重点读**：
  - 对应 spec 的「数据模型 / 端点接口 / 边界 / 明确不做 / 产品使用步骤」段
  - 自己分支相关文件
- **产出**：代码 + 自测结果（lint/test/覆盖率）
- **忽略**：`reviews/` 历史、其他 spec、架构决策讨论
- **上下文建议**：32k（中等代码模型，优先本地 Ollama）

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
- **上下文建议**：32k，模型 `qwen3.8:27b-mlx`（后端含并发/事务/边界，必须 27B 级）

## 前端开发（Frontend Dev）— `frontend-dev`

- **何时接手**：改动**只涉及 `frontend/**`**（`index.html` / `app.js` / `styles.css`）。
- **重点读**：spec 的边界段 + `.codebuddy/skills/frontend-patterns/SKILL.md` + `regression-guard`（第 1–4 条）
- **产出**：前端代码 + 三项自查（class 与 CSS 对应 / `?v=N` 已升 / 无 `innerHTML`）
- **忽略**：`backend/**`、后端 pytest（后端改动转派 `backend-dev`）
- **上下文建议**：32k，模型 `qwen3.5:9b`（改动小且规则明确，优先速度）

## 后端评审（Backend Reviewer）— `backend-reviewer`

- **何时接手**：后端实现完成需评审，或对 `backend/**` 改动做代码审查。
- **重点读**：spec 全部 + 改动文件 + `backend-patterns` + `regression-guard`（第 5–9 条）
- **产出**：后端评审报告（`docs/sdd/reviews/`）
- **忽略**：前端改动（转 `frontend-reviewer`）
- **上下文建议**：32k，模型 `qwen3.8:27b-mlx`（评审需强推理）

## 前端评审（Frontend Reviewer）— `frontend-reviewer`

- **何时接手**：前端实现完成需评审。
- **重点读**：改动文件 + `frontend-patterns` + `regression-guard`（第 1–4 条）
- **产出**：前端评审报告（DOM 契约 / `?v=N` / XSS 三项必查逐项结论）
- **忽略**：后端改动（转 `backend-reviewer`）
- **上下文建议**：32k，模型 `qwen3.5:9b`（机械核对为主）

## 后端回归（Backend Tester）— `backend-tester`

- **何时接手**：改动只涉及后端，需回归验证或按验收点做后端验收。
- **重点读**：验收点 + 相关后端测试 + `backend-patterns`
- **产出**：后端验收结论（命令 / 退出码 / 真实输出摘要）
- **忽略**：前端测试（转 `frontend-tester`）——**单端改动只跑该端回归，省资源**
- **上下文建议**：32k，模型 `qwen3.5:9b`

## 前端回归（Frontend Tester）— `frontend-tester`

- **何时接手**：改动只涉及前端，需回归验证。
- **重点读**：改动文件 + `frontend-patterns`
- **产出**：前端验收结论（`node --check` / class 对应 / `?v=N` / XSS 四项）
- **忽略**：后端 pytest（转 `backend-tester`）
- **上下文建议**：32k，模型 `qwen3.5:9b`
