> 关联：[Spec039](../../specs/039-api-e2e-manual-acceptance-protocol.md) ｜ 索引：[README](./README.md)
> 依赖：Task01；当前状态：`已完成`

# Task02：固化 API E2E 成功案例协议

## 一句话目标

规定真实服务 API 成功案例的创建、捕获、验证和落盘格式。

## 允许修改

- `.codebuddy/skills/spec-api-acceptance/SKILL.md`
- `artifacts/` 下本 Task 的协议样例

## 验收

- 明确自然语言 Intake 何时是必测主路径；
- 记录请求、响应、状态机和最终产物；
- 禁止 mock、内部函数和仅表单路径冒充用户成功案例；
- 缺少 API 成功案例时输出阻塞，不允许进入人工验收。

## 执行结果

协议已固化到 `.agents/skills/spec-acceptance-protocol/SKILL.md` 和 Spec039：真实部署 HTTP、自然语言
主入口、状态轨迹、实体 ID、Artifact 路径和失败证据均为必填；表单、mock、fixture、内部函数不能替代。
Spec032 的真实运行证据见 `artifacts/spec032-api-e2e-success.md`。
