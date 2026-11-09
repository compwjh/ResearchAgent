# 20261110 最终验收报告：实机精排验证 + 全量回归

## 0. 元信息与边界

| 项 | 内容 |
|---|---|
| 报告 | `docs/sdd/reviews/20261110-final-acceptance-review.md`（新建；不覆盖 `045-acceptance-review.md`） |
| 角色 | 跨端验收总控 tester（verification-loop / regression-guard） |
| 执行日期 | 2026-11-10 |
| 仓库根 | `/Users/wjh/work/ResearchAgent-2/ResearchAgent` |
| 工具 | `.venv/bin/python` (3.11.13)、`node` (v18.12.0)、curl |
| 边界 | **只读**：未改业务代码/测试/断言/夹具/版本号，未重启服务，未执行任何 git 写操作；仅新建本报告 |
| 进展日志 | `.codebuddy/agent-logs/spec-045/task-00/tester/20261110-045959.md` |

服务状态（用户声明，本次实测确认）：已带 `RERANKER_SERVER_BIN` 重启，uvicorn PID 18277、llama-server PID 18201；`/api/health` 200；`/api/kb/health` available=true / reason=null；`deploy/reranker/probe.sh` 通过。health 实现为「liveness + 三文档质量探针」，30s 正缓存 + single-flight，timeout 4s 短缓存。本次**未重启服务**。

实机精排请求契约依据：`deploy/reranker/probe.sh:42-49`（`/v1/rerank` 请求体正是三文档质量集，`model` 可选，见 50-52 行）；质量判定依据 `probe.sh:84-109`（results 恰好 3 项、index ∈ {0,1,2} 唯一、score 有限且不全相同、`scores[1]` 严格高于 0/2）。

单端报告汇总说明：本次按指令**直接执行全量回归**，未依赖、也未产出独立的 backend-tester / frontend-tester 单端报告；报告内所有数字均为本次实跑结果，作为两端结论的统一汇总。

## 1. 实机精排验证（第 1 步，独占负载）

执行方式：单个后台脚本 `/tmp/fa_step1.sh` 内先发 5 个并发 `POST http://127.0.0.1:11435/v1/rerank`，`wait` 后**紧接着**（同脚本、无其他请求插入）连续 40 次 `curl http://127.0.0.1:8000/api/kb/health`（间隔 1s）。结果落盘 `/tmp/fa_step1.out`、`/tmp/fa_s1/`。

### 1.1 五个并发 rerank

| # | HTTP | 耗时(s) |
|---|---|---|
| 1 | 200 | 11.030 |
| 2 | 200 | 2.588 |
| 3 | 200 | 5.657 |
| 4 | 200 | 8.540 |
| 5 | 200 | 8.540 |

墙钟 11s。**5/5 HTTP 200**，无 5xx、无超时、无连接错误。耗时分散（2.6–11.0s）系 llama-server 对并发请求排队处理所致，非失败。

质量探针 5/5 通过：每个响应 `results` 均含 index 0/1/2，`scores[1]≈0.9946`（强相关文档「Paris is the capital…」）远高于 `scores[0]/[2]≈3×10⁻⁵`，`top1_is_doc1=True`，符合 `probe.sh:108-109`「强相关文档必须排第一」。示例：`scores={1: 0.9946548, 0: 3.43e-05, 2: 2.76e-05}`。

### 1.2 连续 40 次 /api/kb/health

| 指标 | 实测 | 期望 | 判定 |
|---|---|---|---|
| HTTP 200 | 40/40 | 40 | PASS |
| `reranker_detail.available=true` | **40/40** | 40/40 | PASS |
| `reranker_detail.reason` 集合 | **{None}**（40 次） | 全 null | PASS |
| 顶层 `reranker=true` | 40/40 | — | PASS |
| 响应体含 `timeout` 字样 | **0 次** | 无 timeout | PASS |
| 首次 health 耗时 | **3.207s** | 参考 1.5–2.3s | 略高（见下） |
| 其余 39 次耗时 | 0.116–0.134s | 30s 正缓存命中 | PASS |

首次 3.207s 略高于参考区间 1.5–2.3s，成因是 5 并发 rerank 刚结束造成的排队（质量探针需实调 reranker）；其后 39 次均命中 30s 正缓存，稳定在 0.12s 量级，未触发 4s timeout。**如实输出**：40/40 全部达标，无一次 timeout、无一次 available=false。

