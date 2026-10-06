# spec-041 后端回归报告（T-B input 全量 + T-E 阶段子 span）

- 角色：backend-tester（后端回归/验收）
- 分支：feature/spec-041-langfuse-trace-detail（未切分支、未提交）
- 环境：仓库根 `.venv`（/Users/wjh/ResearchAgent_codebuddy/.venv）；pytest 一律带 `--basetemp=./.tmp-pytest*`（broker 沙箱拒绝 /tmp）
- 范围：`backend/app/platform/observability/spans.py`、`tests/observability/`、`tests/test_observability_prompt_input.py`，以及本次 diff 触及的 `tests/test_chat_route.py`、`tests/test_kb_ask_trace.py`、`tests/test_system_rule_backend.py`
- 结论：**定向回归全绿（675 passed / 1 failed-环境）**；全量回归因沙箱 SIGTERM 未跑完（详见 §3）

---

## 1. 定向回归（真实输出）

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/observability -q --basetemp=./.tmp-pytest` | **5 passed in 0.60s**（含 T-E 新增 5 例） |
| `.venv/bin/python -m pytest tests/test_observability.py tests/test_observability_fixtures.py tests/test_observability_prompt_input.py -q --basetemp=./.tmp-pytest2` | **37 passed in 0.89s**（含 T-B Input 全量测试） |
| `.venv/bin/python -m pytest tests/test_kb_observability.py tests/test_spec031_shadow_observation.py -q --basetemp=./.tmp-pytest3` | **24 passed in 2.74s** |
| `.venv/bin/python -m pytest tests/test_chat_route.py tests/test_kb_ask_trace.py tests/test_system_rule_backend.py -q --basetemp=./.tmp-pytest-mod` | **27 passed in 4.36s**（本次 diff 触及的 3 个测试文件） |

> 说明：任务单里提到的 `tests/backend` **目录不存在**，故以 observability 相关测试文件替代；`tests/test_observability_prompt_input.py` 存在并已跑（37 passed 批次内）。

### T-E 新增用例（tests/observability/test_phase_spans.py，5 例，全通过）
1. `test_four_phase_child_spans_created_with_exact_start_end_times` — InMemorySpanExporter 真实捕获 4 个 child span，纳秒级 start/end 与独立公式 ±1ns 比对，断言 `langfuse.observation.type=span`
2. `test_generation_completion_start_time_equals_started_at_plus_first_token`
3. `test_one_phase_failure_does_not_block_others_or_generation`（单阶段异常 fail-open）
4. `test_tracer_blows_up_is_fail_open_and_generates_no_child_spans`（整 tracer 异常 fail-open）
5. `test_missing_create_span_attributes_helper_still_reports_generation`（评审 HIGH 必改项：私有 helper 缺失时仍上报）

## 2. 导入冒烟 / Lint

| 命令 | 结果 |
|---|---|
| `cd backend && ../.venv/bin/python -c "import app"` | **`import app OK`** |
| `.venv/bin/python -m ruff check backend/app/platform/observability/spans.py tests/observability tests/test_observability.py tests/test_observability_fixtures.py tests/test_observability_prompt_input.py` | **All checks passed!** |

## 3. 全量后端回归（未跑完，如实说明）

- 命令：`.venv/bin/python -m pytest tests/ -q --basetemp=./.tmp-pytest-full --ignore=tests/test_online_model_dispatch.py -p no:cacheprovider`
- 收集阶段：`2548 tests collected, 1 error`（error = `tests/test_online_model_dispatch.py`，见下）
- 运行 22:16→22:32（约 16 分钟），生成 ~4735 个 basetemp 目录后进程被 **SIGTERM** 终止（`pgrep` 确认进程消失）。**全量未跑完，未取得最终 passed/failed 汇总。**
- 原因：broker 沙箱对长时长/重负载 pytest 运行施加 SIGTERM（与任务预警一致）。改为**分段小批次**执行（见 §1/§4），大批次合并（9 文件）同样被 SIGTERM，拆小后通过。

### 已知环境既有问题（非本次引入）
1. **`tests/test_online_model_dispatch.py` 收集失败**：`ModuleNotFoundError: No module named 'langchain_openai'`（`tests/test_online_model_dispatch.py:12`）。属依赖缺失，与 spec-041 无关。
2. **`tests/test_kb_candidate_rebuild.py::test_empty_library_dry_run_reports_bootstrap_without_writes` 失败**：`PermissionError: EEXIST: file already exists, mkdir '.../.tmp-pytest*/test_empty_library_dry_run_rep0/papers'`（broker 沙箱 mkdir 拦截）。该文件**不在本次 diff**，可确定复现（换 basetemp 仍失败）→ 环境问题，非本 spec 引入。

## 4. 补充分段回归（扩大覆盖面）

| 批次 | 文件 | 结果 |
|---|---|---|
| KB batch1 | application_boundary, candidate_rebuild, chunkers, document_boundary, document_delete, document_foundation, document_reindex, document_routes | 177 passed, **1 failed（上述环境项）** in 91.58s |
| KB batch2 | empty_generation_bootstrap, immutable_create, markdown_provenance, metadata_migration, normalize, pdf_provenance, reranker, routes | 141 passed, 25 subtests passed |
| KB batch3 | services, source_provenance_bundle, startup_generation_gate, startup_reindex_recovery, tasks, upload_closure_matrix, legacy_kb_integration, rebuild_cli | 138 passed, 4 subtests passed |
| conversation | compaction_store, compaction_summary, filters | 26 passed |
| conversation | context_usage_api | 13 passed |
| conversation | conversations_api | 16 passed |
| reasoning | capabilities, options_endpoint, protocol | 44 passed |
| reasoning | stream_backend | 14 passed |
| api | test_api, api_module_boundaries | 13 passed |

**分段合计：675 passed / 1 failed（环境） / 29 subtests passed。**

## 5. fail-open 核对（未被破坏）

- `safe.py::safe_call`：`try: return action(...) except Exception: logger.warning(...); return None` —— 捕获一切异常，返回 None，不冒泡。
- `spans.py` 上报路径核对（全部在 safe_call 内）：
  - `record_ollama_generation` → `safe_call(_report)`（spans.py:320）；`_report` 内含 T-B 的 `_format_messages(redact_prompt_messages(...))`（:280）、`start_as_current_observation`（:295）、`generation.update/score`（:308-314）、T-E 的 `_report_phase_spans`（:318）
  - `record_event` → `safe_call(_report)`（spans.py:394）
  - `record_routing_observation` → `safe_call(record_event, ...)`（spans.py:443），且 `should_sample()/get_client()` 也在 safe_call 内
- T-B 变更点：输入格式化从 safe_call 外移入 `_report` 内（:280），强化 fail-open ✓
- T-E 变更点：`_report_phase_spans` 处于 `with ... as generation` 块内、整体在 `safe_call(_report)` 内；tracer 缺失 `getattr(...,None)` 早退；每阶段独立 try；`span.end` 置于 `finally`（`end_on_exit=False` 防 span 泄漏）；私有符号 `create_span_attributes` 已改为 try/except ImportError 容错导入（spans.py:37-40），缺失降级 None ✓
- 测试佐证：`test_one_phase_failure_...`、`test_tracer_blows_up_is_fail_open_...`、`test_missing_create_span_attributes_helper_...` 三例专测 fail-open，全部通过 ✓

## 6. 结论与遗留项

**VERIFICATION REPORT**

```
Build(import app):  PASS
Types:              N/A（无独立 type-checker 配置；ruff 通过）
Lint(ruff):         PASS (0 issues)
Tests(定向):        PASS (675 passed / 1 failed-环境 / 29 subtests)
Tests(全量):        INCOMPLETE（沙箱 SIGTERM，~16min 后被终止）
Security:           N/A（本任务不改安全语义；redact 按 spec 用户裁决保留 content）
Diff:               6 tracked files（spans.py + 3 tests + 2 docs）+ 2 新测试文件
Overall:            定向回归 READY；全量未跑完需知悉
```

- 本次 spec-041 变更（T-B/T-E）**定向回归全部通过**，无新增失败，fail-open 未破坏。
- 遗留/需知悉：
  1. 全量后端回归未跑完（沙箱 SIGTERM），已用 KB/chat/conversation/reasoning/api/observability 分段覆盖替代。
  2. `tests/test_online_model_dispatch.py` 缺 `langchain_openai`（环境既有）。
  3. `tests/test_kb_candidate_rebuild.py::test_empty_library_dry_run_reports_bootstrap_without_writes` 因 broker 沙箱 mkdir 拦截失败（环境既有，非本 spec）。

