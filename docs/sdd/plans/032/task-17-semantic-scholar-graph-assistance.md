# Task 17：Semantic Scholar 自动补全与引用图辅助

> 关联：[Spec 032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task15、Task16 ｜ 当前状态：`最小实现完成，待 Task14 真实 key/部署验收`

## 一句话目标

为交互式研究选择和后续覆盖审查提供标题自动补全、引用和参考文献边；这些能力只辅助用户与 Critic，不改变官方目录和报告的证据权威。

## 前置门禁

- autocomplete 仅返回短候选，不作为完整检索结果。
- citations/references 必须以 Semantic Scholar paperId 为稳定输入，并遵守分页、limit 与 1 RPS 限流。
- 图边不能未经评估直接进入报告引用；报告仍只引用冻结的候选证据。

## 分派 Prompt

```text
角色：后端开发；模型：按 Spec032 执行配置；只读取 Spec032、Task17、SemanticScholarGraphClient、research-coverage-review 和报告引用合同。
允许修改：backend/app/paper_discovery/infrastructure/**、必要的受控 API 契约与 tests/paper_discovery/**；禁止抓取 HTML/Reader、下载 PDF、修改报告引用权威或前端视觉。
必须运行定向测试，验证输入长度、关系 allowlist、分页、限流、API 降级和敏感字段脱敏；结果写入 docs/sdd/plans/032/artifacts/task-17/，日志写入 .codebuddy/agent-logs/spec-032/task-17/backend-dev/。
固定返回：结果状态和摘要、改动文件、测试命令/退出码/结果、产物路径、决策依据、风险与阻塞、主 Agent 后续动作、开始/结束/总耗时、可用时模型/token/工具统计。
```

## 主 Agent 校验步骤

检查 autocomplete query 上限、关系类型白名单、分页 token、无 API key 时的可解释降级；确认图边不会绕过候选评估或报告冻结。

## 测试与验收标准

Mock 验证 autocomplete、citations、references 的结构化返回和非法关系拒绝；API 429/5xx 不泄漏 key、Cookie 或完整响应。

产品入口验收：`/api/papers/semantic-scholar/autocomplete` 和
`/api/papers/semantic-scholar/{paper_id}/{citations|references}` 只返回 metadata-only
合同；缺 key、非法参数和 provider 错误均使用脱敏错误结构。图边不写入目录、报告或 PDF 链路。

## 产出物

图辅助客户端、受控 API（如纳入产品）、定向测试和交接报告。

## 执行结果

客户端基础能力已落在 Task15 共用模块中；本轮补齐图边稳定结果契约、分页、输入边界、错误降级和两个只读 API。前端 UI 入口仍保持关闭，图边不会进入目录、报告或 PDF 链路。

## 变更日志

- 2026-09-21：新增 Academic Graph 交互辅助任务；明确不改变论文目录和报告证据链。
