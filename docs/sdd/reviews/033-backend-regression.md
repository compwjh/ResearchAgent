# spec-033 后端定向回归验证报告

- **Spec**：033 — USENIX 解析器与真实页面结构对齐
- **Task**：task-04（技术评审 MEDIUM 修复后的回归验证）
- **角色**：backend-tester（只验证，未改任何代码）
- **日期**：2026-09-12
- **环境**：Python 3.11，venv = `.venv`，cwd = `/Users/wjh/work/ResearchAgent-2/ResearchAgent`
- **统一命令**：`env -u PYTHONPATH .venv/bin/python -m pytest <文件...> -q --basetemp=/tmp/bt033_<批次名>`
- **工作区状态**：脏（含 spec-033 改动 + 另一 agent 在途的 spec-032.1 改动）。本次**未执行**任何写操作、未使用 `git checkout/restore/stash/reset`。

---

## 1. 批次结果表

| 批次 | 文件 | passed | failed | errors | 耗时(pytest) | 原始尾部输出行 |
|------|------|--------|--------|--------|--------------|----------------|
| b1 | `test_usenix_paper_parser.py` / `test_usenix_publication_source.py` / `test_usenix_detail_tool.py` | 98 | 0 | 0 | 14.41s | `98 passed, 5 warnings in 14.41s` |
| b2 | `test_paper_discovery_api.py` / `test_paper_discovery_search.py` / `test_paper_discovery_normalization.py` | 98 | 0 | 0 | 4.10s | `98 passed, 1 warning, 12 subtests passed in 4.10s` |
| b3 | `test_paper_discovery_async_api.py` / `test_paper_discovery_store.py` / `test_catalog_search_graph_backend_fix.py` | 28 | 0 | 0 | 3.81s | `28 passed, 1 warning in 3.81s` |
| b4 | `test_search_catalog_candidate_urls.py` / `test_fetch_paper_detail_dispatch.py` / `test_frontend_paper_contract.py` | 47 | 0 | 0 | 2.25s | `47 passed in 2.25s` |
| b5 | `test_paper_import.py` / `test_paper_import_identity.py` / `test_paper_import_index_failure_code.py` / `test_paper_import_generation_binding.py` | 40 | 0 | 0 | 3.09s | `40 passed in 3.09s` |
| **合计** | **16 个文件** | **311** | **0** | **0** | **27.66s** | 全部 `passed`，无 SIGTERM（无 exit 137） |

> 备注：b1 的 5 条 warning 与 b2/b3 的 1 条 warning 均为第三方库 `DeprecationWarning`（SWIG `SwigPyPacked/SwigPyObject/swigvarlink`、`starlette.testclient` 的 `anyio.abc.BlockingPortal` 别名），非断言/非业务问题。

### 每文件收集数（b1 基线核对）

| 文件 | collected |
|------|-----------|
| `test_usenix_paper_parser.py` | 47 |
| `test_usenix_publication_source.py` | 42 |
| `test_usenix_detail_tool.py` | 9 |
| 小计 | **98** |

与已知基线（parser 47 + publication_source 42 = 89）**完全一致**，detail_tool 贡献 9。

---

## 2. 失败用例分析

**无失败用例。** 5 个批次 311 个测试全部通过，`failed=0`、`errors=0`，无 xfail/xpass 异常，无 SIGTERM。

因此本节无「完整用例名 / 断言差异原文」可列。

---

## 3. 区分「既有失败」与「回归」的方法（本次使用）

本次**没有测试失败**，故无需对测试项做基线区分。但发现 1 条 **ruff lint 问题**，仍按下列方法确证其归属：

**通用方法（不改工作区）**：

1. **来源归属**：先看失败/告警所在文件是否在 spec-033 的改动集合内。
   - spec-033 触及：`backend/app/paper_discovery/infrastructure/usenix_paper_parser.py`、`.../usenix_publication_source.py`，以及 `tests/test_usenix_paper_parser.py`、`tests/test_usenix_publication_source.py`、`tests/fixtures/usenix/*.html`。
