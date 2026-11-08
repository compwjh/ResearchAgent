> 关联：[spec-045](../../specs/045-evaluation-observability-hardening.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`待执行`

# Task 05 — 观测采样与上报解耦

## 状态与一句话目标

`待执行`。启用 Langfuse 后，观测不再拖慢用户、采样不再撕碎瀑布图、
SDK 升版退化不再静默发生——让观测变成可以放心常开的旁路。

对应 spec 11 项中的 **03（缺陷修复）**、**04（缺陷修复）**、**05（能力补齐，Q7 并入 P1）**。

## 背景与前置条件

- 必读：[spec-045](../../specs/045-evaluation-observability-hardening.md) F9/F10/F11/F16、Q7；
  [045-observability-module-survey.md](../../notes/045-observability-module-survey.md) 第 4/6 节。
- **F9/F10**：`flush()` 同步写在 SSE 生成器内
  （`routes_chat.py:182,204`、`routes_kb.py:1088,1103`、`routes_article.py:154,169`），
  `client.py:56-64` 阻塞等待且 `LANGFUSE_TIMEOUT=5`；`safe.py:13-22` 只吞异常不消除阻塞。
  **但 Langfuse 当前默认关闭**，这是「一启用就踩」的条件性风险，不得描述为现有故障。
- **F11**：`observability/config.py:40-53` `should_sample()` 每次独立 `random.random()`，
  `record_event` 与各 phase span 各自判断（`spans.py:320,439`）；`start_trace` 不参与决策。
- **F16**：私有符号 `langfuse._otel_tracer`（`spans.py:18`）、
  `generation._otel_span._start_time`（`:35-36,168-181`）、
  `langfuse._client.attributes`（`:47`）；找不到即 fail-open 静默跳过；
  `spec-041:93` 只靠人肉「每次升版跑一次回归」。
- 现有护栏：`tests/observability/test_phase_spans.py:152-475` 13 个测试锁住四阶段精确时间戳、
  decode 口径、fail-open、generation 起点回填；但它们用假 tracer
  （`:111-116`），真 SDK 变化测不出来。
- 前置：task 02 已完成（真实 Langfuse 可用，可观察瀑布图）。

## 数据、配置与接口

- 采样：`ContextVar` 保存单次 trace/请求级决策，`should_sample()` 在同一 trace 内返回同一结果；
  `LANGFUSE_SAMPLE_RATE` 配置语义不变，默认 1.0。
- flush：改为后台队列 + 有界批量 + 超时熔断；队列有上限与丢弃计数告警；
  不改变上报字段、metadata 与 7 个 numeric score 的名称。
- 兼容层：单一模块收拢三处私有符号访问，对外暴露稳定语义
  （`backdate_generation_start()` / `create_phase_span()` 等）；
  符号缺失时**显式降级 + 告警**，而非静默跳过。
- 不改变 `completion_start_time`、四段 phase（`load/prefill/decode/overhead`）的语义与顺序。

## 实施步骤与文件边界

1. 红测：① 采样率 0.1 下同一 trace 各阶段决策一致；
   ② Langfuse 模拟挂起 5s 时 SSE 尾包延迟不增加；
   ③ 私有符号缺失时产生明确告警且主链路正常。
2. 采样决策下沉到 `start_trace`/请求入口，`spans.py` 两处判断改读 ContextVar。
3. `flush()` 从三个路由的 SSE 生成器内移出，改为后台队列消费；
   保留 `end_trace()` 的 ContextVar 复位（`trace.py:28-32,66-109`）。
4. 新建兼容层模块，把 `spans.py` 三处私有访问改为调用该层；补降级告警路径。
5. 补真 SDK 升版冒烟用例（锁 `requirements.lock.txt` 的 `langfuse==4.15.1` 形状）。
6. 回归 `tests/observability/`、`tests/system/test_observability.py`、
   `tests/kb/test_kb_observability.py`；真实瀑布图截图取证（Q10 证据④）。

**文件边界**：`backend/app/platform/observability/{config,trace,spans,client,safe}.py`
+ 新增兼容层模块、`backend/app/api/routes_{chat,kb,article}.py`、
`tests/observability/**`、`tests/system/test_observability.py`。

## 子代理分派

- 含 `.py` 改动 → 必须先 `Task(backend-dev)` 分派（`AGENTS.md:127,128`）。
  建议拆两次：一次采样+flush（同一路由集），一次兼容层（同一 `spans.py`，与前者有重叠，
  需串行或由同一 agent 承接以避免写冲突）。
- 真 SDK 冒烟与并发/流中断测试由 `Task(backend-tester)` 独立执行。
- 最小上下文：本 task 文档 + F9/F11/F16 路径行号 + 「不改上报字段与瀑布图语义」硬边界。

## 边界与明确不做

- **不重构 SDK 接入方式**、不改变上报字段与瀑布图语义（Q7）。
- **不宣称「从根上不会坏」**：私有符号消失后精确时间轴仍可能退化；
  本任务保证「退化可发现（显式降级+告警）」与「修复点唯一（一个文件）」。
  真正根治需上游 SDK 公开支持 `start_time`，或放弃精确瀑布图（产品降级，本 spec 不做）。
- 不做在线实时评测、不做人工标注、不做分数口径统一（P2）。
- 不改 `LANGFUSE_ENABLED` 默认值（仍 `false`，启用由 task 02 在受控环境完成）。
- 不新增第三方依赖；队列用标准库。

## 验收、风险与回滚

| 验收点 | 证据 |
|---|---|
| 采样一致 | 红绿测试 + 0.1 采样率下一条完整四段 trace（Q10 证据③） |
| 尾包不阻塞 | 故障注入下 SSE 完成时间对比，flush 不在关键路径 |
| 退化可发现 | 移除假 tracer 的私有属性后出现明确告警，主链路 200 |
| 瀑布图 | 真实截图四段可见、顺序正确（Q10 证据④） |

风险：后台队列可能丢尾部事件，需有界丢弃计数与告警；
`ContextVar` 在 SSE/线程切换下有残留风险（见 `plans/013/task-05:80`），
必须补并发/流中断测试（与 task 08 协同，不重复实现）。
失败时回滚到任务 02 状态，不影响 task 03/04/06/07。

## 产出物、执行结果与变更日志

### 执行结果（2026-11-08，代码与契约测试已完成）

**状态：代码已完成并通过契约测试；Q10 证据 ③④（真实 trace / 瀑布图截图）待 Task 02 环境就绪后补。**

- 改动：`backend/app/platform/observability/{config,trace,spans,client,__init__}.py`、
  新增 `backend/app/platform/observability/sdk_compat.py`、
  `backend/app/api/routes_{chat,kb,article}.py`、`tests/system/test_observability.py`。
- 落地三项（主会话逐项读回核实，非仅凭测试通过）：
  ① `config.py:44-98` 用 `ContextVar` 缓存 trace/请求级单次采样决策，
     `should_sample()` 全链路共用、`reset_sample_decision()` 复位；
  ② `client.py` 新增有界 `queue.Queue` + 后台 worker + `enqueue_flush()`，
     三个路由的 SSE 生成器内改为 `enqueue_flush()`，`flush()` 保留同步语义供直接调用；
  ③ `sdk_compat.py` 收拢 `langfuse._client.attributes` / `_otel_tracer` /
     `generation._otel_span._start_time` 三处私有访问，缺失时显式告警返回 None，
     `spans.py:46,49` 已改为调用兼容层。
- 主会话读回复跑：
  `tests/observability/ + tests/system/test_observability.py + tests/kb/test_kb_observability.py` → **60 passed**；
  加上 fixtures/platform 共 **67 passed**；
  被改路由的业务链路 `tests/system/test_api.py + test_api_routes_coverage.py` → **48 passed**；
  `ruff check` 观测相关文件 → **All checks passed**。

### 待补（Task 02 环境就绪后）

真实 Langfuse trace ID、四段 phase span 截图、私有符号缺失的告警日志样例、
故障注入前后 SSE 尾包延迟对比数据（Q10 证据 ③④）。