**字段结构依据与统计口径修正（如实记录）**：`/api/kb/health` 响应并非顶层 `available/reason`，而是 `backend/app/api/routes_kb.py:120-136` 的 `kb_component_status()`：`reranker_detail = reranker_health()` 原样透传（`available/reason` 在其内），顶层 `reranker = bool(reranker_detail["enabled"] and reranker_detail["available"])`。实测样本：

```json
{"qdrant": true, "embedding": true, "reranker": true,
 "reranker_detail": {"enabled": true, "available": true, "backend": "llama.cpp",
 "model": "ggml-org/Qwen3-reranker-0.6B-Q8_0-GGUF:Q8_0", "reason": null},
 "papers": 15, "chunks": 6702, "v2_llm": {"model": "qwen3.8-27b-q4", "available": true},
 "generation": {"ready": true, "error_code": null}}
```

首版汇总脚本误按顶层 `available`/`reason` 取值，报出 `available_true=0 / nonconforming_rows=40`；核对上述实现后按 `reranker_detail` 正确口径重算得 **40/40 True/None**。该误报与修正过程完整保留，未只挑好结果。

## 2. 全量回归（第 2 步，分批执行避免工具级超时）

各批次 `N passed` 行简单求和为 2409，其中含 C1/C2 共 12 次**复跑**（属重复执行）；去重后全量唯一用例约 2397（前端 518 + 后端 559 + 1319 + E2E 1）。

### 2.1 前端 `tests/frontend/` 全量（pytest，按文件分 4 批）

`tests/frontend/test_*.py` 共 58 个文件，按 `split -l 15` 分为 15/15/15/13 四批，逐批 `.venv/bin/python -m pytest -q`：

| 批次 | 文件数 | passed | failed | skipped | 耗时 | rc |
|---|---|---|---|---|---|---|
| batch1 | 15 | 155 | 0 | 0 | 109.90s | 0 |
| batch2 | 15 | 111 | 0 | 0 | 190.90s | 0 |
| batch3 | 15 | 170 | 0 | 0 | 55.09s | 0 |
| batch4 | 13 | 82 | 0 | 0 | 3.35s | 0 |
| **合计** | **58** | **518** | **0** | **0** | — | 全 0 |

### 2.2 `tests/frontend/*.js` 探针（逐个 `node <file>`）

32 个探针逐个执行：**32 pass / 0 fail（rc=0）**，完整输出 `/tmp/fa_s2_node.out`、逐探针日志 `/tmp/fa_s2_node_logs/`。关键项：`test_frontend_tag_multiselect.js`（Set 多选 / OR 过滤 / +N 更多 / 已选计数 / CSS）、`test_frontend_memory_projects.js`（项目记忆全量列出 / 空态 / 点击接线）、`test_frontend_kb_failure_class_dom_contract.js`（DOM class 反向断言）、`test_frontend_conversation_research.js`（XSS text boundary）、`test_frontend_view_exclusivity.js`。统计脚本首版因 `cut -c` 按字节截断中文导致 `UnicodeDecodeError`，改用 `errors='replace'` 后结论不变（如实记录）。

### 2.3 后端 pytest

| 批次 | 命令 | 结果 | rc |
|---|---|---|---|
| B3 | `pytest -q tests/kb/ tests/system/test_reranker_config.py` | **559 passed**, 6 warnings, 29 subtests passed, 77.41s（期望 ~559 ✓） | 0 |
| B4 | `pytest -q tests/memory/ tests/research/` | **1319 passed**, 1 warning, 26 subtests passed, 283.70s（期望 ~1319 ✓） | 0 |

### 2.4 E2E 用例 1 单跑

命令：`RUN_E2E=1 E2E_BASE_URL=http://127.0.0.1:8000 .venv/bin/python -m pytest -q tests/e2e/test_research_lifecycle_e2e.py -k test_research_task_create_shows_in_list -v`

结果：`1 passed, 1 deselected in 5.16s`，rc=0。用例名核对 `tests/e2e/test_research_lifecycle_e2e.py:105`；**610s 的用例 2 `test_research_lifecycle_follow_through`（:117）按指令未执行**，由 `-k` 主动 deselected。此处如实标注为「未跑」，**不计入通过**。

### 2.5 页面联调 4 项轻量复验