2. **HEAD 基线对照（不写工作区）**：用 `git show HEAD:<path> > /tmp/<file>` 把 HEAD 版本导出到 `/tmp` 再对该副本执行同一检查（lint/测试），对比工作区版本。
   - 若 HEAD 通过、工作区失败 → 变化由**未提交改动**引入，需进一步看该改动是否属本 spec。
   - 若 HEAD 也失败 → **既有失败**。
3. **diff 语义核对**：`git diff <path>` 阅读改动内容，判断其功能域是否与目标 spec 相关。
4. **测试侧辅助**：检查失败测试是否 `import` 了本次改动的符号，或断言内容是否与解析器字段相关。

**应用到本次唯一发现（ruff SIM105）**：

- 位置：`backend/app/chat/application/conversation_service.py:903`（`try: worker.stop() / except Exception: pass`）。
- 该文件**不在 spec-033 改动集合内**。
- HEAD 基线对照：`git show HEAD:backend/app/chat/application/conversation_service.py` 导出到 `/tmp/cs_head.py` 后 `ruff check` → **All checks passed!**；而工作区版本失败。
- `git diff` 显示该文件新增了 `stop_all_workers()`（测试 teardown worker 清理），属**另一 agent 在途改动**，与 USENIX 解析器无关。
- 对 spec-033 触及文件单独 lint：`ruff check app/paper_discovery/infrastructure/usenix_paper_parser.py app/paper_discovery/infrastructure/usenix_publication_source.py` → **All checks passed!**
- **结论**：该 ruff error 是**其他在途改动引入的既有/旁支问题，不是 spec-033 回归**。因无法修改工作区去修复，且不属本 spec 范围，**标记为待人工复核（非 spec-033 阻塞项）**。

> 无「无法确证」的测试项：本次无测试失败；唯一 lint 项已通过 HEAD 对照确证归属。

---

## 4. 其他验证阶段（verification-loop）

| 阶段 | 命令 | 结果 |
|------|------|------|
| Build / 导入冒烟 | `cd backend && env -u PYTHONPATH ../.venv/bin/python -c "import app"` | **PASS** — `import app OK` |
| Types | 项目未配置 pyright/mypy，无类型检查门禁 | N/A |
| Lint（全 backend） | `cd backend && env -u PYTHONPATH ../.venv/bin/ruff check .` | **1 error（SIM105，conversation_service.py，非 spec-033）** |
| Lint（spec-033 文件） | `ruff check app/paper_discovery/infrastructure/usenix_paper_parser.py app/paper_discovery/infrastructure/usenix_publication_source.py` | **PASS — All checks passed!** |
| Tests | 上述 5 批定向测试 | **PASS — 311/311** |
| Security | 未做额外扫描（本任务为定向回归，非全量安全审计） | N/A |
| Diff | `git status --short` / `git diff --stat` | 工作区脏，含 spec-033 与在途 spec-032.1 改动；**未改动任何文件** |

---

## 5. 结论

**spec-033 是否引入回归：否。**

理由：5 个定向批次覆盖 USENIX 解析器 / 论文发现 / 候选 URL / 详情派发 / 前端契约（后端侧）/ 论文导入共 16 个文件，**311 个测试全部通过，0 失败 0 错误**；USENIX 核心基线（parser 47 + publication_source 42）与已知基线完全一致；`import app` 冒烟通过；spec-033 触及的两个源文件 ruff 干净。唯一 ruff error 位于无关的 `conversation_service.py`（其他在途改动新增 `stop_all_workers()`），经 HEAD 对照确证非本 spec 引入。

---

## 6. 边界声明

- 本次**未修改任何文件**（未用 Edit/Write 改代码，未用 `git checkout/restore/stash/reset`）。
- 本次**未跑全量测试**，仅跑任务指定的 5 批定向回归 + 导入冒烟 + ruff。
- 前端渲染/契约的浏览器侧核对**不在本角色范围**，交 `frontend-tester`。
- `--basetemp` 每批使用独立新目录（`/tmp/bt033_b1`…`b5`），避免残留状态导致假失败。
- 环境坑已规避：所有 pytest 调用均带 `env -u PYTHONPATH`。

## 7. 日志路径

`.codebuddy/agent-logs/spec-033/task-04/backend-tester/20260912-222459.md`
