# Task 02：冻结 Claim/Evidence 与报告协议

> 关联：[Spec 030](../../specs/030-research-evidence-reporting.md) ｜ 索引：[README](./README.md)
> 依赖：Spec027 完成；全文验收依赖 Spec029；Spec030 确认及双评审；被依赖：Task03–06；当前状态：`待执行`

## 一句话目标

用固定证据样本冻结 Claim、支持/反驳关系、比较矩阵、引用 manifest 和 Markdown/HTML/JSON 一致性合同。

## 完整分派 Prompt

```text
角色：architect + backend-tester；读取 Spec030、本 Task、Spec027/029 报告与现有 citation/chunk 合同。
允许修改：plans/030/artifacts/task-02/**、tests/test_spec030_contract.py。
禁止业务代码、真实数据、虚构缺失证据、push/merge/reset/stash/clean。
验证：支持/冲突/上下文/缺失/删除证据、错误页码/chunk、引用编号和三格式语义一致；git diff --check。
完成状态：Schema、拒绝规则、降级规则和 Go/No-Go 明确。
报告：artifacts/task-02/evidence-report-contract.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 无法由 citation manifest 回查的 Claim 必须拒绝。
- 产出合同测试与报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建证据与报告协议 Task。
