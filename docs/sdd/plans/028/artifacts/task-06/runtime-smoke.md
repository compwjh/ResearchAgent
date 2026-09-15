# Spec028 Task06 运行时 Smoke

日期：2026-09-16（Asia/Shanghai）

## 启动

- 命令：`PORT=8500 RERANKER_ENABLED=false ./deploy/start.sh`
- 地址：`http://127.0.0.1:8500`
- 结果：FastAPI 启动完成，Uvicorn 监听 8500；Reranker 按收口配置禁用并走 RRF 降级。

## 浏览器证据

使用真实 Codex In-app Browser 刷新 `http://127.0.0.1:8500/#research-view` 后确认：

- 页面标题为 `ResearchAgent`，Research 视图可见。
- 实际加载 `/assets/app.js?v=50`、`/assets/research-tasks.js?v=4`。
- 研究任务列表、研究详情、创建研究会话区域均可渲染。
- 最新 DOM 中包含恢复入口 `research-task-recover-button` 和全文获取区域 `research-acquisition-section`。
- 页面无新增 JavaScript 错误；已有通知连接中断提示按现有 SSE 降级语义展示。

## 限制

本次只完成启动、页面加载和关键 DOM 入口 smoke；没有创建新研究任务、执行真实 Ollama 推理或强制终止进程，因此不把 pause/resume/approval/cancel/recover 的真实点击旅程、跨进程恢复或全文下载写成已通过。