先 `curl -L http://127.0.0.1:8000/`：**HTTP 200、69280 字节，与本地 `frontend/index.html` 字节数一致**；生效资源版本号 `app.js?v=73`（index.html:844）、`styles.css?v=71`（index.html:8），其余 `?v=` 均位于 HTML 注释 compatibility markers 内（7/843/846/847 行）。

| 项 | DOM / 代码依据 | 行为保证 | 结论 |
|---|---|---|---|
| 深度研究主 tab | `index.html:112` `<a class="nav-item" data-view="research">深度研究</a>`；`:225` `<div class="research-main-tabs kb-tabs" id="research-main-tabs" role="tablist" aria-label="深度研究主导航">` | node 探针 `test_create_task_view_contract.js`、`test_frontend_view_exclusivity.js` PASS | 成立 |
| 记忆治理项目记忆列表 | `index.html:115` nav-item `data-view="memory"`；`:452` 注释「所有 active 项目一次性列出，进入视图默认可见」；`:457` `<h2 id="memory-project-documents-title">项目记忆</h2>`；`:464` 空态节点 | node 探针 `test_frontend_memory_projects.js` PASS | 成立 |
| 标签「+N 更多」多选下拉 | `frontend/literature-maps.js:73/1991/2013` 折叠逻辑注释；`:2016` `createElement('button','btn-outline literature-map-tag-filter-more', '+${extra} 更多')`；`:2020` aria-label；CSS `frontend/literature-maps.css:511` 有对应选择器 | node 探针 `test_frontend_tag_multiselect.js` PASS（含 +N 更多） | 成立 |
| 次级按钮可用态 | `index.html:616` `secondary-button btn-outline`；`app.js:2750`、`literature-maps.js:5113` 动态创建同类按钮（app.js 出现 29 次）；`styles.css:1929` `#papers-view .secondary-button:disabled` 定义禁用态，`:16/111/114/125/303` 定义可用态 | B1 全量中 `test_frontend_button_affordance_contract.py:70` 等 17 个用例通过 | 成立 |

4 项均成立，无一项需给出「不成立」的 DOM 证据。

**限制（如实记录）**：本环境**无浏览器渲染/点选工具**，上述复验为「服务实际返回 HTML + 静态 DOM/CSS 契约 + 对应探针/契约测试」三层证据的**静态核对**，并非真实浏览器交互点选。

### 2.6 两个历史 flaky 各连跑 3 次

| 目标 | 修复 | run1 | run2 | run3 | 判定 |
|---|---|---|---|---|---|
| `test_frontend_map_feasibility.py` | K2+Q | 3 passed | 3 passed | 3 passed | 稳定 PASS，非 flaky |
| `test_frontend_literature_map_contract.py::test_component_fixture_renders_and_supports_core_interactions` | K1 | 1 passed | 1 passed | 1 passed | 稳定 PASS，非 flaky |

6 次复跑全部 rc=0。

## 3. 失败项判定（第 3 步）

- 本轮全量回归**零失败**：13 个 pytest 批次全部 rc=0、文件内无 `FAILED`/`ERROR` 起始行、32 个 node 探针全部 rc=0、各批次汇总无 skipped 计数（0 skipped）。因此**没有失败项需要按第 3 步复跑 3 次区分 flaky / 真实回归**。
- 用户点名的两个历史 flaky 已按要求各连跑 3 次，均稳定通过，判定为修复有效、非 flaky。
- 全程**未放宽断言、未改代码/测试/夹具、未加 skip**。
- 「skip / 未达」如实区分，不伪称通过：
  - B5 的 `1 deselected` 是 `-k` 主动排除 610s 用例 2，属**未跑**；
  - `test_research_lifecycle_follow_through`（610s）**未执行**；
  - spec029/030 重型阶段依赖外部 LLM、在 600s 窗口内**未达**（历史已知环境限制），本次不纳入执行范围；
  - 以上均不计入「通过」。

## 4. regression-guard 高频回归点复核

