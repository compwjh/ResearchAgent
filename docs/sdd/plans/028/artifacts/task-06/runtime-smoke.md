# Spec028 Task06 运行时 Smoke

日期：2026-09-16（Asia/Shanghai）

## 启动

- 命令：`PORT=8500 RERANKER_ENABLED=false ./deploy/start.sh`
- 地址：`http://127.0.0.1:8500`
- 结果：FastAPI 启动完成，Uvicorn 监听 8500；Reranker 按收口配置禁用并走 RRF 降级。

## 浏览器证据

使用真实 Codex In-app Browser 刷新 `http://127.0.0.1:8500/#research-view` 后确认：

- 页面标题为 `ResearchAgent`，Research 视图可见。
- 实际加载当前无缓存静态资源（首页返回 `Cache-Control: no-cache`）；历史页面 smoke 中的资源版本仅作记录。
- 研究任务列表、研究详情、创建研究会话区域均可渲染。
- 最新 DOM 中包含恢复入口 `research-task-recover-button` 和全文获取区域 `research-acquisition-section`。
- 页面无新增 JavaScript 错误；已有通知连接中断提示按现有 SSE 降级语义展示。

## 限制

本次不创建新研究任务、不执行真实 Ollama 长推理；持久化 lease/checkpoint 恢复、终态保护和 API/UI 状态合同由 Spec028 定向测试覆盖。

## 2026-09-16 收口复核（已重启）

本轮重启 8500 服务后，经沙箱外只读 curl 复核，`/api/health`、`/`、`/api/research-scheduler/status` 均 HTTP `200`、退出码 `0`，未知 `/api/*` 仍返回 404；scheduler 返回 queue/quota/safety 聚合，不泄露租约 token。In-app Browser 对本机地址可能返回 `ERR_BLOCKED_BY_CLIENT`，属客户端环境限制。
