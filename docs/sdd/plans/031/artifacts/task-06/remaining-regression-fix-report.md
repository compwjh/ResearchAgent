# Spec 031 Task06 剩余回归修复报告

## 执行信息

- 角色：backend-dev
- 模型：Luna high（临时分派）
- 开始：2026-09-17T10:32:00Z（约）
- 结束：2026-09-17T10:40:00Z
- 总耗时：约 8 分钟
- 范围：仅处理 Task06 全量回归暴露的两个精确失败；未修改生产业务代码、未 commit、未 push。

## 根因

1. `test_worker_respects_frozen_window` 没有固定 `COMPACTION_SUMMARY_MODE`。测试默认模式为 `llm`，因此在 Ollama 不可达或摘要输出不确定时，不能稳定验证“冻结窗口会写入段”的契约。
2. 压缩 worker 在生产中会把 `flush_memories` 放到 daemon 线程执行。原测试没有关闭这个与冻结窗口无关的 best-effort 副作用，后续知识库测试可能在断言期间看到该后台线程创建的模型调用，表现为 `create_chat_model` 被调用多次。知识库请求本身的 LangGraph 链路仍只创建一次模型；没有放宽“一次创建”断言。

## 改动

- `tests/test_conversation_compaction_summary.py`
  - 为冻结窗口和空会话 worker 测试固定 `COMPACTION_SUMMARY_MODE=rule`，保证测试验证的是窗口/持久化契约而非真实模型可用性。
  - 增加测试级 autouse fixture，将 `FLUSH_MEMORIES_ENABLED` 设为 `False`。该文件不测试记忆 flush；flush 行为由 `tests/test_spec038_memory_compaction.py` 独立覆盖。
  - 保留生产 fail-open 与异步 flush 行为，不通过放宽 KB 断言掩盖问题。
- `tests/conftest.py`
  - 新增 autouse fixture，在每个测试前后调用 `conversation_service.stop_all_workers()`，清理进程级缓存的演进/分析 worker。
- `tests/test_memory_repositories.py`
  - 仓储 checkpoint/分页测试统一关闭测试不覆盖的 post-checkpoint 模型抽取副作用；该测试文件验证的是 durable checkpoint，不是模型抽取。

## 验证

### 初始复现

```text
.venv/bin/python -m pytest -q \
  tests/test_conversation_compaction_summary.py::test_worker_respects_frozen_window \
  tests/test_kb_routes.py::AskTests::test_streams_tokens_and_citations
```

- 退出码：1
- 结果：冻结窗口通过；KB 测试在同一进程中观察到 `create_chat_model` 5 次，确认是前一测试异步 flush 的跨测试污染，而非 KB 生产路径重复创建。

### 修复后定向测试

```text
.venv/bin/python -m pytest -q \
  tests/test_conversation_compaction_summary.py \
  tests/test_kb_routes.py::AskTests::test_streams_tokens_and_citations
```

- 退出码：0
- 结果：`15 passed`。

### 跨测试顺序回归

```text
.venv/bin/python -m pytest -q \
  tests/test_conversation_compaction_summary.py \
  tests/test_memory_repositories.py \
  tests/test_kb_routes.py
```

- 退出码：0
- 结果：`70 passed`；KB 单模型创建断言在包含 1001 条事件的演进测试后仍通过。

```text
.venv/bin/python -m pytest -q \
  tests/test_spec038_memory_compaction.py \
  tests/test_memory_analysis_repair.py \
  tests/test_conversations_api.py
```

- 退出码：0
- 结果：`42 passed`；显式 worker 与记忆分析测试未被全局清理破坏。

## 风险与阻塞

- 本修复只改变测试隔离，不改变生产中的异步记忆 flush、LLM 摘要降级或 KB 模型创建逻辑。仓储测试中的 post-checkpoint 抽取仅是测试替身，不改变运行时代码。
- Task06 的完整回归、Task02 多实例/证据门禁问题仍由主 Agent 按原 Task06 报告处理；本报告不将其标记为已解决。

## 主 Agent 后续动作

1. 将本报告与测试改动纳入 Task06 工作树审查。
2. 重新运行 Task06 要求的唯一全量回归；确认 KB 单模型创建断言和 compaction 冻结窗口均稳定通过。
3. 若全量回归仍有失败，继续按真实失败根因定向修复，不放宽断言。
