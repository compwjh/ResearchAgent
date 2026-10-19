# Spec016 最终业务回归与本地运行验收

> 状态：全仓回归与本地 HTTP smoke 均已通过；Ollama 推理和浏览器端到端按环境条件跳过。

## 测试基线

- 全仓业务源码候选：`37bb056`。测试期间及之后只有文档迁移提交 `83fadbe`、`4b14130`；业务源码保持冻结。
- Python：`/workspace/researchagent-venv311/bin/python`，Python 3.11.16，依赖已安装。
- 命令：`/workspace/researchagent-venv311/bin/python -m pytest -q -o faulthandler_timeout=60 --junitxml=.sdd/runtime/closure-qa/business-final.xml`（stdout/stderr 重定向至下方日志）。
- 由 root 权限入口启动；本 agent 独立读取 stdout/JUnit，并从 JUnit 抽查 skip 原因。
- stdout/stderr：`.sdd/runtime/closure-qa/business-final.out`。
- JUnit：`.sdd/runtime/closure-qa/business-final.xml`。
- 输出摘要：`3275 passed, 3 skipped, 341 warnings, 546 subtests passed in 386.52s (0:06:26)`；JUnit 统计 3824 cases，0 errors、0 failures、3 skipped。
- Full pytest shell 退出码：`0`。

## 跳过项与外部边界

- 两个 `tests.e2e.test_research_lifecycle_e2e` 案例要求 `RUN_E2E=1` 且先启动 `:8000` 后端，本次未启用浏览器端到端环境。
- `tests.research.test_ollama_direct.RealStreamCallTests.test_real_stream_yields_tokens_and_returns_result` 因 Ollama 不可达或没有可用模型而跳过。
- 因此本次没有声称真实 Ollama 推理已验收；本地 `/api/models` 的真实状态见下文。
- 补充证据：root 在较早候选 `281e933` 的 TestClient SSE 网络探针为 `1 passed in 1.54s`；最终全仓回归也覆盖该测试。工具域 382 项全绿，Ruff 与 compileall 通过（见 `.sdd/runtime/closure-qa/` 对应输出）。

## 本地服务验收

- Smoke helper：`.sdd/runtime/closure-qa/test_live_service.py`（150 行，Git 忽略）；实际命令 `/workspace/researchagent-venv311/bin/python -m pytest -q .sdd/runtime/closure-qa/test_live_service.py --junitxml=.sdd/runtime/closure-qa/service-final.xml`，exit `0`，`1 passed in 2.34s`。原始输出在 `service-final.out`。
- Helper 通过 `setsid deploy/start.sh -d` 启动官方服务，环境为 `HOST=127.0.0.1 PORT=56483 RERANKER_ENABLED=false PYTHONDONTWRITEBYTECODE=1`；启动输出记录 PID `274758`。服务保留运行。
- 首页 `http://127.0.0.1:56483/` 返回 HTTP `200`（62,488 bytes）；`/api/health` 返回 HTTP `200`，`status=ok`，配置模型 `qwen3.8:27b`，`models=[]`。
- `/api/models` 返回 HTTP `200`，`current=null`，local 和 online 两组均为空；无可用模型，未执行或模拟推理。Reranker 已禁用，按 RRF 降级运行。
- 首页响应与当前 `frontend/index.html` 字节完全一致（62,488 bytes，SHA-256 `9a2e714e…78d7e14`，无运行期注入）；12 个版本化静态资源引用都存在于当前 frontend tree，实际 GET 均为 HTTP `200`：`app.js?v=53/54/57`、`styles.css?v=53/56`、`conversation-research.js?v=1`、`kb-inspection.js?v=23`、`processing-tree.js?v=1`、`research-session-ui.js?v=2`、`research-tasks.js?v=15`、`vendor/marked.min.js?v=13`、`vendor/purify.min.js?v=13`。逐项 URL 与字节数见 `live-service-assets.json`；其中 helper 的聚合 `asset_versions` 字段格式不正确，本报告以资源列表的实际 URL 为准。
- 只读 SQLite 检查路径 `data/memory/memory.sqlite3` 确认 schema v8，并包含 `conversations`、`messages`、`conversation_segments`、`conversation_compaction_jobs` 等表；完整结果见 `live-service-memory.json`。

## 收尾判断

全仓 pytest 的可执行案例和本地服务 HTTP smoke 均通过。模型推理因无本地/线上模型未验收；两项浏览器 E2E 需独立启动条件，本次跳过。
