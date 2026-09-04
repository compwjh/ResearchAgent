# Spec 013 Task 05 当前复核

> 关联：[spec-013](../specs/013-llm-observability-platform.md) ｜ 任务：[Task 05](../plans/013/task-05-instrument-chat-kb.md)
>
> 评审角色：Tech Lead ｜ 模型：`qwen3.8:27b-mlx` ｜ 评审性质：当前工作树只读复核
>
> 开始时间：2026-09-03 19:24:00 +0800  
> 结束时间：2026-09-03 19:28:30 +0800  
> 总耗时：4 分 30 秒

## 状态摘要

结论：**Task 05 部分落地，不能按“待执行”从头重做，也不能直接宣告完成。**

已落地的范围：

- 聊天请求和 Agent 聊天路径已统一经 `run_chat()`，支持 `langchain` / `direct` 路由，并在成功、流式失败后记录 Ollama generation；见 `backend/app/api/routes.py:127-185`、`364-430`、`backend/app/services/ollama.py:104-137`。
- KB 问答已建立 `kb-ask` trace，调用检索、构造 prompt、运行生成并记录 `kb.generation`，最后收尾 trace；见 `backend/app/api/routes.py:551-649`。
- embedding 与 retrieval 已有成功/失败阶段事件和耗时；见 `backend/app/services/kb/embed.py:80-110`、`backend/app/services/kb/retrieve.py:117-175`。
- 双链路基准脚本和离线契约测试已落地；Task 05 文档“执行结果”段已有 `scripts/bench_ollama_routes.py` 与 `tests/test_bench_routes.py` 的 7 个用例记录。

尚未完成的范围：

- Task 文档的“当前证据”仍写着“尚未开始”（`task-05-instrument-chat-kb.md:15-21`），与当前工作树冲突，需要在正式执行记录中对账。
- retrieval 内部把 embedding 作为调用链的一部分，但没有独立的 `kb.rerank` 事件；`rerank()` 的异常也只是静默回退原顺序，见 `backend/app/services/kb/retrieve.py:160-175`、`190-215`。
- `record_event()` 虽使用 `safe_call()`，业务层的 `embed_texts()` / `hybrid_search()` 仍直接调用观测函数；如果观测函数本身被替换、mock 或发生非预期异常，缺少业务边界级的安全测试。该项对应技术评审 C8。
- KB 只有一个根 trace、retrieval/embedding/generation 阶段证据；尚未证明真实聊天和真实 KB 请求在 Langfuse 后端形成可查询的完整证据，也未完成 Task 05 的真实链路验收。

## 证据与越界判断

### 已落地文件

当前与 Task 05 直接相关的未提交改动统计为：

- `backend/app/api/routes.py`：183 行新增/修改；
- `backend/app/services/ollama.py`：111 行新增/修改；
- `backend/app/services/kb/embed.py`：27 行新增/修改；
- `backend/app/services/kb/retrieve.py`：93 行新增/修改；
- 另有基准脚本及测试文件，已在 Task 05 执行结果段记录。

### 越界风险

- `backend/app/api/routes.py` 同时包含 Spec 011/012 的 KB 业务逻辑；后续只能在现有接口边界内补观测事件，不得借 Task 05 改变引用、chunker、SSE 或索引语义。
- `backend/app/services/kb/retrieve.py` 的 rerank 能力来自现有可选配置；不得猜测 Spec 014 的最终重排接口，也不得复制 Spec 014 工作树。
- 不应把 `traces` / `observations` 为空单独判为失败：当前 Langfuse v4 `events_only/direct` 模式应以 ingestion 原始事件和 UI/API 可见性作为验收依据，需记录实际部署模式。
- Task 05 的剩余实现若一次修改 `routes.py`、`retrieve.py`、`spans.py` 或测试等超过两文件，违反项目拆分规则，必须拆批。

## 建议的最小后续子任务

以下顺序应在 Spec 013 修复范围确认、Task 04 真实上报门禁通过后执行；每批最多 2 个文件、改动不超过 150 行，并先分派 `junior-dev`。

### 子任务 05-R1：独立 rerank 事件与降级证据

