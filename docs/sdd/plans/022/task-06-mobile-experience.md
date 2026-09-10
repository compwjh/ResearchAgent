# Task 06：手机端适配

> 关联：[Spec 022](../../specs/022-project-conversation-memory.md) ｜ 索引：[README](./README.md)
> 依赖：Task05；被依赖：Task08；当前状态：`待执行`

## 一句话目标

让手机端完整访问项目、会话、记忆、历史分页、处理过程和 RAG 来源，不因侧栏隐藏而失去核心能力。

## 增量范围

- 手机顶部项目/会话入口和侧栏抽屉；选择后自动收起并保持焦点。
- 新建/切换/绑定会话、记忆提示、向上加载旧消息和错误重试。
- RAG 编号与大段切片展开、处理过程动画/折叠、减少动态效果。
- 软键盘、安全区、窄屏布局、触控目标和无横向溢出。

## 子 Agent 分派

- frontend-dev：只改前端和前端测试；后端契约不得为布局方便而另开接口。
- frontend-reviewer/tester：真实窄屏、触控、键盘、滚动保持、XSS 和资源版本检查。
- tester：部署后用手机尺寸浏览器执行里程碑 smoke；不跑后端全量。

## 边界与明确不做

- 不做原生 App、离线 PWA、推送通知、云同步或多人协作。
- 不复制桌面 DOM 为第二套业务页面；使用同一数据和交互状态。

## 测试与验收

- 典型手机宽度下侧栏可达，聊天输入不被键盘遮挡，无横向滚动。
- 长会话向上分页不跳位；正在流式时切换/返回不串写。
- 编号来源可触控展开，长切片可滚动，处理动画遵守 reduced-motion。
- 桌面布局回归保持通过；部署后完成真实浏览器 smoke。

## 风险与回滚

- 手机端若只能访问聊天而不能访问项目/历史，不得判定完成。
- CSS 作用域污染桌面或其他 Tab 时回滚本 Task 样式增量。

## 产出物

- `artifacts/task-06/implementation-report.md`
- `artifacts/task-06/test-report.md`
- `artifacts/task-06/review-report.md`
- `artifacts/task-06/acceptance-report.md`

## 执行结果

待执行后填写。

## 变更日志

- 2026-09-11：手机端保留在 Spec022 内，但明确不进入 Task02 MVP。

