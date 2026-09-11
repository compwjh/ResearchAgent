# Spec024 Task03 后端独立验收报告

## 结果状态和摘要

**PASS**。本轮仅验证后端；指定五个后端测试文件全部通过，迁移成功/八阶段回滚/重启幂等补验通过，项目会话与普通会话 SSE 最小状态检查通过，后端 Python 静态编译与 diff 空白检查通过。未修改业务代码、未写默认数据库、未启动或停止用户服务。

xhigh 口径已与正式 Spec024 同步：显式 `think=true` 且响应含非空 reasoning 与 `evidence_id` 即可判定 provider 支持，server log 为可选审计证据；无响应证据保持 pending/unavailable。本轮实时复采因环境无法访问配置的局域网 Ollama，未新增线上样本，但 Task02 已留存真实探针矩阵。

## 固定验收字段

- 结果：PASS
- P0：无
- P1：无
- P2：无；历史协议审计测试已更新为验证当前 LangChain/direct 推理提取与观测脱敏合同
- 默认数据库：未写入；指定测试均使用 tmp_path 或对 repository path 做临时目录 patch。
- 用户服务：未启动、未停止、未重启。

## 逐条验收证据

### 1. 指定后端定向测试

命令：PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_spec024_backend.py tests/test_conversations_api.py tests/test_ollama_direct.py tests/test_memory_repositories.py tests/test_task09_conversation_filters.py

退出码 0；68 passed, 1 skipped in 2.70s。

覆盖证据包括：推理过滤/NFC/控制字符/20,000 Unicode code point、跨 chunk 模板标记 carry、SSE event envelope 与 event_seq、终态保护与持久序列单调性、真实 probe 接缝与 xhigh evidence、direct off payload、v7 marker/restart、严格 observability metadata allowlist、会话/记忆隔离和既有 conversation filters。

### 2. 临时 v6→v7 成功、八阶段回滚、重启

命令：PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_spec024_protocol.py -k 'v7_cleanup'

退出码 0；9 passed, 4 deselected in 0.26s。

- 成功路径：schema 6 → 7，写入 conversation_history_reset_v1 marker，删除会话及严格依赖，保留 project/memory/system rule/proposal，置空 memory_evidence 会话与消息引用，新增推理字段和 preference。
- 回滚路径：create-metadata、alter-conversations、alter-messages、delete-derived、delete-core、null-evidence、marker、version 八个注入点均恢复原始表计数/schema，marker 不残留。
- Task03 独立测试中的 restart/idempotency 也通过：marker 只存在一条，重启不重复清理或重复写 marker。

### 3. 两类会话 SSE 状态

命令：PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_conversations_api.py -k 'project_and_lazy_conversation_flow or unbound_conversation_does_not_recall_project_memory'

退出码 0；2 passed, 9 deselected in 0.98s。

- 项目会话：HTTP 200；首个可写事件为 meta，末事件为 done；记忆召回/回答生成 progress 状态可持久化，异步记忆分析完成。
- 普通（无项目绑定）会话：HTTP 200；不召回项目记忆；与项目会话共用同一 SSE 路由和后端链路。
- 既有完整 conversation 测试还覆盖 done.status=completed、worker 失败不阻断 SSE、流关闭后 assistant 持久化为 interrupted。

### 4. 真实 probe 证据策略

- Task02 已落盘真实矩阵：qwen3.8:27b-mlx 的 off/low/medium/high 有 HTTP response evidence；xhigh 有非空 thinking 但缺受信 server-log；qwen3.8:27b high 被 provider 明确拒绝；其余档位按模型能力矩阵记录。
- 当前实现逐档请求 /api/chat，5 秒超时、按 model 缓存 5 分钟；只在 HTTP 200 且响应 message.thinking 非空（off 则无 thinking）时记录 evidence_id；不静默把 unsupported 映射为其他档位。
- 本轮实时调用 probe_reasoning_capabilities 对 qwen3.8:27b-mlx、qwen3.8:27b、qwen3.5:9b 均返回 MODEL_CAPABILITIES_UNAVAILABLE，原因为当前执行环境无法访问 .env 指向的 http://192.168.31.180:11434。没有把这次失败写成模型能力结论，也没有保存原始 thinking。

### 5. 静态校验

命令：PYTHONPATH=. .venv/bin/python -m py_compile backend/app/api/routes_conversations.py backend/app/api/schemas.py backend/app/chat/application/chat_graph.py backend/app/chat/application/chat_runner.py backend/app/chat/application/reasoning.py backend/app/memory/models.py backend/app/memory/repository.py backend/app/platform/observability/spans.py backend/app/platform/ollama.py backend/app/platform/ollama_direct.py

退出码 0。

命令：git diff --check

退出码 0；无空白错误。

## 风险与主 Agent 后续动作

1. 在可访问 Ollama 的环境重新执行三模型五档 probe，只记录支持集合、HTTP 状态、字段摘要和 evidence_id，不落盘原始 reasoning；确认 qwen3.8:27b high 继续稳定返回 unsupported。
2. 继续按 Spec 收口流程完成前端 Task04、部署前全量回归和架构师签字；本报告仅覆盖后端 Task03，不替代最终 Acceptance Review。

## 改动文件

- 本轮仅覆盖写：docs/sdd/plans/024/artifacts/task-03/backend-test-report.md
- 未修改 backend/**、frontend/**、默认数据库或服务进程。

## 产物与进展日志

- 验收报告：docs/sdd/plans/024/artifacts/task-03/backend-test-report.md
- 进展日志：.codebuddy/agent-logs/spec-024/task-03/backend-tester/20260912-011208.md

## 开始、结束、总耗时

- 开始：2026-09-12 01:12:10 +0800
- 结束：2026-09-12 01:17:00 +0800（约）
- 总耗时：约 5 分钟

## 模型、token 与工具统计

- 模型：临时 Luna high（按任务要求）
- token：运行时未提供精确统计，未估算
- 工具：只读 shell、pytest、py_compile、git diff-check、apply_patch；未执行 reset/stash/clean/push/merge，未启动子 Agent
