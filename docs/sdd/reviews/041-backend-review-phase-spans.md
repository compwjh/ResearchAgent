# spec-041 T-E 后端评审报告：spans.py 补 5 阶段子 span

- 评审角色：backend-reviewer
- Spec / 任务：spec-041 / T-E（spans.py 补 4 阶段子 span）
- 分支：feature/spec-041-langfuse-trace-detail（未切、未提交）
- 评审范围：`backend/app/platform/observability/spans.py`、`tests/observability/test_phase_spans.py`
- 评审方式：只读；逐行核对源码 + 实际读取 `.venv` 内 langfuse 私有符号 + 实跑 pytest/ruff
- 关联评审：T-B（input 全量）已通过；本轮只评 T-E 新增项

## 结论

**有条件通过（Conditional Pass）**

存在 1 个必改项（HIGH，fail-open 缺口），不阻塞合并但须在合入前修复。私有 API 使用经核实确属必要，无公开替代。时间戳、单测质量、越界检查均合规。

## 逐条核对

### 1. 私有 API 使用的必要性与封装边界
- (a) 必要性：**确认必要**。实测 `.venv/lib/python3.11/site-packages/langfuse/_client/client.py:837+` 的 10 个 `start_as_current_observation` overload 均未提供 `start_time` 参数；仅 `start_as_current_span`（client.py:1342/1714）支持 `start_time`。文档所述「SDK 主路径下 generation 主体 startTime≈endTime、需绕开主路径」属实。
- (b) 封装兜底：**部分缺失，见必改项**。
  - `_otel_tracer` 取用：`spans.py:157` `getattr(langfuse, "_otel_tracer", None)` + `None` 早退（158-159），安全降级 ✓。
  - `create_span_attributes` 取用：`spans.py:34` 为**模块顶层硬导入** `from langfuse._client.attributes import create_span_attributes`。该符号为私有（`langfuse._client.attributes` 模块 + `create_span_attributes`），一旦未来 SDK 升级路径/符号变动，整模块 `ImportError`，`record_ollama_generation`/`record_event`/`record_routing_observation`/`redact_prompt_messages` 全部不可用，且**不归 `safe_call` 兜底**（函数根本不存在，调用点直接崩）。这与模块 docstring（spans.py:153-155「任何意外都不会冒泡到业务」）及 `safe.py` 硬约束（「埋点的任何异常都不得冒泡到业务」）矛盾。
  - 补充核实：`create_span_attributes` 返回已过滤 `None` 的 dict（attributes.py:91-113），`span.set_attributes(dict)` 用法正确 ✓。

### 2. 时间戳正确性
4 阶段推导式与基准逐字一致：
- `phase:load`      = [s, s+load_ms]                          → spans.py:168 ✓
- `phase:prefill`   = [s+load_ms, s+load_ms+prompt_eval_ms]   → spans.py:171-172 ✓
- `phase:decode`    = [s+first_token_ms, s+first_token_ms+eval_ms] → spans.py:176-177 ✓
- `phase:overhead`  = [s+first_token_ms+eval_ms, s+client_wall_ms] → spans.py:181-182 ✓
- `first_token` 不成 span，写入 generation 主体 `completion_start_time` → spans.py:280 / 调用 spans.py:297 ✓
- `started_at=None` 回退：`base = now - client_wall_ms`，与 `completion_start_time` 既有回退（spans.py:252）**同公式**，两条轴方法论一致 ✓
- 残余（LOW，见可选建议）：`started_at=None` 时 `_report_phase_spans` 内 `base` 取 `now`（spans.py:163）与 `completion_start_time` 的 `now`（spans.py:252）为两次独立调用，正常（传入 started_at）路径完全对齐，仅 None 边缘路径有微秒级轴错位。

### 3. fail-open（最高优先级）
- 调用位置：`_report_phase_spans` 在 `with ... as generation:` 块内（spans.py:297），整体处于 `safe_call(_report)`（spans.py:299）内 ✓
- tracer 缺失：`getattr(...,None)` + 早退 ✓（157-159）
- 单阶段隔离：每阶段独立 `try`（187），`except Exception`（201-205）记 warning，不阻断其余阶段与 generation ✓
- span 泄漏防护：`end_on_exit=False` 且 `span.end(end_time=...)` 置于 `finally`（198-200），`set_attributes` 抛错也必结束 ✓
- **缺口**：见必改项 #1（`create_span_attributes` 硬导入破坏模块级 fail-open）。

