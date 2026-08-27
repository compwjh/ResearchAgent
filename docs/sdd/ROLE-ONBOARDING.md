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
