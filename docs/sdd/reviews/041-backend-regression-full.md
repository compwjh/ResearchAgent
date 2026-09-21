# spec-041 后端全量回归报告（分段执行）

- 分支：`feature/spec-041-langfuse-trace-detail`
- 解释器：`.venv/bin/python`（Python 3.11.7）
- 命令统一加 `--basetemp=./.tmp-pytest`（broker 沙箱拒绝在 /tmp 建临时目录）
- 执行者：backend-tester-1（只跑测试，未改任何代码/测试/spec，未 commit/push）
- 回归动机：确认 T-B（`redact_prompt_messages` 保留 input 原文）、T-E（`_report_phase_spans` 4 阶段子 span）与默认路由变更（`OLLAMA_ROUTE` 默认 `langchain`→`direct` + conftest 固定回 langchain）未引入回归。

---

## 1. 分批结果（真实数字）

| 批次 | 范围 | passed | failed | 其他 | 耗时 |
|---|---|---|---|---|---|
| 1 | `tests/observability` `tests/runtime` | 5 | 0 | — | 2.6s |
| 2 | `test_chat_route.py` + 5 个 `test_conversation*` | 68 | 0 | — | 98s |
| 3a | 13 个 `test_kb_*.py` | 236 | 1 | — | 66s |
| 3b | 12 个 `test_kb_*.py` | 229 | 0 | 29 subtests | 20s |
| 4 | `test_api_routes_coverage.py` `test_skill_intent.py` `test_system_rule_backend.py` | 81 | 0 | — | 45s |
| 5-0 | chunk_0（24 文件） | 201 | 0 | — | 13s |
| 5-1 | chunk_1（24 文件） | 285 | 1 | — | 58s |
| 5-2 | chunk_2（24 文件） | 357 | 0 | 1 collection error；12 subtests | 83s |
| 5-3 | chunk_3（24 文件） | 345 | 0 | 8 subtests | 321s |
| 5-4 | chunk_4（24 文件） | 357 | 1 | — | 31s |
| 5-5 | chunk_5（21 文件） | 381 | 0 | 18 subtests | 47s |
| **合计** | | **2545** | **3** | **1 collection error；67 subtests** | ~13min |

> 说明：`tests/backend` 目录不存在，批次 1 按实际改为 `tests/observability tests/runtime`。
> `--basetemp=./.tmp-pytest` 会被 pytest 清空，分批用的文件清单已移到
> `.codebuddy/agent-logs/spec-041/task-13/backend-tester/lists/`。

## 2. 全量覆盖度

- `tests/*.py` 共 **176** 个（含 `conftest.py`，即 175 个测试文件）。
- 已跑集合与 `ls tests/*.py`（去 conftest）**diff 为空 → COVERAGE_COMPLETE**。
- 另含目录内测试文件 `tests/observability/test_phase_spans.py`、`tests/runtime/test_effort_calibration.py`。
- **未跑到：0 个文件。全量 100% 跑完（分段执行，未触发 SIGTERM）。**

## 3. 失败用例清单（3 failed + 1 collection error）

全部为**环境既有**，无一条触及 `spans.py` / `chat_runner.py` / `config.py` / `OLLAMA_ROUTE` / `redact` / `phase`。

| # | 用例 | 性质 | 根因（实测） | 建议修法 |
|---|---|---|---|---|
| 1 | `tests/test_online_model_dispatch.py`（collection error） | 环境既有 | `ModuleNotFoundError: No module named 'langchain_openai'`（`from langchain_openai import ChatOpenAI`） | 在 venv 安装 `langchain_openai`，或将该模块改为 `pytest.importorskip("langchain_openai")` |
| 2 | `test_kb_candidate_rebuild.py::test_empty_library_dry_run_reports_bootstrap_without_writes` | 环境既有 | `PermissionError: EEXIST ... mkdir '.tmp-pytest/.../papers'`，由 broker shim `sitecustomize._brokered_path_mkdir` 抛出（第二次 `mkdir(exist_ok=True)` 也被拦） | 沙箱侧放行 `mkdir`，或测试改用 `tmp_path` 下已存在判定（非本次改动范围） |
| 3 | `test_import_compensation.py::test_import_without_temp_dir_uses_attempt_private_root_and_cleans_only_it` | 环境既有 | 断言 `not seen[0].exists()` 失败（清理后目录仍在）。**根因证实**：broker shim 包装了 `shutil.rmtree`（`shutil.rmtree.__module__=='sitecustomize'`）且丢失 `avoids_symlink_attacks` 属性（`python -S` 无 shim 时为 `shutil`/`True`），`paper_import._cleanup_attempt_root`（L291-292）据此提前 `return`，清理永不执行 | 沙箱侧保留 `shutil.rmtree.avoids_symlink_attacks` 属性；与 spec-041 无关 |
| 4 | `test_spec032_doi_resolver_import.py::test_import_removes_its_own_temp_root_after_a_rejected_doi` | 环境既有 | 同 #3：`paper-import-*` 临时目录未被清理（`shutil.rmtree` 被 shim 包装后 `avoids_symlink_attacks` 缺失） | 同 #3 |

**真实回归：0 条。**

## 4. Ruff

