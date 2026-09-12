# Spec027 Task06 部署与运行时 Smoke

## 启动证据

- 命令：`PORT=18081 RERANKER_ENABLED=false ./deploy/start.sh`（前台）
- 退出方式：验证完成后 Ctrl-C；日志显示 `Application startup complete`、`Uvicorn running on http://127.0.0.1:18081`，并正常 `Shutting down` / `Application shutdown complete`。
- 默认 8000 首次后台尝试在沙箱中被 `operation not permitted` 阻断；18080 已被 PID 61835 占用，因此使用脚本支持的可用端口 18081。未声称 8000 已部署。

## HTTP 结果

| 请求 | 结果 |
|---|---|
| `GET http://127.0.0.1:18081/api/health` | HTTP 200，JSON `status=ok`，列出 11 个 Ollama 模型 |
| `GET http://127.0.0.1:18081/` | HTTP 200，HTML 51952 bytes |
| `GET http://127.0.0.1:18081/api/research-tasks` | HTTP 200，`research_tasks=[]`、`next_cursor=null` |
| `POST http://127.0.0.1:18081/api/research-tasks` body `{}` | HTTP 400，`PLAN_VALIDATION_FAILED` 稳定错误体 |

首页源码进一步确认：`data-view="research"`、`mode-select` 的 `research` 选项、深度研究工作台和 `/assets/research-tasks.js?v=1` 均存在。

## 真实依赖结果

- `OLLAMA_BASE_URL=http://127.0.0.1:11434 ... task05-close-probe.py`：`/api/tags` 成功；最小 chat 请求 3 秒超时，记为环境阻断。
- USENIX 最小 source smoke：`USENIX_UNAVAILABLE`。
- DBLP 最小 source smoke：`DBLP_NETWORK_ERROR`，整体 `DBLP_UNAVAILABLE`。
