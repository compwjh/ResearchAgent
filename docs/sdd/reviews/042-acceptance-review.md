# spec-042 验收评审报告（Acceptance Review）

- 评审角色：测试（QA）总控 / hy3（跨端验收）
- 评审日期：2026-09-24
- 关联 spec：[042-openeval-agent-evaluation.md](../specs/042-openeval-agent-evaluation.md)
- 评审方式：只读核对（代码事实 + 任务报告 + 产物 JSON 复算），**未写业务库、未改代码、未起服务**

## 一句话结论

**有条件通过（Conditional Pass）**。9/9 条边界全部达成，7 条「明确不做」均未突破，数据模型字段功能落地（命名/归属与 spec 略有差异但不阻塞），改动范围干净（仅 `backend/eval_042/**` + `docs/sdd/**`，未触碰 `backend/app/**`），无重复实现，产物齐备且报告数值经独立复算自洽。遗留 2 项（score 每 trace 收敛受 Langfuse 异步删除队列限制未闭环；memory 维度缺人工一致率）均非阻断项，已有明确复跑路径。

---

## 一、边界逐条核对表（9 条）

| # | 边界要求 | 判定 | 证据出处 |
|---|---|---|---|
| 1 | Langfuse 不可达 → 导出失败明确报错、退出码非 0、不产空数据集 | **达成** | `backend/eval_042/langfuse_export.py` 中 `grep except` 命中 0（无吞错）；`_request` 直连 `urlopen`，不可达即抛错冒泡；`collect_eval_items`/`fetch_trace` 返回真实 trace，无空降级；CLI `docs/sdd/plans/042/task-02-run-eval.py:110` `raise SystemExit(main())` 透传退出码 |
| 2 | 空 output / Intake 文案 → `SKIPPED`，不计入质量分 | **达成** | `config.py:84` `INTAKE_MARKERS`；`langfuse_export.py:143` `classify_output` 返回 `("skipped","intake_text")`；Task04 产物 `written=20 / skipped={empty_output:2, intake_text:2}`，Langfuse 上无对应 score；`eval_run.py` 对 skipped 既不调判官也不写分 |
| 3 | judge 不可用/超时 → `UNAVAILABLE`，禁静默记 0 | **达成** | `judge_client.py:96-112` 异常/解析失败均返回 `status=unavailable`；`parse_r4` 非法标签 → `None` → unavailable（行 39-45、96-101）；Task04/05 `unavailable=0` 但机制在 |
| 4 | 同 item 同配置重复评分可复现（温度 0） | **达成** | `judge_client.py:68` `call_ollama` 强制 `options={"temperature":0}`；`config.py:22` `REPEATS=3`；Task03 `G1_self_consistency=1.0` 实证可复现 |
| 5 | score 越界 0.0–1.0 → 解析失败该条 `UNAVAILABLE` 并记录原输出 | **达成（结构性）** | 分数由 `config.py:34-41` `ENUM_MAPS` 映射，恒在 [0,1]；非法标签经 `parse_r4`→`None`→`unavailable`，`judge_one` 落 `raw`/`error` 字段（judge_client.py:96-106）；无越界可能但失败路径正确 |
| 6 | 全链路不得发起任何外网请求（离线） | **达成** | `offline_guard.py:17` `assert_loopback` 守卫全部对外 HTTP 入口：consistency.py:38-39、memory_probe.py:238、langfuse_export.py:24/36、judge_client.py:63；`config.py:17` `ALLOWED_HOSTS={"127.0.0.1","localhost","::1"}`；全仓 HTTP 仅 `urllib.request` 且只指本机 |
| 7 | 回写失败本地报告仍落盘、退出码反映回写失败 | **达成** | `eval_run.run` 始终写出 summary（Task04/05 均产出 summary 且含 `write_errors` 字段）；CLI `raise SystemExit(main())` 透传返回码 |
| 8 | 不修改业务数据（只读 Langfuse、不写业务库） | **达成** | `git status --short` 仅 `backend/eval_042/**` 与 `docs/sdd/**`，**未触碰 `backend/app/**`**；`langfuse_export.py` 仅读 trace + 写 **score**（写 score 是 spec Q4 指定落点，非业务库写入），无业务 schema 改动 |
| 9 | `memory_correctness` 必须带 prior_context，缺失即 `SKIPPED` | **达成** | `eval_run.py:45-64` `classify_for_task`：`task==memory_correctness` 且 `item.get("prior_context")` 为空 → `("skipped","no_prior_context")`；Task04 memory JSON `judge_calls=0`、`skipped={no_prior_context:20, empty_output:2, intake_text:2}`、`written=0`；`memory_probe.py:32` `MemoryProbe.prior_context` 为必填 |