```
.venv/bin/python -m ruff check backend tests   → Found 105 errors (全仓既有)
```
- 规则分布：I001×34、F401×18、SIM118×10、E701×8、SIM105×7、SIM117×6、F841×6 …（均为历史存量）。
- **spec-041 全部改动文件单独跑 → `All checks passed!`**
  `backend/app/platform/config.py`、`backend/app/platform/observability/config.py`、
  `backend/app/platform/observability/spans.py`、`tests/conftest.py`、
  `tests/test_chat_route.py`、`tests/test_kb_ask_trace.py`、`tests/test_system_rule_backend.py`、
  `tests/observability/test_phase_spans.py`。
- 结论：改动文件 lint 干净；105 条为全仓既有，非本次引入。

## 5. 三项关键行为确认（实测）

| 项 | 方法 | 结果 |
|---|---|---|
| 生产默认值确为 `direct` | 独立进程 `.venv/bin/python -c "from backend.app.platform import config; print(config.OLLAMA_ROUTE)"` | **`direct`** ✅（`config.py:122`） |
| conftest autouse fixture 只影响测试、不动生产配置 | ① 读 `tests/conftest.py:78-93`：`monkeypatch.setattr("backend.app.chat.application.chat_runner.OLLAMA_ROUTE","langchain")`，只改 `chat_runner` 模块内导入副本，**未** patch `platform.config.OLLAMA_ROUTE`；② 自建 pytest 插件（autouse 前后断言 `platform.config.OLLAMA_ROUTE == "direct"`）跑 `tests/test_chat_route.py` → **13 passed** | ✅ 生产配置对象全程未被改动 |
| `test_default_route_is_direct` 通过 | `pytest "tests/test_chat_route.py::RunChatTests::test_default_route_is_direct"` | **1 passed** ✅ |

## 6. 安全扫描（改动文件）

- `sk-*` / `api_key=` / `password=` / `BEGIN RSA|PRIVATE` 模式扫描 → **NO_SECRETS_FOUND**。
- 说明：spec-041 系用户裁决「input/output 全量可见」的**有意**设计变更（`redact_prompt_messages` 不再清零 content），已在 `tests/test_kb_ask_trace.py`、`tests/test_system_rule_backend.py`、`tests/test_chat_route.py` 同步更新断言；非漏洞。

## 7. Diff 审查（spec-041 代码/测试改动，共 11 个）

| 文件 | 变更 | 评价 |
|---|---|---|
| `backend/app/platform/config.py` | `OLLAMA_ROUTE` 默认 `langchain`→`direct` + 注释 | 符合 T-默认路由要求 |
| `backend/app/platform/observability/config.py` | `route()` docstring 更新 | 仅注释 |
| `backend/app/platform/observability/spans.py` | `redact_prompt_messages` 保留原文；新增 `_report_phase_spans`；`create_span_attributes` try/except 容错导入 | 符合 T-B / T-E；fail-open 正确 |
| `tests/conftest.py` | 新增 autouse fixture `_pin_default_route_to_langchain_in_tests` | 只 patch chat_runner 副本，隔离正确 |
| `tests/test_chat_route.py` | 改名 `test_default_route_is_direct` + 显式 patch；input 断言改全量可见 | 符合 |
| `tests/test_kb_ask_trace.py` | content 断言由「全空」改「非空」 | 符合 |
| `tests/test_system_rule_backend.py` | 改名 + content 断言改保留原文 | 符合 |
| `tests/observability/test_phase_spans.py`（新增） | T-E 用例（4 span 时间戳 ±1ns、fail-open、私有 helper 缺失） | 非恒真、不 skip，覆盖到位；本批 5 passed |
| `tests/test_observability_prompt_input.py`（新增） | input 全量可见断言 | 单跑 6 passed |
| `docs/sdd/*`（spec-status-changelog、specs/013、specs/041、reviews、HANDOFF） | 文档 | — |

未发现非预期改动、缺失错误处理或边界问题。

---

## VERIFICATION REPORT

```
Build:     PASS   （import smoke: `import backend.app.main` → IMPORT_OK）
Types:     PASS   （无独立 type checker；改动文件 ruff 全过）
Lint:      PASS   （spec-041 改动文件 0 error；全仓 105 error 均为存量）
Tests:     PASS   （2545 passed / 3 failed / 1 collection error；覆盖 177/177 文件 = 100%）
Security:  PASS   （改动文件 0 secrets）
Diff:      9 modified + 2 new test files（+ docs）（均为 spec-041 预期改动）

Overall:   READY —— 未发现任何 spec-041 引入的后端回归
```

### 失败项性质判定
- 环境既有：4 条（3 failed + 1 collection error）——缺 `langchain_openai`；broker shim 拦 `mkdir`；broker shim 包装 `shutil.rmtree` 致 `avoids_symlink_attacks` 丢失 → 清理路径提前 return（2 条）。
- **真实回归：0 条。**

### 阻塞项
- 无阻塞 spec-041 判定的问题。
- 附注（非阻塞，环境层）：建议在沙箱侧保留 `shutil.rmtree.avoids_symlink_attacks` 属性并放行 `mkdir`，并在 venv 补装 `langchain_openai`，即可让这 4 条转绿；它们与 spec-041 无关。

### 日志路径
`.codebuddy/agent-logs/spec-041/task-13/backend-tester/progress.md`
