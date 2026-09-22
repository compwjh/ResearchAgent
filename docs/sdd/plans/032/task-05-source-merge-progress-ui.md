# Task 05：原来源合并、任务进度与界面阶段交付（部分完成）

> 关联：[Spec 032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task03、Task04；被依赖：新版 Task06–12；当前状态：`部分完成（历史交付，禁止按旧 Prompt 继续执行）`

## 一句话目标

记录原 Task05 已产出的 Registry、来源 API、authority 常量和 SQLite provenance 表；未完成的动态选源、真实同步、字段落库、进度与界面已拆入新版 Task06–12。

## 实际结果与差异（2026-09-20）

- 已有：`source_authority.py`、`source_registry.py`、Store schema v3/v4、DBLP 部分 provenance、`GET/PATCH/POST /api/papers/sources` 路由。
- 未完成：ID/authority 与 Adapter 不一致；3 条旧 authority 测试失败；Registry 未装配 Graph；`POST /sync` 无真实调度；非 DBLP 字段 provenance 未完整落库；来源卡 UI 未实现。
- 以 [资产审计](./asset-gap-audit.md) 为证据；旧 Prompt 保留仅用于历史追溯，**不再是可执行分派**。

## 历史分派 Prompt（已失效，不得复用）

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
- 实际产出和缺口见上节；未完成部分按新版任务交接，Task05 不得直接改为“已完成”。

## 变更日志

- 2026-09-12：创建来源集成与 UI Task。
- 2026-09-20：审计为部分完成，保留历史 Prompt，剩余范围拆入 Task06–12。
