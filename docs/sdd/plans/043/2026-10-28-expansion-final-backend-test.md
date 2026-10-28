# Spec043 Task11 最终后端全量回归

日期：2026-10-28（Asia/Shanghai）  
角色：backend-tester  
最终候选：`9721cbcbbf556e25ebba8de76875540180c02830`  
后端冻结点：`1357494b`  
进展日志：`.codebuddy/agent-logs/spec-043/task-11/backend-tester/20261028-221119.md`

## 结论

**PASS（Task11 后端全量 pytest 与 coverage 门槛）。** 唯一一次最终后端全量运行退出码 **0**：**3183 passed、3 skipped、8 warnings、67 subtests passed**，耗时 **236.93 秒**。coverage 为 **82.32%**，达到 `--cov-fail-under=80` 门槛。

最终候选 `backend` Git tree 为 `3990c80cf64d8f6c791164add245bd33707f1552`，与冻结点相同；`backend` 与 `tests/`（排除 `tests/frontend/`）在工作树没有未提交变更。本报告只签署后端 pytest 与 coverage，不替代真实 API、部署或 Spec043 总体验收。

## 最终命令与运行隔离

执行命令为：

```text
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests \
  --ignore=tests/frontend -p no:cacheprovider -p offline_isolation \
  --basetemp=/private/tmp/spec043-task11-final-backend-20261028/exit0/basetemp-final \
  --cov=backend --cov-report=term-missing:skip-covered \
  --cov-report=xml:/private/tmp/spec043-task11-final-backend-20261028/exit0/coverage.xml \
  --cov-fail-under=80
```

子进程通过 `env -i` 启动，`RUN_E2E` 完全不存在于环境中；预检确认 `PAPER_DISCOVERY_ENABLED=true`、`PYTHON_DOTENV_DISABLED=1`、Langfuse 关闭，在线模型清单及 LLM / Semantic Scholar 密钥为空。Ollama、embedding、reranker 与 E2E 地址均指向无服务的 `127.0.0.1:9`。没有启动真实服务、浏览器、模型或来源，也未读取用户 `.env`。

运行前将 Task10 已成功的临时 socket guard 复制到本轮独立 tmp。它拒绝非 loopback 地址和运行服务端口 `3000、6333、6334、8000、11434、11435`，允许其他受控 loopback 与 Unix socket。数据库、KB/Qdrant、下载目录、浏览器 profile、HOME、TMP、XDG/Python 缓存、pytest basetemp 及 coverage 均在 `/private/tmp/spec043-task11-final-backend-20261028/exit0/`。没有全局设置 `MEMORY_DIR`；仓库根 conftest 隔离 markdown memory，临时插件只对非默认值断言用例 patch config `MEMORY_DIR`。

运行前单独执行 `tests/e2e/test_research_lifecycle_e2e.py`，退出码 0，**2 skipped**；两项均由既有条件“需设置 `RUN_E2E=1` 并先启动 `:8000`”跳过。完整全量运行后，为明确第三项原因，按同一离线隔离环境对 Ollama 真实调用用例做了一次独立 `-rs` 验证（未重跑全套）：`tests/research/test_ollama_direct.py::RealStreamCallTests::test_real_stream_yields_tokens_and_returns_result` 退出码 0，输出 `SKIPPED [1] tests/research/test_ollama_direct.py:401: Ollama 不可达或无可用模型，跳过真实调用`。这与本轮无服务的 loopback endpoint 一致。全量原始结果及 coverage 未改写；逐项 skip 证据见 `ollama-skip-verification.txt` 和 `/private/tmp/spec043-task11-final-backend-20261028/exit0/logs/ollama-skip.log`。

8 条 warning 均为依赖弃用提示（SWIG 与 jieba 的 `DeprecationWarning`）。

## 结果与可复核材料

- 完整 pytest 原始输出：`/private/tmp/spec043-task11-final-backend-20261028/exit0/logs/pytest-full.log`
- 完整运行退出码：`/private/tmp/spec043-task11-final-backend-20261028/exit0/logs/pytest-full.exit`（`0`）
- E2E skip 预检输出：`/private/tmp/spec043-task11-final-backend-20261028/exit0/logs/e2e-skip.log`
- 运行环境预检：`/private/tmp/spec043-task11-final-backend-20261028/exit0/logs/env-preflight.txt`
- 原始 coverage 数据：`/private/tmp/spec043-task11-final-backend-20261028/exit0/.coverage`（118,784 bytes，SHA-256 `f964bfee5cdb8929df6e1749779d52fdcbdaa6fb950cebec3a7b5d41b1fdfd6e`）
- Coverage XML：`/private/tmp/spec043-task11-final-backend-20261028/exit0/coverage.xml`（line-rate `0.8232`）
- Coverage source 文件清单：`/private/tmp/spec043-task11-final-backend-20261028/exit0/coverage-source-files.txt`（210 个文件）
- 本轮 source manifest：backend 与非前端 tests 共 489 个 tracked 文件；SHA-256 `12ec7c6b133d2e97d60fa202e168a9f1a42f8df1aea4abc431bdd1f084094e16`。另有 Git `backend` tree hash `3990c80cf64d8f6c791164add245bd33707f1552`，与冻结点一致。
- 脱敏摘要、可复现命令和运行 stamp：见 [`task-11-runs/final-regression/backend/summary.md`](task-11-runs/final-regression/backend/summary.md)、[`command.sh`](task-11-runs/final-regression/backend/command.sh)、[`run-stamp.txt`](task-11-runs/final-regression/backend/run-stamp.txt)。原始输出与 `.coverage` 保存在独立 tmp，不复制进仓库。

## VERIFICATION REPORT

- **Build：** 未运行（本委托仅要求后端全量 pytest）。
- **Types：** 未运行。
- **Lint：** 未运行。
- **Tests：** PASS（3183 passed、3 skipped、8 warnings；67 subtests passed）；coverage 82.32%，80% 门槛达到。
- **Security：** 未运行。
- **Diff：** PASS；冻结点与当前候选的 backend tree 一致，且 backend 与非前端 tests 工作树无差异。
- **部署 / 真实 API：** 未运行；本角色没有启动服务或调用真实服务。
