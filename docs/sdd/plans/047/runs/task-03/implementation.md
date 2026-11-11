# Task 03 / D5 — Ollama 路由配置漂移修正（执行结果）

> **代行留痕**：本任务由主会话代行。依据 `AGENTS.md`「代行是例外，唯一允许条件是改动不含任何代码文件
> （纯文档 / 配置 / 评审文档）」——本任务改动的是 `.env` 配置 + 服务启停运维，**未改任何 `.py` / `.js` /
> `.html` / `.css` 业务代码文件**，故允许代行。三处留痕：本报告头部、`047-acceptance-review.md`
> 评审记录结论、`docs/sdd/spec-status-changelog.md` 变更日志条目。

## 背景

`.env:12` 的 `OLLAMA_ROUTE=langchain` 覆盖了 `backend/app/platform/config.py:134` 的代码默认值 `direct`
（`config.py:6-8` 的 `load_dotenv()` 在 import 时注入，不属于 OS 进程环境，故 `ps eww` 查不到）。
后果：LangChain 的 `ChatOllama` 丢弃 Ollama 原生 timings，7 个 score 中 6 项为 0、四段 phase span
前三段零长度、`phase:overhead` 吃满整段墙钟（用户 2026-11-09 两张截图所问现象）。

## 操作（按 D5 已确认裁决）

1. **备份**：`cp .env .env.bak.spec047.20261109043121`（911 字节，23 行）。
2. **注释掉覆盖行**（用 `config.py:134` 默认 `direct`，最易回滚）：
   `.env:12` → `# OLLAMA_ROUTE=langchain  # spec-047 D5: 注释掉，使用 config.py:134 默认 direct`
   新进程验证：`.venv/bin/python -c "from backend.app.platform import config; print(config.OLLAMA_ROUTE)"` → `direct`。
3. **停服务**：`./deploy/stop.sh` 已 TERM 旧 PID 65665（脚本清理 `deploy/run.pid` 时因该文件不存在
   报了一次 `safe-delete` 非致命错误，不影响停机；`health=000`、端口无监听确认已停）。
4. **启动**：`nohup env HOST=127.0.0.1 PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh > deploy/run.log 2>&1 < /dev/null &`
   → `/api/health` 200，新 PID 63038，`Application startup complete`、无 ERROR。
5. **真实 E2E**：`POST /api/conversations/messages`（`qwen3.8:27b` / `reasoning_effort=off`）
   → 帧 `meta/progress/token/done`、`status=completed`、`errors=[]`。

## 真实取证（`route-correction-e2e.json`）

| 项 | 结果 |
|---|---|
| trace | `c5dff10a848487988dfa3f5dd26ca7cb`，`route=direct` |
| 四段 phase span | `phase:load` / `phase:prefill` / `phase:decode` / `phase:overhead` 全部存在 |
| 7 项 score | `load_ms=21094.417`、`prompt_eval_ms=5020.079`、`eval_ms=1737.645`、`tokens_per_sec=14.387`、`ttft_ms=26164.094`、`overhead_ms=5.751`、`is_cold_start=1` —— **全部非零** |
| 对照组 | langchain 下 `load_ms/prompt_eval_ms/eval_ms/tokens_per_sec` 恒 0，`phase:overhead` 吃满 39.49s |

> 取证坑（如实留痕）：`GET /api/public/scores?traceId=` 存在读回过滤怪癖（返回 100 条、跨 trace 混入），
> 已按 `score.traceId` 本地过滤得 `scores_matched=7`；另有一条更晚的 `langchain` trace 来自服务重启前的
> 后台评测窗口，未用作 direct 生效证据。初次落盘曾误取该 trace，已用确定 ID 重写本目录 JSON。

## 回滚（无需改代码）

- 文件回滚：`cp .env.bak.spec047.20261109043121 .env` 后按上述 stop/start 重启。
- 即时临时回退：`OLLAMA_ROUTE=langchain env HOST=127.0.0.1 PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`
  （`load_dotenv(override=False)`，shell 环境变量优先）。
- 回滚代价：回到 langchain 的「token 恒 0 / 四段瀑布条前三段为 0 / 观测失效」。

## 边界

- `.env` 在 `.gitignore`，改动**不进版本控制**；未改任何 `.py` / `.js` / `.html` / `.css`。
- `chat_runner.py:150-158` 线上模型强制 langchain 回退**不受影响**；SSE 对外帧型未变。
- 未授权 push / 合 main，`origin/main` 仍 `1b26c76c`。
