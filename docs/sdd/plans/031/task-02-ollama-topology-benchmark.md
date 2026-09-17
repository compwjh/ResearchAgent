# Task 02：单实例/多实例与 Worker 基准门

> 关联：[Spec 031](../../specs/031-dynamic-model-resource-routing.md) ｜ 索引：[README](./README.md)
> 依赖：Spec027/028 完成、Spec031 确认及双评审；被依赖：Task03–06；当前状态：`实施中`

## 一句话目标

对单 Ollama 服务的 1–4 个 9B Worker 做可复现基准，并仅在证据证明有收益时放行多实例。

## 完整分派 Prompt

```text
角色：architect + backend-tester；读取 Spec031、本 Task、Spec013 观测接口、Spec027/028 调度合同和当前 Ollama 配置。
允许修改：plans/031/artifacts/task-02/**、tests/test_spec031_benchmark_contract.py；不得永久修改 Ollama 配置。
禁止下载模型、破坏局域网访问、在真实研究任务繁忙时压测、业务代码、push/merge/reset/stash/clean。
验证：固定输入、预热/冷启动分离、1/2/3/4 Worker、TTFT、吞吐、峰值内存、错误率；必要时临时多端口探针后清理。
完成状态：多实例 GO/NO-GO，有原始数据、环境和复现命令。
报告：artifacts/task-02/ollama-topology-benchmark.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 统计口径必须相同；超时记录环境，不能改写为性能结论。
- 产出基准数据、合同测试和 Go/No-Go 报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建 Ollama 拓扑基准 Task。
