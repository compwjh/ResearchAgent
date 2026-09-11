# Task 02：冻结 Source Adapter、Provenance 与增量协议

> 关联：[Spec 032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Spec015/027 可用、Spec032 确认及双评审；被依赖：Task03–06；当前状态：`待执行`

## 一句话目标

证明现有全局目录能承载新增来源，冻结 Adapter、字段权威级别、增量单元、安全主机和冲突合并合同。

## 完整分派 Prompt

```text
角色：architect + backend-tester；读取 Spec032、本 Task、Spec015 catalog/domain/source、安全 URL 边界和各目标来源公开结构说明。
允许修改：plans/032/artifacts/task-02/**、tests/test_spec032_source_contract.py、固定脱敏样本目录。
禁止业务适配器、真实批量抓取、PDF 探测/下载、任意网站配置、push/merge/reset/stash/clean。
验证：discover/fetch/parse/normalize/health、ETag/hash、字段冲突、重复 DOI/标题、允许主机和单源失败。
完成状态：每个新增来源具备可实现映射或明确 NO-GO，禁止占位选择器。
报告：artifacts/task-02/source-adapter-contract.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 核对没有第二套缓存/身份规范化；固定样本来源和更新时间可追溯。
- 产出合同测试、fixture 清单和报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建来源协议 gate。
