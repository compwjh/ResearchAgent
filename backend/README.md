# Backend

后端采用分层结构，业务代码位于 `app/` 包内：

- `app/main.py`：FastAPI 应用装配和静态资源入口
- `app/api/`：HTTP 路由和请求 schema
- `app/core/`：配置和基础设施
- `app/domain/`：领域状态和数据模型
- `app/services/`：外部服务适配器，例如 Ollama
- `app/graphs/`：LangGraph Agent 节点和工作流

兼容启动入口为 `backend.main:app`，推荐使用 `app.main:app`。