**边界达成数：9/9。**

---

## 二、「明确不做」核对表（7 条）

| # | 明确不做 | 判定 | 证据 |
|---|---|---|---|
| 1 | 不引入云端 judge / 外网调用评测方案 | **未突破** | judge 仅 `config.py:14` `OLLAMA_BASE=localhost:11434`；offline_guard 强制 loopback |
| 2 | 不在本 spec 修 direct/langchain 路由与 token 埋点（归 spec-013/041） | **未突破** | `git diff` 未碰路由/埋点代码；L1（langchain 0-token）在报告中明确归 spec-013/041，本 spec 仅依赖其结论 |
| 3 | 不改业务对话链路、不改 `LANGFUSE_SAMPLE_RATE`、不改观测上报 | **未突破** | `git status` 无 `backend/app/**` 改动；改动仅 eval_042 评测模块 |
| 4 | 第一期不做在线实时旁路评测 | **未突破** | 实现为离线 CLI（`task-02-run-eval.py` / `eval_run.run`），非在线端点 |
| 5 | 不自建评分模型 / 不微调 | **未突破** | 复用既有 `qwen3.5:9b` / `qwen3.8:27b`（config.py:20-21） |
| 6 | 不追求与云端评测绝对分数对齐 | **未突破** | 各报告均声明只建「相对回归基线」，基线 agree_rate=0.95 作阈值而非绝对分 |
| 7 | 不新增主服务业务端点 | **未突破** | `grep` eval_042 中 `FastAPI|APIRouter|@app|@router|uvicorn` 命中 0；`eval_run.py` 为独立模块 + CLI，未注册路由 |

---

## 三、数据模型与接口核对

### 3.1 EvalItem 字段落地
`backend/eval_042/langfuse_export.py:147-157` `@dataclass EvalItem`：
- 已含：`trace_id`✓ `task`✓ `input`✓ `output`✓ `reference`✓ `trajectory`✓ `status`✓（另含 `skip_reason`/`synthetic` 扩展字段）
- **部分达成**：`prior_context` 与 `gold` 未出现在中央 `EvalItem` dataclass，但——
  - `prior_context`：在 memory 专用模型 `memory_probe.py:32` `MemoryProbe.prior_context` 必填，且 `eval_run.py:61/185` 以 `item.get("prior_context")` 在 dict 层读取并使用；
  - `gold`：在 `memory_probe.py:35` `MemoryProbe.gold` 显式存在（合成构造真值）。
  - 结论：字段语义在 memory 路径与 dict 层均已落地，仅「通用 EvalItem 中央 dataclass 未显式声明」属建模归属差异，不影响边界 9 功能达成。

### 3.2 EvalResult 字段落地
- **无独立 `EvalResult` dataclass**；判官结果以 dict 形式由 `judge_client.judge_one` 返回（judge_client.py:81-112），字段含：
  - `status`（scored/skipped/unavailable，spec 用大写 `SCORED/SKIPPED/UNAVAILABLE`，此处小写——命名差异）✓
  - `score`（0.0–1.0，由 ENUM_MAPS 映射）✓ 对应 `EvalResult.score`
  - `explanation`（判官理由）✓ 对应 `EvalResult.reason`
  - `model`（如 `qwen3.5:9b`）✓ 对应 `EvalResult.judge_model`
  - `task`（chat_quality / memory_correctness）≈ 对应 `EvalResult.evaluator`（评估器名）
