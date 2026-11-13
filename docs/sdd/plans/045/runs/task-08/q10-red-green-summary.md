# Q10 证据 ① —— 缺陷类红绿测试记录汇总（03 / 04 / 09）

> Spec 045「验收（Q9/Q10）」四类证据之 ①。适用 11 项加固中的**缺陷修复**类：
> 03 采样提到 trace 级、04 `flush()` 出 SSE、09 脱敏 + thinking 上报。
> 汇总者：`backend-tester`（Task 08 后端回归角色）。日期：2026-11-08。

## 0. 纪律与取证方法（先说清楚，避免「编造失败输出」）

- **历史红测输出未落盘**：遍查 `plans/045/task-03/04/05/06` 文档、
  `runs/task-02/evidence.md`、`.codebuddy/agent-logs/spec-045/**`，这三项
  **只有 GREEN 通过数**（task-05「60 passed / 67 passed / 48 passed」、
  task-06「214 passed」、task-03「149 passed」），**没有一条 RED 失败断言原文**。
  task-07 有真实红绿（`13 failed, 2 passed` → `15 passed` 等），但对应的是
  retention / 基准卡片，**不是 03/04/09 项**，不挪用。
- 因此按要求**补一次可复现的 RED→GREEN 取证**：把三项修复点在
  **隔离副本** `/tmp/spec045-redgreen/`（复制当前 `backend/` + `conftest.py` + 既有测试文件）
  中按修复前提交 `6fa877a3`（实现提交 `1b26c76c` 的父提交）的语义做**手术式回退**，
  再跑仓库中**已有的红测文件**，取下真实失败断言；GREEN 则在**当前仓库真实代码**上
  跑同一批用例。
- **仓库 `backend/**` 零改动**：`git diff --stat -- backend/` 为空；隔离副本在 `/tmp`，
  不在仓库内。未改任何业务代码、未改测试断言（RED 用的是仓库里既有的红测文件）。
- 解释器纪律：`source .venv/bin/activate` 在本机被 Conda 覆盖（activate 脚本内
  `VIRTUAL_ENV` 指向 `/Users/wjh/PyCharmMiscProject/.venv`），`python` 实际解析到
  `/opt/anaconda3/bin/python` 并因缺 `fastapi` 误报；**全部命令改用显式
  `.venv/bin/python`**（`fastapi 0.141.1` / `langfuse 4.15.1`），与技能文档「用错解释器
  非代码 bug」一致。

### 复现命令（三条 RED + 一条 GREEN）

```bash
cd /Users/wjh/ResearchAgent
.venv/bin/python /tmp/spec045_build_sandbox.py     # 生成隔离副本并回退（脚本见附录 A）
cd /tmp/spec045-redgreen
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest \
  "tests/observability/test_task05_decoupling.py::TraceSamplingConsistencyTests" -q --tb=short   # RED 03
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest \
  "tests/observability/test_task05_decoupling.py::FlushQueueDecouplingTests" -q --tb=short      # RED 04
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest \
  "tests/platform/test_task06_identity_redaction.py" -q --tb=short                              # RED 09
cd /Users/wjh/ResearchAgent
.venv/bin/python -m pytest tests/observability/test_task05_decoupling.py \
  tests/platform/test_task06_identity_redaction.py -q --tb=short                                # GREEN
```

---

## 1. 加固项 03 —— 采样决策提到 trace / 请求级（F11）

| 项 | 内容 |
|---|---|
| 测试文件 | `tests/observability/test_task05_decoupling.py` → `TraceSamplingConsistencyTests`（2 用例） |
| 修复文件行号 | `backend/app/platform/observability/config.py:47`（`_sample_decision` ContextVar）、`:65-90`（`decide_sampling` / `should_sample` 读缓存）、`:93-99`（`reset_sample_decision`）；`backend/app/platform/observability/trace.py:97`（`start_trace` 调 `decide_sampling()`）；`backend/app/api/routes_chat.py:82`（chat 请求入口落点） |
| 缺陷 | `should_sample()` 每次独立 `random.random()`，各阶段决策不一致撕碎瀑布图 |

**RED（真实输出，`EXIT=1`）**

