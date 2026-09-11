# Task 04：实现研究任务页面、SSE 与会话入口

> 关联：[Spec 027](../../specs/027-research-task-dynamic-orchestration-mvp.md) ｜ 索引：[README](./README.md)
> 依赖：Task03；被依赖：Task05–06；当前状态：`待执行`

## 一句话目标

让用户从会话显式创建深度研究任务，并在独立页面观察计划、Worker、模型、论文选集和报告，刷新后可以恢复。

## 范围与步骤

- 新增独立前端模块，避免继续堆积 `app.js`；入口与现有项目/会话 UI 复用状态和安全渲染函数。
- 实现任务列表、计划时间线、模型/Worker 标签、论文选集、只读报告和会话任务卡片。
- SSE 使用 event_seq 去重和重连；低频查询仅作恢复兜底。
- 桌面三栏、窄屏单栏；手机端可查看、暂停/取消和阅读报告。

## 完整分派 Prompt

```text
角色：frontend-dev，模型按 Spec027 执行配置；本地模型单次最多改两个代码文件。
读取：Spec027、本 Task、Task03 API 报告、frontend/index.html、frontend/app.js、frontend/styles.css、现有 conversation/project 模块。
允许修改：frontend/research-tasks.js、frontend/index.html、frontend/styles.css、必要的 app.js 接线和 tests/test_spec027_frontend*；按两文件分派。
禁止：修改 backend；使用 innerHTML 渲染不可信内容；展示隐藏思维链/完整 Prompt；引入前端框架；push/merge/reset/stash/clean。
完成状态：可从深度研究模式创建任务，实时/刷新后查看时间线和报告，普通模式只建议切换。
验证：node --check、DOM/事件/SSE/版本号合同、桌面与 390px 浏览器 smoke、git diff --check。
结果写入：docs/sdd/plans/027/artifacts/task-04/frontend-report.md。
返回固定字段同 Spec027 Task 规范。
```

## 主 Agent 校验与验收

- 检查资源版本号、XSS、安全文本渲染、事件终态和菜单遮挡。
- 重跑前端定向测试，不跑后端全量。
- 断开 SSE 后恢复无重复；页面关闭不发送取消；手机关键操作可达。

## 风险、回滚与产出

- API 合同不完整时停止，不在前端猜字段。
- 回滚仅移除研究任务入口/模块，不影响普通聊天。
- 产出：前端代码、合同测试、`artifacts/task-04/frontend-report.md`；执行结果待填写。

## 变更日志

- 2026-09-12：创建研究任务工作台 Task。
