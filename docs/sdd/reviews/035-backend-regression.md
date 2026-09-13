# Spec 035 — 后端回归报告

> **主会话代行（原因）**：`backend-tester` 子代理两次执行均未能产出本报告（第一次因子代理 API 网络故障 `ENOTFOUND copilot.tencent.com` 中断；第二次因后台残留进程导致输出污染、报告未落盘）。按 `AGENTS.md`「代行」规则，本报告为**纯文档**（不含任何代码文件改动），由架构师主会话代行并在此留痕。
> 实际测试命令与结果均为真实执行，非转述。

## 一、结论

**未引入回归。** 全量回归 **1702 passed / 2 failed / 1 skipped / 62 subtests passed**，耗时 826.25s。
2 个失败经 `git worktree` 干净基线 `79cfa21` 验证为**改动前即存在的存量失败**，与 spec-035 无关。

## 二、最终全量回归

```bash
cd /Users/wjh/work/ResearchAgent-2/ResearchAgent
env -u PYTHONPATH .venv/bin/python -m pytest tests -q --basetemp=/tmp/s035-final
```

```
FAILED tests/test_chat_route.py::ChatApiTests::test_prompt_never_contains_secrets
FAILED tests/test_chat_route.py::ChatApiTests::test_record_generation_called_once_with_route
2 failed, 1702 passed, 1 skipped, 6 warnings, 62 subtests passed in 826.25s (0:13:46)
```

## 三、失败归因（用干净基线隔离）

归因方法（不动当前工作树，避免误伤 spec-034 在途改动）：

```bash
git worktree add /tmp/s035-base 79cfa21
cd /tmp/s035-base
env -u PYTHONPATH <主项目>/.venv/bin/python -m pytest \
    tests/test_chat_route.py tests/test_api_routes_coverage.py \
    tests/test_kb_upload_closure_matrix.py -q --basetemp=/tmp/s035-basebt
```

基线结果：

```
FAILED tests/test_chat_route.py::ChatApiTests::test_prompt_never_contains_secrets
FAILED tests/test_chat_route.py::ChatApiTests::test_record_generation_called_once_with_route
2 failed, 54 passed, 1 warning in 4.65s
```

| 失败用例 | 基线 `79cfa21` | 归因 |
|---|---|---|
| `test_chat_route.py::test_prompt_never_contains_secrets` | ❌ 失败 | **存量失败**，非本 spec 引入 |
| `test_chat_route.py::test_record_generation_called_once_with_route` | ❌ 失败 | **存量失败**，非本 spec 引入 |

## 四、本 spec 曾引入并已修复的 3 个回归

首次全量回归为 `5 failed / 1699 passed`，其中 3 个经基线比对确认为本次引入，已全部修复：

| # | 用例 | 根因 | 修复 |
|---|---|---|---|
| 1 | `test_api_routes_coverage.py::RunAgentBranchTests::test_run_chat_branch_reports_exception` | Task05 把 membership 校验换成 `is_model_available()`，而 44 处测试 patch 的目标是各路由**模块级** `get_available_models`；`is_model_available` 内部走 `ollama.get_available_models`，patch 静默失效 | 新增**纯函数** `is_online_model()`（不调 Ollama、不发网络请求），路由改回 `m not in get_available_models() and not is_online_model(m)`，保住模块级 patch 目标 |
| 2 | `test_api_routes_coverage.py::RunAgentBranchTests::test_run_chat_branch_streams_answer` | 同上 | 同上 |
| 3 | `test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered` | 改了 `backend/app/api/routes_kb.py`，而它在 spec-018 冻结清单中，sha256 不匹配 | 按 spec-020 BUG-08 惯例刷新 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` 中该项 sha256 与 `inventory_digest`（diff 仅 2 行） |

修复后复跑：上述 3 个**全部转绿**，`test_chat_route.py` 仅剩 2 个存量失败，无新增。

## 五、低消耗硬约束核对

本 spec 要求开发/验收阶段**只测连通性**，唯一允许的真实请求是 `max_tokens=1` 的最小 chat completion。
核对结果：新增 5 个测试文件（`test_online_model_registry` / `test_online_model_dispatch` / `test_online_models_api` / `test_online_model_probe` / `test_online_model_validation`）**全部使用 mock/monkeypatch，未发任何真实网络请求**，无 Key 环境下正常通过、未出现因缺 Key 而失败。

## 六、环境缺口（非实现缺陷）

- **C1**：本机 Ollama 指向局域网 `192.168.31.180:11434`，当前不可达 → 端侧模型列表为空，相关用例走降级路径。
- **C2**：未配置任何线上 Key → 线上模型列表为空，`status=ready/unreachable` 的真实探测路径未被执行。

## 七、备注：工作树含 spec-034 在途改动

`backend/app/api/routes_tools.py`、`backend/app/skills/tool_service.py`、`tests/test_tool_registry.py`、`tests/test_frontend_skill_tool_contract.py` 属 **spec-034（工具源码查看器）** 的未提交改动，本次全量回归包含它们且**未造成失败**，但不属 spec-035 范围，提交时需按文件隔离。
