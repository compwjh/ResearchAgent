# Task 05：接通来源合并、任务进度与界面

> 关联：[Spec 032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task03、Task04；被依赖：Task06；当前状态：`待执行`

## 一句话目标

让 Research Task 动态选择已启用来源、按权威级别合并论文，并向用户展示缓存、获取、失败和降级状态。

## 完整分派 Prompt

```text
角色：backend-dev 与 frontend-dev 分端执行；读取 Spec032、本 Task、Task03/04 报告和 Spec027 来源进度 UI。
允许修改：paper_discovery/research 的最小接缝、routes、frontend/research-tasks.js/styles、对应 spec032 tests；本地模型按两文件拆分。
禁止重新实现 Planner、报告、下载/KB；低权威覆盖官方字段；全量回归；push/merge/reset/stash/clean。
完成状态：来源卡片显示 cached/fetching/completed/failed；单源失败仍有 partial；合并结果可查看字段来源。
验证：冲突、缓存命中、部分失败、event_seq、XSS、桌面手机 smoke、定向测试、git diff --check。
报告：artifacts/task-05/backend-report.md 与 frontend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 核对来源权威排序、去重和任务预算；不跑全量。
- 产出集成代码、测试和双端报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建来源集成与 UI Task。
