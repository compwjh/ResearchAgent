# Spec043 Task08 全量回归报告

## 结论

当前收口候选 `a328932` 的提权隔离全量回归明确为 `PASS`：`3224 passed / 0 failed / 2 skipped / 67 subtests passed / 5 warnings`，`regression_exit_code=0`。稳定证据：[原始回归日志](runs/20261022-a328932-full-regression/full-regression.log)、[脱敏元数据](runs/20261022-a328932-full-regression/regression-metadata.json)。

最新回归结论为 `PASS`（见文末 2026-10-22 重跑记录）。此前候选 `1a3ff26` 的首轮完整 `tests -q` 曾因运行沙箱和 4 个非浏览器契约失败而 `BLOCKED`；该轮历史证据保留，不与本次候选混用。未改业务代码、未部署、未启动/停止服务、未读取 `.env` 或凭据，也未向生产 SQLite/Qdrant 写入数据。

## 执行记录

- 候选：`1a3ff26`
- 临时根目录：`/private/tmp/spec043-task08-ykEMIK`
- 原始日志：[full-regression.log](/private/tmp/spec043-task08-ykEMIK/full-regression.log)
- 开始时间：2026-10-21 23:50:03 +0800（由 154.23 秒墙钟时长反推；原始 wrapper 未打印 start）
- 结束时间：2026-10-21 23:52:37 +0800
- pytest 退出码：`1`（18 个失败；shell wrapper 另因 zsh 的只读变量名 `status` 未能打印状态，并以 1 退出）
- 计数：`3191 passed, 18 failed, 14 skipped, 67 subtests passed, 5 warnings`
- 服务 `8000`：未触碰；真实 API 证据由独立 live-api 记录维护

实际命令（无 `-k`、`--ignore`、`--deselect`、`--maxfail` 或人工 skip）：

```text
regression_root=$(mktemp -d /private/tmp/spec043-task08-XXXXXX)
mkdir -p "$regression_root/data/kb" "$regression_root/data/kb/qdrant" \
  "$regression_root/data/articles" "$regression_root/data/browser-profile" \
  "$regression_root/data/paper-search" "$regression_root/data/memory" \
  "$regression_root/data/literature_maps" "$regression_root/data/research" \
  "$regression_root/data/agent_tasks" "$regression_root/pytest-cache" \
  "$regression_root/pytest-tmp"
PYTHON_DOTENV_DISABLED=1 \
COMPACTION_SUMMARY_MODE=rule \
KB_DIR="$regression_root/data/kb" \
QDRANT_PATH="$regression_root/data/kb/qdrant" \
KB_META_PATH="$regression_root/data/kb/papers.json" \
MEMORY_DB_PATH="$regression_root/data/memory/memory.sqlite3" \
LITERATURE_MAP_DB_PATH="$regression_root/data/literature_maps/literature_maps.sqlite3" \
RESEARCH_DB_PATH="$regression_root/data/research/research.sqlite3" \
AGENT_TASKS_DB="$regression_root/data/agent_tasks/agent_tasks.sqlite3" \
PAPER_DISCOVERY_DB_PATH="$regression_root/data/paper-search/state.sqlite3" \
ARTICLE_DOWNLOAD_DIR="$regression_root/data/articles" \
PAPER_DISCOVERY_BROWSER_PROFILE_DIR="$regression_root/data/browser-profile" \
LANGFUSE_ENABLED=false \
.venv/bin/python -m pytest tests -q \
  -o "cache_dir=$regression_root/pytest-cache" \
  --basetemp="$regression_root/pytest-tmp" \
  >"$regression_root/full-regression.log" 2>&1
```

未设置 `MEMORY_DIR`、`RUN_E2E=1`、业务默认 model/embedding 配置或 `OLLAMA_ROUTE`；`PYTHON_DOTENV_DISABLED=1` 生效。唯一允许的生产侧读取仍是既有 `mode=ro`、仅 `SELECT COUNT(*)` 的 memory 污染哨兵。

## 失败节点与诊断

### 环境性浏览器失败（14 个节点）

完整回归中的以下节点均在 Chromium 启动阶段失败，首个异常为 macOS `mach_port_rendezvous ... Permission denied (1100)`，表现为 Playwright `TargetClosedError`，不是断言失败：

