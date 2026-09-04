# 技术评审：spec-013 本地 LLM 调用观测与性能评估平台

- **评审对象**：`docs/sdd/specs/013-llm-observability-platform.md`
- **评审时间**：2026-09-03 18:11（重试，复用上次中断日志 tech-lead-013-tech-20260903-172356.md）
- **评审角色**：tech-lead（开发主管）｜**模型**：qwen3.8:27b-mlx（本地 Ollama MLX）
- **需求评审结论**：通过（附意见），强制约束 C1–C6；本评审新增约束从 **C7** 起。
- **复核范围**：本次只补做维度 2、维度 3，并复核 task-05 代码落地矛盾；维度 1、4 复用上次分析。

## 维度 1：数据模型一致性 — 通过（附 C1/C2，须先改 spec）

- ✅ 数据模型字段与已实现代码一致：`ollama_direct.py` L24 `OllamaTimings.prompt_eval_ms`、`observability/spans.py` L41/L87 `derive_metrics` 输出 `prompt_eval_ms`、`bench_ollama_routes.py` L127 读 `prompt_eval_ms`，三处统一。
- ❌ **C2（阻塞）**：spec L114 数值型 score 列表写成 `prefill_ms`，与同文档 L104 数据模型字段名 `prompt_eval_ms` 及上述代码矛盾。裁定：以 `prompt_eval_ms` 为准，spec L114 必须改。
- ❌ score 项数：`spans.py` L38-46 `SCORE_METRICS` 为 7 项（ttft/load/prompt_eval/eval/overhead/tokens_per_sec/is_cold_start），spec L114 仅列 6 项、漏 `overhead_ms`、错列 `prefill_ms`。须对齐到 `SCORE_METRICS`。
- ✅ 其余字段（ttft/load/eval/tokens_per_sec/is_cold_start/route）命名与默认值（L110 `is_cold_start` 阈值 200、L111 route 默认 langchain）与代码/配置一致。
- 结论：维度 1 通过，但 C2 属实现前必改的 spec 内部矛盾，须先修订再进实现。

## 维度 4：执行配置（模型/角色）— 通过

- ✅ spec L174/L175：开发主管 & 初级开发 = `qwen3.8:27b-mlx`，与 `MODEL_REGISTRY` L26/L39 及 `AGENTS.md` L104/L105 一致（2026-09-03 已统一 MLX 版）。
- ✅ spec L173 PM = `qwen3.5:9b`，与 L33 基线一致。
- 结论：执行配置已与仓库现状同步，无需修订模型名。

## 维度 2：接口设计的失败语义 — 通过

核对 spec L116-134（端点/接口表 + 9 条边界）与 `observability/safe.py`、`client.py`、`config.py`：

- ✅ **静默降级不冒泡**：spec L121/L133 承诺「埋点失败 no-op 降级、不冒泡到业务」。`safe.py` L18-22 `safe_call` 以 `except Exception` 兜住一切，吞异常仅记 warning 并 `return None`，业务调用方拿不到异常。承诺**成立**。
- ✅ **LANGFUSE_ENABLED=false 零开销**：`config.py` L15-17 `enabled()` 直读 `config.LANGFUSE_ENABLED`（core/config L49 默认 false）；`client.py` L26-27 `get_client()` 在 `enabled()` 为假时**直接 return None，不 import、不构造 Langfuse、不发网络**。`should_sample()` L44-45 同样先 `enabled()` 短路。承诺**成立**。
- ✅ **采样未命中不创建 client**：`should_sample()` L48-50 先判 `rate<=0 → False`、L51-52 `rate>=1 → True`，越界由 `sample_rate()` L36-38 回退 1.0 并 warning。未命中即不创建/不发送。承诺**成立**。
- ✅ **凭证缺失不建 client**：`client.py` L29-33 `credentials_ready()` 为假时 return None 且仅告警一次（`_warned_missing_credentials`）。
- ✅ **SDK 初始化失败降级**：`client.py` L39-51 异常只记 warning、`_client=None`；`flush()` L61-64 亦吞异常。
- ✅ 边界①②③（Ollama 停服/流中断/缺 timings）归 `ollama_direct` 链路，`timings_available` 置位由 L129 约束，安全层只负责观测不冒泡，分层清晰。
- ⚠️ 提示（非阻塞）：`safe_call` 用裸 `except Exception`（L20），符合「观测层兜一切」的硬约束（C6），但需保证所有埋点入口都经 `safe_call` 包裹（见 C7）。
- 结论：维度 2 通过——spec 承诺的失败语义在代码层全部落实，无冒泡风险。

## 维度 3：模块拆分与零侵入 — 通过（附 C7/C8 实施约束）

**（a）分层合理性**：埋点集中在 `backend/app/observability/`（safe/client/config/spans），业务侧（`api/routes.py`、`kb/retrieve.py`、`kb/embed.py`）只 import `record_event / record_ollama_generation` 等命名入口，调用即埋点。`ollama_direct.py` 作为直连客户端独立于 LangChain 链路与 `observability/` 解耦，仅产出 `OllamaTimings`，不反向依赖观测层。分层清晰、职责单一，**通过**。

