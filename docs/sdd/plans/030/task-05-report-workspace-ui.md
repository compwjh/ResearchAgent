# Task 05：实现报告工作台与引用交互

> 关联：[Spec 030](../../specs/030-research-evidence-reporting.md) ｜ 索引：[README](./README.md)
> 依赖：Task04；被依赖：Task06；当前状态：`已完成`

## 一句话目标

让用户查看比较矩阵、阅读版本化报告、展开引用证据并下载 Markdown/JSON。

## 完整分派 Prompt

```text
角色：frontend-dev；读取 Spec030、本 Task、Task04 API 报告、现有 citation 与文档检查器交互。
允许修改：frontend/research-tasks.js、frontend/styles.css、必要模板和 tests/test_spec030_frontend*；本地模型按两文件拆分。
禁止任意编辑报告、innerHTML 注入、修改后端、全量回归、push/merge/reset/stash/clean。
完成状态：矩阵缺口可见；编号引用可展开论文/证据等级并跳到现有切片检查；可下载两个权威文件。
验证：node --check、XSS/DOM/引用/版本/手机合同、浏览器 smoke、git diff --check。
报告：artifacts/task-05/frontend-report.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 检查引用编号、键盘操作、窄屏和旧版本切换。
- 产出 UI、合同测试和报告；执行结果待填写。

## 变更日志

- 2026-09-12：创建报告工作台 Task。
- 2026-09-17：完成矩阵、缺口、版本化报告、引用定位和只读下载 UI；`node --check` 与前端定向测试通过。
