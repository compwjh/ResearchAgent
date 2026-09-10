# Spec018 Task06：浏览器管理器并发 reopen 修复报告

## 状态摘要

**PASS（浏览器管理器隔离并发子门禁）**。本次只修复 `PaperBrowserManager` 的状态边界，并补充确定性故障注入测试；没有访问真实浏览器、网络、Qdrant，也没有修改导入、路由、数据库或 Spec 文档。

## 修复内容

- `open_session()` 现在在同一个 `_state_lock` 临界区内完成：
  - profile ownership 的获取与设置；
  - 共享 Playwright context 的获取；
  - `context.new_page()` 与页面超时配置；
  - 新 `BrowserSession` 注册到 `_sessions`。
- 这样 TTL 回收线程无法在 `new_page()` 完成和 `_sessions.add()` 之间进入 idle cleanup，避免新 session 绑定已被关闭的 context。
- 删除 `close()` 中 recovery 之后的锁外 profile release。profile 只由 `_recover_after_failure()` 在状态锁内统一释放，避免新线程 reopen 后被旧 close 路径误释放。
- 保留现有 site lock、TTL timer、manager recovery、shutdown 清理和失败回收语义。

## 故障注入测试

新增两个确定性并发测试：

1. 最后一个旧 session 到期回收时，另一个线程被阻塞在共享 context 的 `new_page()`；断言新 session 注册后 context 未被误关、profile ownership 仍保持且新 session 可用。
2. ACM 与 IEEE 两站点同时 open；断言两个 session 都成功、共享同一个未关闭 context，且 profile ownership 没有竞态丢失。

测试使用 fake clock、fake timer、threading events 和 fake Playwright，不发起外部请求。

## 验证

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_browser_manager.py` | 0 | **28 passed**，5 个既有第三方 `DeprecationWarning` |
| `.venv/bin/ruff check backend/app/paper_discovery/infrastructure/paper_browser_manager.py tests/test_paper_browser_manager.py` | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile backend/app/paper_discovery/infrastructure/paper_browser_manager.py tests/test_paper_browser_manager.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 决策依据

仅增加已有状态锁的保护范围，不引入第二套引用计数或新的资源生命周期模型。`_sessions` 是 idle cleanup 的事实依据，因此把“资源使用开始—session 注册”纳入同一状态边界即可证明 cleanup 不会观察到不完整状态；两站点并发测试同时验证 profile ownership 的串行化。

## 风险与阻塞

- 未验证真实 Playwright 的 context/page close、浏览器进程被杀、SIGTERM、跨进程 profile lock 或真实 ACM/IEEE 登录。
- Task06 的真实 Qdrant、索引切换、确认替换和生产维护窗口仍是独立未通过门禁；本报告不改变 Task06 总体状态。
- 本次没有阻塞。

## 主 Agent 后续动作

1. 审阅本报告及 manager/test diff。
2. 合并本修复与同一浏览器生命周期批次的其他报告后，再运行整组浏览器/导入定向回归。
3. 若独立 reviewer 通过，可在 Spec018 分支创建本地原子提交；不要 push 或自动合并主分支。

## 运行数据

- 开始：2026-09-10 10:11（Asia/Shanghai）
- 结束：2026-09-10 10:22（Asia/Shanghai）
- 总耗时：约 11 分钟
- 模型：按本次临时分派使用 Luna high 子 Agent
- token / 工具调用统计：当前运行环境未提供可靠统计，未伪造填写

## 变更文件

- `backend/app/paper_discovery/infrastructure/paper_browser_manager.py`
- `tests/test_paper_browser_manager.py`
- `docs/sdd/plans/018/artifacts/task-06/browser-manager-concurrency-fix-report.md`

## 进展日志

`.codebuddy/agent-logs/spec-018/task-06/browser-manager-concurrency-fix/20260910-101011.md`