**（b）是否真零侵入**：
- ✅ 观测层「外挂包裹」：`safe_call`（safe.py L13）吞异常；`get_client`（client.py L19）未启用/缺凭证直接 return None；不修改业务返回值与异常语义。
- ✅ `should_sample()`（config.py L42-53）先 `enabled()` 短路、再判凭证、再判采样率，未命中零动作。
- ⚠️ **kb 侧埋点非纯外挂**：`kb/retrieve.py` L126-174、`kb/embed.py` L91-109 把 `record_event` 内嵌在业务 `try/except` 体内（成功/异常各记一次），未走 `safe_call` 包裹。虽「记录后原样抛出、绝不吞、绝不改变异常类型」（注释 L169/L104），但若 `record_event` 自身抛错会污染业务异常——这正是 C6 要求统一的隐患。

**（c）关键复核：task-05 埋点代码是否已落地（影响 task-05 是否还需开工）**：
- ✅ **task-05 A（聊天链路）已落地**：`routes.py` L154/171/393/418/610/627 已调用 `record_ollama_generation`（含流式/非流式与 KB 生成路径），import 在 L14。
- ✅ **task-05 B（KB RAG）部分落地**：`kb/embed.py` L98/105 记 `kb.embedding`；`kb/retrieve.py` L131/163/170 记 `kb.retrieval`（空集合/命中/异常三分支）。
- ⚠️ **kb.rerank 未独立记录**：`kb/retrieve.py` L162 `result = rerank(question, hits)` 之后 L163 仅把重排耗时**并入 `kb.retrieval`**，无独立 `kb.rerank` 事件。
- 结论：**task-05 的 A 与 B 主体在代码层面已存在**，与 task-05 文档「当前证据：尚未调用」相矛盾。task-05 不应整体从零开工，应收敛为：①补一条独立 `kb.rerank` 事件（满足验收 A7「可见 embedding/检索/重排/生成」，否则 A7 不达标）；②把 kb 侧 `record_event` 纳入 C6 兜底；③复核既有调用是否覆盖全部路径。

## 维度 5：前端回归点 — 通过（本 spec 不触发）

- ✅ `frontend/index.html` 静态资源 `?v=13`（L7/L128-130）。spec-013 不改 `frontend/`（task-07 改 Langfuse 源码，非本项目 frontend），故**无需升级 `index.html` 版本号**。
- ✅ JS class 名 / CSS 选择器一致性：本 spec 不新增前端组件，无新增 class/selector 改动，回归面为零。

## 判定统计

| 维度 | 判定 |
| :--- | :--- |
| 1. 数据模型一致性 | 通过（附 C1/C2，须先改 spec L114） |
| 2. 接口失败语义 | 通过 |
| 3. 模块拆分/零侵入 | 通过（附 C7/C8 实施约束） |
| 4. 执行配置 | 通过 |
| 5. 前端回归点 | 通过（本 spec 不触发） |
| 阻塞项 | 0（C1/C2 为 spec 内部修订，非代码阻塞） |
| 新增约束 | C7、C8（C1–C6 继承需求评审） |

## 强制约束（本评审新增，从 C7 起）

- **C7（补 kb.rerank 独立埋点，task-05 收敛项 / A7 达成前提）**：`kb/retrieve.py` L162 重排后须新增独立 `record_event(name="kb.rerank", ...)` 记录重排耗时与命中数，不得仅并入 `kb.retrieval`。否则验收 A7「可见 embedding/检索/重排/生成」四阶段中「重排」不可见，A7 不达标。
- **C8（统一观测兜底，落实 C6）**：`kb/retrieve.py` L126-174、`kb/embed.py` L91-109 的 `record_event` 当前内嵌业务 try/except，须改经 `observability.safe.safe_call` 包裹（或内部 try/except 吞异常），确保埋点自身异常不污染业务异常语义；与 `routes.py` 的 `record_ollama_generation` 入口保持一致。

> task-05 处置建议：A（聊天链路）与 B（KB RAG）主体埋点**代码层已落地**（routes.py L154/171/393/418/610/627、kb/embed.py L98/105、kb/retrieve.py L131/163/170），task-05 文档「当前证据：尚未调用」已**过时**。task-05 不应整体从零开工，应收敛为：①落实 C7；②落实 C8；③回归核对既有调用是否覆盖全部路径。task-05 文档须同步更新「当前证据」。

## 技术评审结论：通过

- 5 个维度全部通过；无代码层阻塞项；C1/C2 为 spec 内部修订（须实现前完成，非代码阻塞）；C3（需求评审）为 task-05 前置硬卡点（trace UI 可见性冒烟）。
- 新增强制约束 C7、C8 两条，均为 task-05 实施/收敛项。
- 关键复核结论：task-05 的 A/B 埋点在代码层面**已落地**，与 task-05 文档现状描述矛盾——task-05 应收敛而非从零重做；kb.rerank 独立埋点缺失构成 A7 风险（C7）。

