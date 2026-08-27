# SDD 文档目录

这里保存项目的 Specification-Driven Development（SDD）文档。

## 目录约定

- `00-sdd-spec-template.md`：所有需求 spec 的统一模板，不直接填写具体需求。
- `specs/`：每个具体需求一份 spec 文件，使用 `NNN-kebab-case.md` 命名，例如 `001-chat-layout.md`。
- `reviews/`：每份 spec 的评审文档（需求/技术/验收），编号与 spec 一致。
- `MODEL_REGISTRY.md`：模型库（线上 + 本地 Ollama），spec 执行配置的模型唯一来源。
- `pr-template.md`：PR 模板，合入 `main` 前须填写。
- `ROLE-ONBOARDING.md`：各角色上手指南，控制上下文 token，避免全项目扫描。
- `archive/`：已完成、取消或废弃的 spec，保留历史记录。

## 多角色与门禁（详见 `AGENTS.md`）

- 五角色：架构师、产品经理、开发主管、初级开发、测试；spec 由架构师编写、PM 补产品使用步骤。
- 三道门禁：需求评审 → 技术评审 → 验收评审；未过门禁不得进入下一阶段。
- 分支模型：Trunk-Based 轻量变体（`main` 主干 + `spec/NNN-*` / `fix/NNN-*` 短分支，squash 合回即删）。
- 合并门禁：CI 全绿 + 覆盖率 ≥ 80% + 至少 1 个 approval。
- CI 质量门禁：lint / test / 覆盖率≥80% / build，失败阻断并落盘原因；部署沿用 SDD 且支持回滚。

## 完成后的部署

Spec 标记为 `已完成` 前后必须由 Agent 直接执行服务启动并完成运行时验证，不能只提供推荐命令。服务成功启动后，最终交付信息必须包含实际访问地址、端口和启动命令；默认端口被占用时由 Agent 使用可用端口并直接启动。启动失败时记录真实原因和解决命令，不得将未启动的服务报告为已部署。

## Spec 状态

每份需求 spec 的开头必须包含状态：

`Draft` → `待确认` → `已确认` → `实施中` → `已完成`

如果需求被取消，状态改为 `已取消` 并移入 `archive/`。