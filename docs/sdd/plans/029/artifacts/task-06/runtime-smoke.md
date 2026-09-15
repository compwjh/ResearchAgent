# Spec029 Task06 运行时 Smoke

日期：2026-09-16（Asia/Shanghai）

## 启动

- 命令：`PORT=8500 RERANKER_ENABLED=false ./deploy/start.sh`
- 地址：`http://127.0.0.1:8500`
- 结果：FastAPI 启动完成，Research 页面真实加载；Reranker 按配置禁用。

## 浏览器证据

真实浏览器刷新 Research 页面后确认：

- 研究任务列表、详情和创建表单均可访问。
- 实际加载 `/assets/app.js?v=50`、`/assets/research-tasks.js?v=4`。
- 页面 DOM 包含全文获取区域 `research-acquisition-section`，可由任务详情按候选快照显示。
- 页面没有新增 JavaScript 错误。

## 尚未执行

真实公开 PDF 下载/导入/索引、浏览器候选增删与显式确认、登录等待/失败重试、全文证据升级和删除重验证尚未执行；因此 Spec029 仍保持实施中，不能把自动化合同测试代替真实全文证据。
