# Task 05：实现导入进度与失败恢复界面

> 关联：[Spec 029](../../specs/029-research-fulltext-acquisition.md) ｜ 索引：[README](./README.md)
> 依赖：Task03、Task04；被依赖：Task06；当前状态：`已完成`

## 一句话目标

让用户在 Research Task 中增删候选、确认下载，并查看已有、下载、登录等待、索引和证据升级状态。

## 完整分派 Prompt

```text
角色：frontend-dev；读取 Spec029、本 Task、Task03/04 报告、现有批量导入 UI 和 research-tasks.js。
允许修改：frontend/research-tasks.js、frontend/styles.css、必要模板与 tests/test_spec029_frontend*；本地模型按两文件拆分。
禁止修改后端、浏览器原生 prompt、复制导入状态机、自动点击登录/确认、push/merge/reset/stash/clean。
完成状态：清单可增删；确认前零下载；逐篇状态/重试可见；全文证据可跳转原文切片。
验证：node --check、DOM/XSS/状态映射、桌面手机 smoke、git diff --check。
报告：artifacts/task-05/frontend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 检查确认、重复提交、登录等待和失败恢复交互，不跑全量。
- 产出 UI、合同测试和报告；已完成定向验证。

## 执行结果

- 已完成候选增删、只读预览、显式确认、逐篇状态、登录等待、失败重试和全文证据定位入口；确认前不下载。
- 定向测试：15 passed；`node --check frontend/research-tasks.js` 通过；`git diff --check` 通过。
- 报告：[frontend-report.md](./artifacts/task-05/frontend-report.md)。

## 变更日志

- 2026-09-12：创建获取进度 UI Task。
- 2026-09-16：完成进度与失败恢复界面；后端未返回服务端 `search_id` 时前端安全禁止确认。