| 高频点 | 复核依据 | 结论 |
|---|---|---|
| JS 渲染 class 名 ↔ CSS 选择器一致 | `literature-maps.js:2016` `literature-map-tag-filter-more` ↔ `literature-maps.css:511`；B1 全量中 `test_frontend_button_affordance_contract.py:117` `test_new_css_classes_are_rendered_by_frontend_sources` 通过 | PASS |
| 前端资源版本号 `?v=N` | index.html:8 `v=71`、:844 `v=73`；`test_frontend_button_affordance_contract.py:194` `test_asset_versions_are_frozen` 通过。本次未改前端代码，无需升版本 | PASS |
| XSS（只用 textContent / input.value） | node 探针 `test_frontend_conversation_research.js`、`test_frontend_processing_tree.js` 通过；`test_frontend_button_affordance_contract.py:150/184` 通过 | PASS |
| SQLite 迁移 / 外键 RESTRICT / SSRF / USENIX 来源 | 由 B3(559) + B4(1319) 后端全量回归覆盖，0 failed；本次未改业务代码、无新增迁移 | 未见回归 |
| 稳定错误体 / acquire-release try-finally / SSE 合成帧不带 id: | 同上，后端全量 1878 个用例 0 failed | 未见回归 |

## 5. Overall：**READY**

理由：
1. 实机精排：5/5 并发 rerank HTTP 200 且质量排序正确；40/40 health `available=true`、`reason=None`、无 timeout。
2. 回归全绿：前端 518 passed（58 文件 / 4 批）+ 32/32 node 探针；后端 559 + 1319 passed；E2E 用例 1 通过。
3. 两个历史 flaky 各连跑 3 次稳定通过；页面联调 4 项静态核对成立。
4. 零 failed、零 skipped（除主动 deselected 的用例 2），无真实回归项；全程只读、未重启服务、无 git 写操作。

保留项 / 风险（不阻断 READY，需跟踪）：
- 5 并发 rerank 耗时分散（最长 11.0s），首次 health 3.207s 高于参考区间 1.5–2.3s，系并发排队所致；生产若有并发精排需求需评估排队 / 批量策略。
- 页面 4 项为静态核对，缺真实浏览器点选复验。
- 610s E2E 用例 2 与 spec029/030 重型 LLM 阶段未达，未纳入本次验证。

## 6. 已知环境阻塞与后续工单建议

1. **浏览器自动化缺失** → 建议引入 Playwright / 浏览器 MCP，对深度研究主 tab、项目记忆列表、+N 更多下拉、次级按钮可用态补真实点选与视觉回归。
2. **E2E 用例 2(610s) / spec029/030 重型阶段依赖外部 LLM，600s 窗口内未达** → 建议拆分为可 mock 的分阶段用例、外部 LLM 改 stub，并配置独立 nightly job 与更长窗口；在达成前保持「未达」标注，不伪称通过。
3. **rerank 并发排队** → 建议评估 `RERANKER_SERVER_BIN` 的并行度 / 批量推理参数与 llama-server `--parallel` 配置；复测无并发负载时首次 health 是否回落至 1.5–2.3s。
4. **health 字段口径** → `/api/kb/health` 的 `available/reason` 嵌在 `reranker_detail` 内（routes_kb.py:120-136），监控 / 告警 / 验收脚本须按正确字段取值，避免本次「顶层取值误报 0/40」类问题复发；建议补一条契约测试锁定响应结构。
5. **验收统计脚本健壮性** → 本次两处统计口径问题（health 字段层级、中文按字节截断 UTF-8）均为验收脚本自身问题，非产品缺陷；建议统一 `errors='replace'` 且按实现代码核对字段路径。

## 7. 证据与依据清单

- 进展日志：`.codebuddy/agent-logs/spec-045/task-00/tester/20261110-045959.md`
- 实机验证：`/tmp/fa_step1.out`、`/tmp/fa_s1/rerank_*.json`、`/tmp/fa_s1/health_*.json`、`/tmp/fa_s1/health_index.txt`
- 回归原始输出：`/tmp/fa_s2_pytest.out`（含 BATCH_FILES_N 分批清单）、`/tmp/fa_s2_node.out`、`/tmp/fa_s2_node_logs/`
- 关键代码依据：`deploy/reranker/probe.sh:42-55,84-109`；`backend/app/api/routes_kb.py:120-136`；`frontend/index.html:8,112,115,225,452,457,464,616,844`；`frontend/literature-maps.js:73,1991,2013,2016,2020,5113`；`frontend/literature-maps.css:511`；`frontend/app.js:2750,3012`；`frontend/styles.css:16,111,114,125,303,1929`；`tests/frontend/test_frontend_button_affordance_contract.py:70,117,194`；`tests/e2e/test_research_lifecycle_e2e.py:105,117`
- 历史报告（未覆盖）：`045-acceptance-review.md`、`045-requirement-review.md`、`045-tech-review.md`

## 开发主管签字