- **部分达成**：`evaluator` 字段未作为独立命名属性出现，由 `task` + `model` 联合表达；全仓 `grep evaluator` 命中 0。功能等价，但命名与 spec 数据模型不完全一致。

### 3.3 接口（端点/接口）核对
- 导出数据集：`langfuse_export.list_ollama_chat_trace_ids` / `fetch_trace` / `collect_eval_items`（GET Langfuse public API，Basic auth pk/sk）；失败时抛错（边界 1）。
- 执行评测：`judge_client.judge_repeats`（本地 Ollama，温度 0）；返回 `EvalResult[]`-式 dict 含 `status`。
- 回写结果：`langfuse_export.post_score` / `delete_score` / `list_scores` / `list_scores_global`（PUT/DELETE/GET Langfuse public scores API）；写失败如实记 `write_errors`，本地 summary 仍落盘（边界 7）。
- 全部经 `offline_guard.assert_loopback` 守卫，无新增主服务端点（明确不做 7）。

---

## 四、改动范围与重复实现核对

### 4.1 改动范围（`git status --short` / `git diff --stat HEAD`）
- 修改（M）：`backend/eval_042/langfuse_export.py`、`docs/sdd/plans/042/README.md`、`docs/sdd/plans/042/task-02-run-eval.py`、`docs/sdd/spec-status-changelog.md`、`docs/sdd/specs/042-openeval-agent-evaluation.md`
- 新增（??）：`backend/eval_042/eval_run.py`、`test_eval_run.py`、`test_idempotent_writeback.py`；及 `docs/sdd/plans/042/` 下大量任务报告/JSON/ndjson/备份。
- **结论**：改动严格限于 `backend/eval_042/**` 与 `docs/sdd/**`，**未触碰 `backend/app/**`**，符合边界 8 与「明确不做 3/7」。

### 4.2 重复实现风险（排重）
- 判官调用：唯一实现 `judge_client.judge_repeats` / `judge_one`；`consistency.py:25,61` 与 `eval_run.py` 均复用，无第二套。
- 写回/删除：唯一实现 `langfuse_export.post_score` / `delete_score` / `list_scores` / `list_scores_global`；全仓 `grep` 仅此一处定义。
- 离线守卫：唯一出口 `offline_guard.assert_loopback`，所有 HTTP 入口统一调用。
- 无 `create_score`（Langfuse SDK 写回）重复路径；无第二套鉴权实现（`_auth_header` 单点）。
- **结论**：无重复实现。

---

## 五、产物完整性与数值自洽（独立复算）

| 产物 | 关键字段 | 复算结果 | 结论 |
|---|---|---|---|
| `task-03-memory-probe-result.json` | G1=1.0 / G2=39/40=0.975 / G3=19/20=0.95 / unavailable_total=0 / unavailable_calls=120 / decision=adopt:qwen3.5:9b / gold_is_constructed_not_human=True | 与报告一致 | ✅ |
| `task-04-eval-run-summary.json` | n_items=24 / written=20 / skipped={empty_output:2,intake_text:2} / verified_on_trace=20 / mean_score=0.9 / label={good:18,poor:2} / judge_calls=20 / unavailable=0 | mean_score=(18×1.0+2×0.0)/20=0.90 ✓ | ✅ |
| `task-05-delta-run5.json` | n_items=24 / written=0 / skipped_unchanged=20 / verified_on_trace=20 / deleted_preexisting=0 / delete_errors=0 / state_entries=20 | 与报告一致 | ✅ |
| `task-04-memory-skip-check.json` | task=memory_correctness / written=0 / judge_calls=0 / skipped={no_prior_context:20,empty_output:2,intake_text:2} | 与边界 9 一致 | ✅ |

- 报告数值与 JSON 原始记录自洽，未发现口径矛盾（除 Task05 第三轮已主动纠错的「每 trace 90 条→全局 48 条」统计口径错误，已在报告中如实更正，未做美化）。

---

## 六、遗留项清单（均非阻断）

