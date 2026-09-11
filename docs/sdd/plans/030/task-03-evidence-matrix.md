# Task 03：实现跨论文证据矩阵

> 关联：[Spec 030](../../specs/030-research-evidence-reporting.md) ｜ 索引：[README](./README.md)
> 依赖：Task02 GO；被依赖：Task04–06；当前状态：`待执行`

## 一句话目标

实现 Claim、Evidence、比较维度和单元格的持久化生成与严格引用校验。

## 完整分派 Prompt

```text
角色：backend-dev；读取 Spec030、Task02 报告、Research Task 选集和全文证据接口。
允许修改：backend/app/research/**、routes_research.py、必要迁移、tests/test_spec030_matrix*.py；本地模型每次最多两代码文件。
禁止新检索/embedding、凭常识补论文事实、前端、全量回归、push/merge/reset/stash/clean。
完成状态：固定样本生成支持/冲突/空缺矩阵；所有 evidence id、paper、chunk/page 可校验。
验证：Schema、事务、重复、删除证据、项目隔离、恶意文本、定向 pytest、git diff --check。
报告：artifacts/task-03/backend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 检查模型调用在事务外、无证据单元格保持空。
- 产出矩阵代码、测试和报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建证据矩阵实现 Task。
