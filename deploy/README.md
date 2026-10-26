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

PORT=8300 ./deploy/start.sh -d   # 换端口启动（默认 8000）
```

启动后访问 http://127.0.0.1:8000 （换成自定义端口时相应替换）。

## 停止

```bash
./deploy/stop.sh           # 仅停止后台进程
```

## 说明

- 服务默认绑定 `127.0.0.1:8000`（本机）。`HOST` / `PORT` 支持环境变量覆盖（如 `PORT=8300`、`HOST=0.0.0.0`），无需改脚本；如需对外暴露可用反向代理（nginx 等）转发。
- 聊天/模型能力依赖本地 Ollama（`http://localhost:11434`），部署机需自行安装并拉取模型。
- 当前为单进程简单部署，未含进程守护（systemd/supervisor）、HTTPS、容器化；需要时可在此基础上扩展。

## 部署后确认

合并远程分支、重建内存数据库或更换端口后，必须按 [`VERIFICATION.md`](./VERIFICATION.md) 完成 Git 分支、SQLite schema、Ollama、静态资源版本、会话接口和上下文压缩的逐项确认。只检查 `/api/health` 不足以证明会话和压缩功能可用。

## 当前登录会话中的临时后台托管

2026-10-26 本机修复验收发现，工具会话结束后，普通 `nohup` 子进程可能被宿主执行环境清理。当前 8000 服务由 macOS 当前登录会话托管，执行的仍是既有启动脚本；未安装开机启动 plist，仍只监听本机回环地址。

```bash
launchctl submit -l com.researchagent.recovery8000 \
  -o /Users/wjh/ResearchAgent/deploy/run.log \
  -e /Users/wjh/ResearchAgent/deploy/run.log \
  -- /bin/zsh -c 'cd /Users/wjh/ResearchAgent && exec env HOST=127.0.0.1 PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh'
```

同一标签不可重复提交；需要停止这次托管时执行：

```bash
launchctl remove com.researchagent.recovery8000
```

停启后仍须核对端口、健康接口、知识库依赖及真实项目产物，不能以启动命令退出码 0 代替验证。当前修复的重启后证据见 `docs/sdd/plans/038/artifacts/20261026-file-management/final-background-*.json`。这不是系统开机自启方案；重新登录后按需要再启动。
