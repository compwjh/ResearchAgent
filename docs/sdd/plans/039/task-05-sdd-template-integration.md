> 关联：[Spec039](../../specs/039-api-e2e-manual-acceptance-protocol.md) ｜ 索引：[README](./README.md)
> 依赖：Task04；当前状态：`已完成`

# Task05：接入 Spec/Task 模板与 Agent 交接

## 一句话目标

让每个新 Spec 在初稿记录核心人工场景，开发收口时必须补齐详细步骤，并让子 Agent 交付物包含验收证据。

## 允许修改

- `docs/sdd/00-sdd-spec-template.md`
- `AGENTS.md` 中与验收交接直接相关的精简规则
- Agent/Task 模板中与交付证据直接相关的段落

## 明确不做

- 不改变业务 API；
- 不强制每个 Task 跑全量回归；
- 不要求每次都创建新测试文件。

## 执行结果

已将验收协议接入 `docs/sdd/00-sdd-spec-template.md` 与 `AGENTS.md`：Spec 收口必须记录真实部署
API E2E、自然语言主路径、逐步点击/提示/等待/恢复动作，并达到至少 9/10 准备度且无 P0/P1。
未修改业务 API，也未改变 Task 阶段只跑定向测试、Spec 收口才跑全量回归的边界。