```
$ /Users/wjh/ResearchAgent/.venv/bin/python -m pytest \
    "tests/observability/test_task05_decoupling.py::TraceSamplingConsistencyTests" -q --tb=short
FF                                                                       [100%]
tests/observability/test_task05_decoupling.py:67: in test_same_trace_decisions_consistent_at_low_rate
    self.assertEqual(
E   AssertionError: 2 != 1 : 同一 trace 内采样决策必须一致，实际 [False, True, False, True, False, True, False, True]
tests/observability/test_task05_decoupling.py:94: in test_start_trace_caches_decision_for_whole_trace
    self.assertFalse(
E   AssertionError: True is not false : start_trace 后应缓存同一采样决策，record_* 不得重新随机
2 failed in 0.38s
```

**GREEN（真实输出，`EXIT=0`）**

```
$ .venv/bin/python -m pytest \
    "tests/observability/test_task05_decoupling.py::TraceSamplingConsistencyTests" -q
..                                                                       [100%]
2 passed in 0.28s
```

**结论：PASS**（先红后绿，断言原文与修复点一一对应）。

---

## 2. 加固项 04 —— `flush()` 移出 SSE 关键路径（F9 / F10）

| 项 | 内容 |
|---|---|
| 测试文件 | `tests/observability/test_task05_decoupling.py` → `FlushQueueDecouplingTests::test_enqueue_flush_is_nonblocking_when_client_hangs` |
| 修复文件行号 | `backend/app/platform/observability/client.py:24-36`（有界 `_flush_queue` + 熔断状态）、`:111-149`（`_do_flush` / 后台单消费者）、`:152-160`（`_ensure_flush_worker`）、`:163-175`（`enqueue_flush` 非阻塞）；三个 SSE 路由改调 `enqueue_flush()`：`backend/app/api/routes_chat.py:191,214`、`routes_kb.py:1097,1113`、`routes_article.py:162,178` |
| 缺陷 | `client.flush()` 同步阻塞在 SSE 生成器内，Langfuse 挂起即转化为用户可见尾包延迟 |

**RED（真实输出，`EXIT=1`）** —— 注入的慢 flush 挂 10s，同步语义原样透传：

```
$ /Users/wjh/ResearchAgent/.venv/bin/python -m pytest \
    "tests/observability/test_task05_decoupling.py::FlushQueueDecouplingTests" -q --tb=short
F                                                                        [100%]
tests/observability/test_task05_decoupling.py:129: in test_enqueue_flush_is_nonblocking_when_client_hangs
    self.assertLess(
E   AssertionError: 10.001411125063896 not less than 0.1 : enqueue_flush 必须非阻塞，不应被 5s flush 拖慢（耗时 10.001s）
1 failed in 10.34s
```

**GREEN（真实输出，`EXIT=0`）**

```
$ .venv/bin/python -m pytest \
    "tests/observability/test_task05_decoupling.py::FlushQueueDecouplingTests" -q
.                                                                        [100%]
1 passed in 0.29s
```

**结论：PASS**（`10.001s → <0.1s` 是真实耗时对比，非 mock 断言）。

---

## 3. 加固项 09 —— 统一脱敏口径 + `raw_events.payload` 上限 + thinking 正文上报（F12 / F13）

| 项 | 内容 |
|---|---|
| 测试文件 | `tests/platform/test_task06_identity_redaction.py`（15 用例） |
| 修复文件行号 | 新增 `backend/app/platform/observability/redaction.py:44`（`redact_text`）、`:73`（`redact_payload`）、`:86`（`bounded_payload`）；`backend/app/platform/observability/spans.py:417-434`（`redact_prompt_messages`）、`:383-390`（thinking 正文写入 `generation.update` 独立字段与 metadata）；`backend/app/memory/repository.py:1161-1163`（三套写入统一脱敏 + 上限 + 统一 ID）；`backend/app/api/routes_conversations.py:980-987`（`_redact_sensitive` 复用同一口径）；`backend/app/platform/observability/request_id.py`（统一 ID 模块） |
| 缺陷 | 三套脱敏口径冲突、payload 无上限、只记 `reasoning_present/reasoning_chars` 不上报 thinking 正文 |

**RED（真实输出，`EXIT=1`）** —— 关键失败断言原文（8 failed / 7 passed，节选 4 条）：

