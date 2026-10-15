---
name: sdd-plan-tasks
description: 将需求整理为可评审的 SDD spec、任务索引与完整 Task Prompt，并按仓库协议落盘。用户要求规划、拆分或创建 SDD spec 和 Task 文档时使用。
---

# SDD Plan Tasks

把用户目标转成可评审、可独立执行的 SDD 文档，并保持需求、任务和链接一致。

## 编排流程

1. 阅读 `AGENTS.md` 的 SDD 流程、`docs/sdd/00-sdd-spec-template.md` 和 `docs/sdd/TASK-PROTOCOL.md`。修改既有 spec 时，先读该 spec、任务索引及相关 Task，沿用已有编号和已确认范围。
2. 从请求中明确目标、范围、明确不做、可观察的验收条件、依赖和必要门禁。标出仍阻止拆分或验收的缺失信息，不把猜测写成事实。
3. 新建 spec 时，按模板创建 spec、任务索引 README 和从 Task 02 开始的全部 Task 文档；修改既有 spec 时，只更新受影响的文档并核对索引。让每个 Task 交付一个可独立验收的结果；确保依赖有依据、无环，文档链接真实有效。
4. 对每个可执行 Task，严格采用协议规定的 metadata 与完整 prompt 块。填写准确的输入文件、逻辑角色、能力、允许路径、依赖、门禁、产物、验证命令和回传 schema；prompt 必须可原样分派、范围封闭且能据证据验收。选择仓库中实际定义且匹配工作的角色。
5. 对照模板和协议逐项检查必填内容、唯一标识、Task 与 spec/README 状态镜像、依赖及路径。让实施细节留在 Task，让 spec 说明需求与验收边界。
6. 按 `AGENTS.md` 应用 spec 的初始状态、确认与停止规则。若 Plan Mode 暂不允许写文件，先完成可审阅的计划；首个可写 turn 优先落盘 spec、索引和全部 Task，再遵循同一确认门禁。

## 交付

列出实际落盘的路径，概述 Task 顺序与依赖，并说明未解决的阻塞项。只记录可观察的依据和决定，不写隐藏推理。完成规划后停止，不开始实现或执行 Task。