- `tests/frontend/test_frontend_map_analysis_contract.py::test_component_fixture_supports_analysis_history_failure_and_conversation_bridge`
- `tests/frontend/test_frontend_map_analysis_contract.py::test_component_fixture_keeps_running_job_requeryable_after_poll_limit`
- `tests/frontend/test_frontend_map_analysis_contract.py::test_component_fixture_shows_retryable_failure_and_drops_stale_analysis`
- `tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_drawers_single_pan_and_desktop_boundary[375]`
- `tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_drawers_single_pan_and_desktop_boundary[390]`
- `tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_pinch_center_bounds_switch_and_blur_cleanup`
- `tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_and_detail_scroll_use_real_touch_gestures`
- `tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_detail_close_is_not_blocked_by_global_navigation`
- `tests/frontend/test_frontend_map_mobile_contract.py::test_global_mobile_navigation_close_paths_keep_map_entry_reachable[375]`
- `tests/frontend/test_frontend_map_mobile_contract.py::test_global_mobile_navigation_close_paths_keep_map_entry_reachable[390]`
- `tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_state_resets_after_desktop_view_exit`
- `tests/frontend/test_frontend_map_mobile_contract.py::test_desktop_detail_survives_desktop_resize`
- `tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_drawer_state_resets_on_desktop_resize_round_trip`
- `tests/frontend/test_frontend_map_mobile_contract.py::test_desktop_mouse_node_drag_saves_changed_position`

按 root 授权使用 `require_escalated`，以同一临时隔离约束单独诊断两份前端文件，结果为 `16 passed in 29.80s`、退出码 `0`。诊断原始日志：[browser-diagnostic.log](/private/tmp/spec043-task08-browser-beuVIT/browser-diagnostic.log)。因此这 14 项的原始全量失败已定位为运行沙箱权限阻断；但未重写全量计数，原始全量仍保持 `BLOCKED`。

### 非浏览器失败（4 个节点）

1. `tests/conversation/test_conversation_context_usage_api.py::test_auto_compaction_threshold_boundary`
   - `recorded_low` 出现 `('auto', {'est_tokens_before': 3804})`，测试在 `tests/conversation/test_conversation_context_usage_api.py:201` 断言不应自动 compact。
   - 分类：应用/阈值契约失败，需 root 安排同范围诊断；tester 未修改实现或测试。

2. `tests/kb/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered`
   - `backend/app/main.py` 实际 SHA-256 为 `efdf81a23b77646edebd1f61af717c23116d2a2535cfbde0fc53c220d5bf4a47`，矩阵期望为 `43a41025609611fb959c3305c6ef6af8743883d7947f8c397c16a5925d7f0fff`。
   - 分类：冻结清单/候选内容不一致，需 root 诊断是否应更新矩阵或回退候选；tester 不改 hash。

3. `tests/system/test_api_module_boundaries.py::test_api_does_not_import_infrastructure`
   - 静态违规：`backend/app/api/routes_conversations.py:51` 导入 `backend.app.literature_maps.infrastructure.store`；`backend/app/api/routes_literature_maps.py:16` 导入同一 infrastructure 模块。
   - 分类：模块边界契约失败，需后端范围修复后重跑；tester 不改业务代码。

4. `tests/system/test_legacy_kb_integration.py::test_reindex_uses_canonical_application_and_route_with_fake_qdrant`
   - `tests/system/test_legacy_kb_integration.py:226` 期望 `result["chunkers"]["v1"]["status"] == "indexed"`，实际为 `"indexing"`；错误字段为 `None`。
   - 分类：KB reindex 状态契约失败，需 root 安排后端诊断；tester 不改实现或测试。

## Skip 与 warning

- `14 skipped` 为测试自身条件保护产生；本轮未使用人工 skip、`-k`、deselect 或 ignore。静态 guard 对应为：11 个浏览器能力测试（map feasibility 1、literature-map expansion 8、literature-map contract 1、map groups/exports 1）因普通 sandbox 的 Chromium 启动阻断而自 skip；`tests/e2e` 的 2 个生命周期用例因未设置 `RUN_E2E=1` 按仓库约定整体 skip；scheduler runtime 的 1 个可选 LangChain/Ollama 合同测试因依赖不可用 skip。原始命令使用 `-q`，pytest 未展开逐项 skip reason；上述构成来自测试内现有 guard，不是人工过滤。
- `5 warnings` 已保留在原始日志末尾，主要为依赖二进制类型的 `DeprecationWarning`；未因 warning 改变退出结论。

## 后续处理边界

首轮报告仅保留证据并标记 `BLOCKED`；不得以升级权限的 16 项前端诊断替代完整回归重跑。该首轮历史记录不代表最终候选结果；本 tester 不改代码、不部署、不操作生产服务或数据库。

