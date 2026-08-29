# 部署（简单形式）

前端为纯静态资源，由 FastAPI 直接挂载（`/assets` + `index.html`），无需独立构建或单独托管。

## 前置

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 启动

```bash
./deploy/start.sh          # 前台运行，Ctrl+C 停止
./deploy/start.sh -d       # 后台运行，日志见 deploy/run.log
```

启动后访问 http://127.0.0.1:8000 。

## 停止

```bash
./deploy/stop.sh           # 仅停止后台进程
```

## 说明

- 服务绑定 `127.0.0.1:8000`（本机）。如需对外暴露，改 `deploy/start.sh` 的 `HOST`/`PORT` 或用反向代理（nginx 等）转发。
- 聊天/模型能力依赖本地 Ollama（`http://localhost:11434`），部署机需自行安装并拉取模型。
- 当前为单进程简单部署，未含进程守护（systemd/supervisor）、HTTPS、容器化；需要时可在此基础上扩展。
