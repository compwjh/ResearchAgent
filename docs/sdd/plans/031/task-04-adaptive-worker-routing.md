# Task 04：实现内存感知 Worker 扩缩与策略激活

> 关联：[Spec 031](../../specs/031-dynamic-model-resource-routing.md) ｜ 索引：[README](./README.md)
> 依赖：Task03；被依赖：Task05–06；当前状态：`实施中`

## 一句话目标

在质量门和全局资源额度内动态调整 9B Worker，并以受控流程激活或回滚路由策略。

## 完整分派 Prompt

```text
角色：backend-dev；读取 Spec031、本 Task、Task02/03 报告和 Spec028 scheduler。
允许修改：backend/app/research/**、必要平台资源探针、routes_research_routing.py、tests/test_spec031_adaptive*.py；本地模型按两文件拆分。
禁止交换内存扩容、自动下载/卸载模型、越过用户 profile、跨机器调度、全量回归。
完成状态：资源充足时 9B 可扩，余量不足排队；27B 默认单并发；探针失败退回静态单 Worker；策略可原子回滚。
验证：Fake 内存/模型状态、跨任务公平性、模型升级、策略门、定向 pytest、git diff --check。
报告：artifacts/task-04/backend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 核对全局额度原子性、至少 20% 余量和外部调用不持锁。
- 产出自适应调度代码、测试和报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建自适应 Worker Task。
- 2026-09-17：Task03 单实例条件放行且复审 GO，启动 Task04；只允许在现有 ResourceProbe/ResearchScheduler 上增加有界的资源感知调度和策略门。