### 4. 单测质量（regression-guard 边界 12）
文件 `tests/observability/test_phase_spans.py`（227 行），直接 `import` 被测模块（删除即 ImportError，无静默 skip 守卫）✓。
- `test_four_phase_child_spans_created_with_exact_start_end_times`：用 `InMemorySpanExporter` 真实捕获，断言 4 个 span 名称集合相等（149-153），`start_time`/`end_time` 纳秒与**独立公式** `_expected_phases` 推算值 ±1ns（155-168，非恒真），并断言 `langfuse.observation.type=span`（170-173）✓
- `test_generation_completion_start_time_equals_started_at_plus_first_token`：断言 `completion_start_time == started_at + first_token_ms` 精确相等（180-184）✓
- `test_one_phase_failure_does_not_block_others_or_generation`：注入 `phase:decode` 抛 `RuntimeError`，断言其余 3 span 仍生成且 generation 仍上报（186-208）✓ 覆盖单阶段异常 fail-open
- `test_tracer_blows_up_is_fail_open_and_generates_no_child_spans`：mock tracer 抛异常，断言 0 child span 且 generation 仍上报、不冒泡（210-226）✓ 覆盖整 tracer 异常 fail-open
- 结论：断言均非恒真、无依赖缺失静默跳过、直接断言纳秒值、覆盖两种 fail-open 场景，质量优秀。

### 5. 未越界
- `OBS_MAX_INPUT_CHARS` / `obs_config.max_input_chars()`：用法未改（spans.py:278）✓
- 采样率语义：`should_sample()` 仍做门控（spans.py:239）✓
- OTel SDK 版本：diff 未变动依赖 ✓
- 业务对话逻辑：未改动 ✓
- `redact_prompt_messages` 签名：`(messages: Sequence[Dict[str,str]]) -> List[Dict[str,str]]` 不变（spans.py:314）；content 现按 spec-041 用户裁决原样保留，非边界破坏 ✓

## 必改项清单

1. **[HIGH] 私有符号 `create_span_attributes` 顶层硬导入破坏模块级 fail-open**
   - 位置：`backend/app/platform/observability/spans.py:34`
   - 问题：私有导入在模块加载期，缺失即整模块 `ImportError`，使 `record_ollama_generation` 等全部不可用，不归 `safe_call` 兜底，违反本模块 fail-open 硬约束。
   - 修复方向：改为受保护导入 + `None` 兜底，
     ```python
     try:
         from langfuse._client.attributes import create_span_attributes
     except ImportError:  # 私有符号随 SDK 升级变动时，不应拖垮整个观测模块
         create_span_attributes = None
     ```
     并在 `_report_phase_spans` 内：`if create_span_attributes is not None:` 才 `span.set_attributes(...)`（属性仅影响 dual 模式落 observations，缺失时仍应照常创建带精确起止时间的 OTel child span 与 generation 上报）。

## 可选建议

- **[LOW] 共享 `started_at=None` 回退的 `base` 取点**：将 `completion_start_time` 与 `_report_phase_spans` 共用的 `base = now - client_wall_ms` 计算收敛到同一处（如 `record_ollama_generation` 先算一次 `base` 并传给 `_report_phase_spans`），避免 None 边缘路径下两条时间轴因两次独立 `now()` 产生微秒级错位。正常（传入 started_at）路径已完全对齐，故仅 LOW。

## 实测结果（本机）

- `pytest tests/observability/test_phase_spans.py -q --basetemp=./.tmp-pytest`：
  `.... [100%]` → **4 passed in 0.46s**
- `.venv/bin/python -m ruff check backend/app/platform/observability/spans.py tests/observability/test_phase_spans.py`：
  **All checks passed!**

## 签字

- 评审人：backend-reviewer（只读评审，未改代码/spec，未 commit/push）
- 日期：2026-09-21
-  verdict：有条件通过（1 个 HIGH 必改项须在合入前修复）
