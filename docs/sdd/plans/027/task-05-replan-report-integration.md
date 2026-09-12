# Task 05：完成 Re-plan、报告、模型升级与集成

> 关联：[Spec 027](../../specs/027-research-task-dynamic-orchestration-mvp.md) ｜ 索引：[README](./README.md)
> 依赖：Task03、Task04；被依赖：Task06；当前状态：`实施中`

## 一句话目标

把最小纵向切片补齐为有界动态研究闭环，真实呈现覆盖不足、Re-plan、fast→strong 升级和 partial/completed 报告。

## 实施范围

- Critic 输出结构化覆盖矩阵和缺口；最多两次 Re-plan，计划版本不可覆盖。
- 三种质量档位落实软预算，所有档位受统一硬上限。
- 报告标记 catalog/abstract 证据；无摘要不得生成论文方法或结果。
- 单源失败、无新增证据、取消和软预算耗尽均收敛到真实终态。

## 完整分派 Prompt

```text
角色：backend-dev 与 frontend-dev 分端执行，模型按 Spec027 执行配置；本地模型每次最多改两个代码文件。
读取：Spec027、本 Task、Task03/04 固定报告和实际 diff。
允许修改：backend/app/research/**、routes_research.py、frontend/research-tasks.js、frontend/styles.css、对应 spec027 定向测试；分端且按两文件拆分。
禁止：PDF 下载、全文结论、新来源、路由历史学习、多 Ollama 实例、隐藏思维链展示、全量回归。
完成状态：固定样本能在覆盖不足时新增计划版本并补搜，模型升级可见，最终生成 completed 或 partial 报告。
验证：Re-plan/预算/无新增/单源失败/取消/证据等级/前端时间线定向测试与 git diff --check。
结果分别写入 artifacts/task-05/backend-report.md 与 frontend-report.md。
返回固定字段同 Task 规范。
```

## 主 Agent 校验与验收

- 核对没有覆盖已完成 WorkItem，累计任务数不突破硬上限。
- 重跑跨端定向测试和固定样本浏览器 smoke，不执行全量回归。
- 报告中的每个主要结论有目录/摘要引用，limitations 与真实失败一致。

## 风险、回滚与产出

- Critic 只能给模糊文本或无法保证预算时停止并回到 Task02 合同。
- 产出：集成代码、测试、双端报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建动态闭环集成 Task。
- 2026-09-12：Task04 已收口，按依赖满足启动 Task05；前后端分端并行实现，模型仅本轮临时使用 Luna high。
- 2026-09-12：完成第一阶段后端 Re-plan 与前端动态事件展示；Task05 定向后端回归 92 passed、前端 Python 101 passed、Node 合同 5/5，仍保留软预算与真实 fast→strong 升级未完成项，Task05 不收口。
- 2026-09-12：完成第二阶段后端接线：阶段边界软预算耗尽收敛为 partial 并写入稳定 `budget_exhausted` 摘要；可注入 ModelRouter 的 `MODEL_ESCALATED` 安全事件接入任务事件流，含 search-worker 路径。后端定向回归 95 passed、5 subtests，Task05 仍因真实 Ollama 路由与 Task06 验收未收口。