- 文件：`backend/app/services/kb/retrieve.py` + `tests/test_kb_observability.py`。
- 目标：在不改变排序和回退语义的前提下，为 rerank 成功、禁用和异常降级分别记录一次 `kb.rerank` 事件；异常必须继续返回原顺序。
- 验收：事件至少包含 `status`、输入/输出数量、是否启用和降级原因；观测异常不改变 `hybrid_search()` 的业务异常/返回值。

### 子任务 05-R2：聊天与 KB 观测故障隔离覆盖

- 文件：`backend/app/api/routes.py` + `tests/test_kb_ask_trace.py`（必要时另拆聊天测试批次）。
- 目标：补齐 `LANGFUSE_ENABLED=false`、观测 client 抛错、流式中断时的业务结果和 SSE 契约测试；不得修改默认 `langchain` 行为。
- 验收：观测异常不覆盖 Ollama/Qdrant 原异常；`end_trace()` 在正常、空结果、检索失败和生成失败路径均执行。

### 子任务 05-R3：embedding/retrieval 安全边界（若 R1/R2 暴露缺口）

- 文件：`backend/app/services/kb/embed.py` + `tests/test_kb_observability.py`，或 `retrieve.py` + 同一测试文件，二选一批次。
- 目标：把观测调用的安全边界固定为可测试协议；不改变 embedding/retrieval 原异常类型、重试和过滤语义。
- 验收：成功、空集合、网络异常、观测异常各有测试，且密钥、绝对路径、完整敏感 prompt 不进入事件 metadata。

### 子任务 05-R4：真实双链路证据与文档回填

- 文件：`scripts/bench_ollama_routes.py` + `docs/sdd/plans/013/task-05-instrument-chat-kb.md`。
- 目标：在本地服务可用时运行一条聊天和一条 KB 请求，记录 route、trace/event 名称、退出码和结果路径；只回填事实，不伪造 Langfuse UI/数据库视图结果。
- 验收：基准脚本离线测试继续通过；真实运行失败时明确记录阻塞，不将其标为完成。

## 建议测试命令

已执行并通过：

```bash
.venv/bin/python -m pytest -q tests/test_chat_route.py tests/test_kb_ask_trace.py tests/test_kb_observability.py tests/test_bench_routes.py
```

结果：`24 passed in 2.40s`。

后续 R1/R2 完成后至少执行：

```bash
.venv/bin/python -m pytest -q tests/test_chat_route.py tests/test_kb_ask_trace.py tests/test_kb_observability.py tests/test_bench_routes.py
.venv/bin/python -m pytest -q
```

真实验收需另行记录服务前置检查、聊天请求、KB 请求、Langfuse ingestion/event 查询和退出码；在 Task 04 的真实上报门禁未形成稳定可复现证据前，不得开始 R4 以外的扩大性改动。

## 风险与阻塞

- **主要阻塞**：Task 04 的真实 Langfuse 上报门禁与 Task 05 文档状态尚未完成一致化；不能仅凭离线单测进入 Task 06/07。
- **接口风险**：现有测试中部分 mock 仍指向旧的 `build_chat_graph` 入口，虽然当前组合测试通过，后续新增测试应以 `run_chat` 为稳定边界，避免错误地验证未被调用的 mock。
- **数据风险**：真实观测链路需确认当前 Langfuse v4 的事件模式；不要把空的派生视图误判成无上报。
- **工作树风险**：当前存在其他 Spec 的未提交修改；后续子任务必须基于文件级 diff 和允许范围执行，不得 reset、stash、clean、覆盖或复制其他 Spec 工作树。

## 主 Agent 后续动作

1. 将本评审文件作为 Task 05 当前状态的唯一交接证据，并修正 Task 05 文档中的过时“尚未开始”描述。
2. 先完成 Task 04 真实上报门禁的文档回填，再由用户确认 Spec 013 的修复范围。
3. 按 R1 → R2 → R3/R4 顺序逐批分派 `junior-dev`，每批完成后读回文件、运行针对性测试并记录结果。
4. R1/R2 完成且真实 trace/event 证据可复现后，再决定是否开放 Task 06/07。

## 评审结论

**部分完成，需按最小子任务继续；不批准将 Task 05 标记为已完成，也不建议从头重做已落地的聊天、KB generation 和双链路基准代码。**