## 最终候选重跑（2026-10-22，提权隔离）

- 候选：`a328932`
- 回归根目录：`/private/tmp/spec043-task08-GywaN2`
- 原始日志：[full-regression.log](/private/tmp/spec043-task08-GywaN2/full-regression.log)（59 行，4411 字节，保留完整原始输出）
- 仓库稳定日志：[runs/20261022-a328932-full-regression/full-regression.log](runs/20261022-a328932-full-regression/full-regression.log)
- 脱敏元数据：[runs/20261022-a328932-full-regression/regression-metadata.json](runs/20261022-a328932-full-regression/regression-metadata.json)
- 启动前静态证据：[preflight log](/private/tmp/spec043-task08-preflight-a328932.log)；`check_test_layout.py` 退出码 `0`，`check_test_naming.py` 退出码 `0`；测试中 `PaperDiscoveryStore()` 零匹配（rg 退出码 `1`，符合零发现预期）。
- `service_8000`：启动前发现既有 Python 监听；未启动、停止或触碰该服务。
- `started_at`：`2026-10-22T09:19:28Z`
- `ended_at`：`2026-10-22T09:31:55Z`
- `regression_exit_code`：`0`（wrapper 正常退出；未使用 zsh 保留变量 `status`）
- 计数：`3224 passed / 0 failed / 2 skipped / 67 subtests passed / 5 warnings`
- pytest 原始汇总：`3224 passed, 2 skipped, 5 warnings, 67 subtests passed in 745.06s (0:12:25)`
- 结果：`PASS`

实际执行命令（`exec_command` 使用 `require_escalated`；无 `-k`、`--ignore`、`--deselect`、`--maxfail`、并行分片或人工 skip）：

```text
regression_root=$(mktemp -d /private/tmp/spec043-task08-XXXXXX)
mkdir -p "$regression_root/data/kb" "$regression_root/data/kb/qdrant" \
  "$regression_root/data/articles" "$regression_root/data/browser-profile" \
  "$regression_root/data/paper-search" "$regression_root/data/memory" \
  "$regression_root/data/literature_maps" "$regression_root/data/research" \
  "$regression_root/data/agent_tasks" "$regression_root/pytest-cache" \
  "$regression_root/pytest-tmp"
PYTHON_DOTENV_DISABLED=1 \
COMPACTION_SUMMARY_MODE=rule \
KB_DIR="$regression_root/data/kb" \
QDRANT_PATH="$regression_root/data/kb/qdrant" \
KB_META_PATH="$regression_root/data/kb/papers.json" \
MEMORY_DB_PATH="$regression_root/data/memory/memory.sqlite3" \
LITERATURE_MAP_DB_PATH="$regression_root/data/literature_maps/literature_maps.sqlite3" \
RESEARCH_DB_PATH="$regression_root/data/research/research.sqlite3" \
AGENT_TASKS_DB="$regression_root/data/agent_tasks/agent_tasks.sqlite3" \
PAPER_DISCOVERY_DB_PATH="$regression_root/data/paper-search/state.sqlite3" \
ARTICLE_DOWNLOAD_DIR="$regression_root/data/articles" \
PAPER_DISCOVERY_BROWSER_PROFILE_DIR="$regression_root/data/browser-profile" \
LANGFUSE_ENABLED=false \
.venv/bin/python -m pytest tests -q \
  -o "cache_dir=$regression_root/pytest-cache" \
  --basetemp="$regression_root/pytest-tmp" \
  >"$regression_root/full-regression.log" 2>&1
regression_exit_code=$?
```

隔离与 skip 说明：未设置 `MEMORY_DIR`、`RUN_E2E=1`、业务 model/embedding 配置或 `OLLAMA_ROUTE`；`PYTHON_DOTENV_DISABLED=1` 生效。2 个 skip 均为 `tests/e2e/test_research_lifecycle_e2e.py` 的两个生命周期用例，由模块级 `pytest.mark.skipif(not os.environ.get("RUN_E2E"), reason="浏览器端到端需设置 RUN_E2E=1 并先启动后端服务(:8000)")` 合法触发；本轮未人工 skip、未设置 `RUN_E2E`。5 个 warning 为原始日志中的 `SwigPyPacked`（2）、`SwigPyObject`（2）和 `swigvarlink`（1）`DeprecationWarning`，未改变退出结论。

本轮没有失败节点或首失败堆栈需要保留；临时根目录及原始日志按计划保留供复核。tester 未修改代码、未部署、未提交。