```
$ /Users/wjh/ResearchAgent/.venv/bin/python -m pytest \
    "tests/platform/test_task06_identity_redaction.py" -q --tb=short
FFFF..F.FF...F.                                                          [100%]
tests/platform/test_task06_identity_redaction.py:143: in test_langfuse_input_has_no_plaintext_credentials
    assert marker not in reported, f"Langfuse input 仍含明文 {marker!r}"
E   AssertionError: Langfuse input 仍含明文 'sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789'
tests/platform/test_task06_identity_redaction.py:156: in test_raw_events_payload_has_no_plaintext_credentials
E   AssertionError: raw_events.payload 仍含明文 'sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789'
tests/platform/test_task06_identity_redaction.py:218: in test_oversized_raw_event_payload_is_truncated_and_flagged
    assert len(encoded) <= MAX_RAW_EVENT_PAYLOAD_CHARS
E   assert 50031 <= 4000
tests/platform/test_task06_identity_redaction.py:334: in test_thinking_text_is_reported_in_independent_field
    assert independent == THINKING_TEXT
E   AssertionError: assert None == '先检索再推理，最后汇总证据'
8 failed, 7 passed in 1.18s
```

> 另有 `test_route_layer_redaction_has_no_plaintext_credentials`（:166）、
> `test_redact_prompt_messages_keeps_non_credential_text`（:173）、
> `test_oversized_payload_still_carries_request_id`（:237）、
> `test_same_request_id_in_langfuse_raw_events_and_routing`（:249）同批失败，
> 完整输出保留在 `runs/task-08/red-09-redaction-thinking.log`。

**GREEN（真实输出，`EXIT=0`）**

```
$ .venv/bin/python -m pytest tests/platform/test_task06_identity_redaction.py -q
...............                                                          [100%]
15 passed in 0.90s
```

**结论：PASS**（凭据明文、payload 上限、thinking 正文三类断言均由红转绿）。

---

## 4. 汇总表

| 加固项 | 测试文件 | RED（真实） | GREEN（真实） | 修复文件行号 | 判定 |
|---|---|---|---|---|---|
| 03 采样提到 trace 级 | `tests/observability/test_task05_decoupling.py::TraceSamplingConsistencyTests` | `2 failed in 0.38s`，`AssertionError: 2 != 1 : 同一 trace 内采样决策必须一致，实际 [False, True, …]` | `2 passed in 0.28s` | `config.py:47,65-99`、`trace.py:97`、`routes_chat.py:82` | PASS |
| 04 flush 出 SSE | `tests/observability/test_task05_decoupling.py::FlushQueueDecouplingTests` | `1 failed in 10.34s`，`AssertionError: 10.001… not less than 0.1 : …（耗时 10.001s）` | `1 passed in 0.29s` | `client.py:24-36,111-175`、三路由 `enqueue_flush()` | PASS |
| 09 脱敏 + thinking | `tests/platform/test_task06_identity_redaction.py` | `8 failed, 7 passed in 1.18s`，`Langfuse input 仍含明文 'sk-proj-…'`、`assert 50031 <= 4000`、`assert None == '先检索再推理，最后汇总证据'` | `15 passed in 0.90s` | `redaction.py:44,73,86`、`spans.py:383-390,417-434`、`repository.py:1161-1163`、`routes_conversations.py:980-987` | PASS |

合并 GREEN：`tests/observability/test_task05_decoupling.py` +
`tests/platform/test_task06_identity_redaction.py` → `21 passed in 0.97s, EXIT=0`。

**历史红测输出未落盘**的三项均已补齐可复现的 RED→GREEN 取证；未编造任何失败输出，
未修改仓库业务代码。Q10 证据 ① 判定：**齐全**。

---

## 附录 A：隔离副本构建脚本（`/tmp/spec045_build_sandbox.py`）

复制当前 `backend/` + `conftest.py` + 既有红测文件到 `/tmp/spec045-redgreen/`，再按
`6fa877a3` 语义回退 6 处（每处用字符串锚点精确替换并断言锚点存在）：

1. `config.py::should_sample` → 每次独立 `random.random()`（无 ContextVar 缓存）；
2. `client.py::enqueue_flush` → 同步 `flush()`；
3. `spans.py::redact_prompt_messages` → content 原样返回；
4. `spans.py::record_ollama_generation` → `generation.update(output=…)`（无 thinking）；
5. `repository.py::append_raw_event` → `safe_payload = payload`（明文/无上限/无 ID）；
6. `routes_conversations.py::_redact_sensitive` → 修复前的窄正则。

真实输出日志已归档于本目录：`red-03-sampling.log`、`red-04-flush.log`、
`red-09-redaction-thinking.log`、`green-current-code.log`；隔离副本构建脚本
`/tmp/spec045_build_sandbox.py` 位于 `/tmp`（隔离环境，不入库），正文附录 A 已逐处列明回退内容。