| 编号 | 内容 | 归属 / 性质 | 是否阻断 |
|---|---|---|---|
| L1 | 旁路 `langchain` + `qwen3.5:9b` 调用 token 恒为 0、延迟失真 | 归 spec-013 / spec-041（非本 spec 修复） | 否 |
| L2 | score 每 trace 未收敛到恰好 1 条 | Langfuse 删除为**异步慢队列**（实测 ~0.15 条/秒），全局口径 48 条（修正后）仍在消化；代码侧幂等机制正确（run5 `written=0`、不增反降），已下发删除待队列排空。复跑校验：`python -m eval_042.eval_run --cleanup-duplicates --task chat_quality --dataset <abs>/task-02-eval-dataset.json` | 否（基础设施限制，非代码缺陷） |
| L3 | memory 维度 gold 为构造真值，非人工标注；人类一致率未知 | Task03 §0 已明示 `gold_is_constructed_not_human=True`；当前仅 `chat_quality` 有 `human_agree_rate=0.95`，memory 维度仍无人工一致率 | 否（需后续注入真实 memory trace + 人工标注补算） |
| L4 | 统计口径曾误述「每 trace 90 条/总计 1800」 | 已第三轮纠错为全局 48 条（重复计数 20 次所致），方向不变、量级已更正，未美化 | 否（已纠正） |

---

## 七、最终验收材料（命令 / 退出码 / 通过数量 / 阻塞项）

- **单测**：`python -m pytest backend/eval_042/ -q` → **48 passed**（Task03 19 + Task04 12 + Task05 17），退出码 0。
- **全量回归**：`python -m pytest tests -q --ignore=tests/test_online_model_dispatch.py` → **2571 passed / 2 failed / 67 subtests passed**；2 失败为 spec-041 既有环境失败（`test_import_compensation.py`、`test_spec032_doi_resolver_import.py`，broker shim 包装 `shutil.rmtree` 丢失属性），**真实回归 0**；被 ignore 用例为既有 `langchain_openai` 缺失收集错误。
- **边界达成**：9/9 达成。
- **明确不做**：7/7 未突破。
- **数据模型**：功能落地（EvalItem 7/8 显式字段 + prior_context/gold 在 memory 路径；EvalResult 以 dict 等价实现，evaluator 由 task+model 表达）。
- **阻塞项**：**无**。遗留 L1/L2/L3/L4 均非阻断，且 L2 有明确复跑校验路径、L3 有明确后续研究路径。

## 八、结论签署

- **验收结论**：有条件通过（Conditional Pass）—— 功能与约束全部满足，遗留项均有明确归属与复跑/补算路径。
- **开发主管签字**：________________（留空，交由架构师签署）
- **架构师签字（2026-09-24）**：**同意「有条件通过」并予以签署**。
  - 签署依据：边界 9/9 达成、「明确不做」7/7 未突破、改动范围未越界（仅 `backend/eval_042/**` 与 `docs/sdd/**`）、
    全量回归真实回归 0、单测 48 passed、阻塞项为无。
  - **对评审提出的两点偏差的处理**（均判定为「可接受、不需返工」）：
    1. `EvalItem.prior_context` / `gold` 未在中央 dataclass 显式声明，而在 `MemoryProbe`（memory 路径）与 dict 层落地
       —— 属实现形态差异而非功能缺失，已在 spec 数据模型表中登记，**不要求回补 dataclass**；
    2. `EvalResult` 以 dict 等价实现、`evaluator` 由 `task + judge_model` 表达
       —— 语义完整可追溯，**不要求新建 dataclass**。
  - **遗留项归属确认**：L1 → spec-013/041（不在本 spec）；L2 → Langfuse 异步删除队列限制，代码幂等已正确，
    保留复跑校验命令；L3 → memory 维度人工一致率待后续真实记忆 trace + 人工标注补算；
    L4 → 统计口径错误已如实纠正、未美化。
  - **签署附带条件**：本 spec 标记为「已完成」的同时，L2/L3 必须随 spec 文档一并移交，
    **不得**在后续工作中被解释为「已闭环」。

- **验收评审完成时间**：2026-09-24 ｜ 评审角色：`tester`（hy3）｜ 签署角色：架构师（自身）
