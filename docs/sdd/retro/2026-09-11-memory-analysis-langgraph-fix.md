# 记忆分析 LangGraph 输入修复报告（Spec022 后续缺陷）

## 结果状态和摘要

已完成。LangGraph 内部状态现在声明并统一使用 `messages`；`run_chat` 在没有显式消息列表时，将 `prompt`（优先）或兼容入口 `question` 规范化为 role/content 消息列表。图节点只消费 `messages`，避免 LangGraph 因状态 schema 未声明而丢弃分类 Prompt，进而触发 `CLASSIFIER_FAILED`。

## 改动文件

- `backend/app/chat/domain/chat.py`
- `backend/app/chat/application/chat_runner.py`
- `backend/app/chat/application/chat_graph.py`
- `tests/test_chat_route.py`
- `tests/test_api_routes_coverage.py`

## 针对性验证

- `tests/test_chat_route.py tests/test_task05_memory_analysis_repair.py tests/test_api_routes_coverage.py`：63 passed
- `tests/test_kb_ask_trace.py tests/test_task10_backend.py tests/test_ollama_direct.py`：36 passed
- 相关后端文件 `py_compile`：通过
- `git diff --check`：通过

## 决策依据与边界

`StateGraph(ConversationState)` 只保留状态 schema 中声明的字段。原实现虽向 `graph.stream` 传入 `messages`，但 `ConversationState` 未声明该字段，因此分类 Prompt 在图入口被丢弃。外部 `question` 参数仍由 `run_chat` 兼容，但内部 graph 只接受规范化后的 `messages`；本次未修改 Ollama 启动方式、环境配置、前端或数据库，也未新增 Spec023。

## 风险

直接绕过 `run_chat`、仅传 `question` 给 graph 的旧内部调用不再作为有效输入；已更新仓库内直接 graph 测试，外部 question 入口保持兼容。

