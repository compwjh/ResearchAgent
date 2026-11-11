# task-03 修复 D：`.env` 路由修正 + 重启与回滚验证

> 关联：[spec-047](../../specs/047-evaluation-p2-and-observability-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`已完成`（主会话代行；`runs/task-03/route-correction-e2e.json`，route=direct、7 项非零） ｜ 对应 spec 表编号 04 ｜ 决策 D5

## 状态与一句话目标

`待执行`。注释掉 `.env:12` 的 `OLLAMA_ROUTE=langchain`，让 `config.py:134` 默认 `direct` 生效；备份 → 重启 → 真实 chat 验 timings/token 非 0 → 记录回滚命令。

## 背景与前置条件

- 只读调查 D 节 + [技术评审 §3 风险 3](../../reviews/047-tech-review.md)：`config.py:8` import 期 `load_dotenv()`、`config.py:134` 默认 `direct`、`.env:11-12` 覆盖为 `langchain`；langchain 下 timings/token 恒 0；`deploy/start.sh` 不 source `.env`、无 `--reload`，须 stop/start 重启。没有任何测试依赖 `.env` 的 langchain 值（`test_chat_route.py:148-168` 反锁默认 direct）。
- 前置：task-02 完成；D5 已拍板「注释掉 + 默认 direct」。

## 数据 / 配置 / 接口增量

- **仅改 `.env`**：注释 `.env:12`（`# OLLAMA_ROUTE=langchain`），用 `config.py:134` 默认 `direct`；**不改任何 `.py`/`.js`、不新增字段**；`.env` 在 `.gitignore`，改动不进版本控制。
- 不新增 / 不改接口。

## 实施步骤与文件边界

1. 备份：`cp .env .env.bak.$(date +%s)`。
2. 注释 `.env:12`。
3. 重启：`./deploy/stop.sh && ./deploy/start.sh -d`（选无活跃 SSE 会话窗口；先 `/api/health` 确认停稳）。
4. 验证：`source .venv/bin/activate` 后 `.venv/bin/python -c "from backend.app.platform import config; print(config.OLLAMA_ROUTE)"` → `direct`；`curl -s http://127.0.0.1:8000/api/health` → 200；真实 chat `completed` 后 `GET /api/public/traces?limit=1` 核对 usage/timings **非 0**；`pytest -q tests/conversation/test_chat_route.py tests/system/test_observability.py`。
5. 记录回滚命令（见下）。

## 子代理分派

- 本 task 为配置 + 运维取证（无业务代码）；由主会话 / `backend-tester` 在授权窗口执行，**本轮评审阶段不执行、不改 `.env`、不重启**。
- 分派最小上下文：技术评审 §3 风险 3 + 本任务。

## 边界与明确不做

- **不改线上模型强制 langchain 回退**（`chat_runner.py:150-158`）；改 `direct` 只影响本地默认链路。
- 不改 `config.py:134` 默认值、不改 `tests/conversation/test_chat_route.py:148-168` 的「默认 direct」断言。
- **重启影响面如实记录**：仅后端 uvicorn 进程（+ 其启动的 reranker）需重启；Langfuse 自托管栈 / 前端静态资源 / `eval_042` 离线 CLI **不受影响**；重启窗口内正在进行的 SSE 会中断。
- `.env` 改动不进版本控制；不 push、不合 main；不写状态台账。

## 验收、风险与回滚

- 验收：`config.OLLAMA_ROUTE == direct` + `/api/health` 200 + 当前部署版本真实 chat 后 trace timings/token 非 0（`retro045:42` 重启后重新取证才作数）+ 7 score 齐全（与 task-01 联动）。
- 风险：重启中断活跃 SSE（选窗口）；`MEASUREMENT:43-44` 回滚代价（回到「对话 500 + token 恒 0」）。
- **回滚 A（完整）**：`cp .env.bak.<ts> .env && ./deploy/stop.sh && ./deploy/start.sh -d`。
- **回滚 B（临时即时，不改文件）**：因 `load_dotenv()` 默认 `override=False`，shell 环境变量优先于 `.env`，可直接 `OLLAMA_ROUTE=langchain ./deploy/start.sh -d` 即时回退。

## 产出物、执行结果与变更日志

- 产出物：`docs/sdd/plans/047/runs/task-03/*.json`（`config.OLLAMA_ROUTE` 输出、真实 chat trace ID、timings/token 非 0 证据、回滚命令记录）、`.env.bak.<ts>` 路径。
- 执行结果：待执行后填写。
- 变更日志：待执行后填写。

