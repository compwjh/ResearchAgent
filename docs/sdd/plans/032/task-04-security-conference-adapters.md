# Task 04：接入 IEEE S&P、ACM CCS 与 NDSS

> 关联：[Spec 032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task02 GO；被依赖：Task05–06；当前状态：`待执行`

## 一句话目标

基于官方页面固定样本实现三个安全会议目录 Adapter，支持年度/track 单元、摘要缺失和结构变化降级。

## 完整分派 Prompt

```text
角色：backend-dev；读取 Spec032、Task02 报告、USENIX source 模式、安全 URL facade 和目标会议固定样本。
允许修改：backend/app/paper_discovery/**、固定 fixtures、tests/test_spec032_conference_sources*.py；本地模型每次最多两代码文件。
禁止登录绕过、PDF 下载/探测、任意根 URL、覆盖 USENIX/DBLP、前端、全量回归。
完成状态：IEEE S&P、ACM CCS、NDSS 各有来源定义、单元发现、解析、provenance 和稳定错误。
验证：多年度/track、缺摘要/关键词、页面变化、重定向/允许主机、定向 pytest、git diff --check。
报告：artifacts/task-04/backend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 新来源没有真实固定样本或依赖脆弱猜测选择器时不得启用。
- 产出 adapters、fixtures、测试和报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建安全会议 Adapter Task。
