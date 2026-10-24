# Spec042 最终完整回归报告

## 当前结果：145f9d6 PASS

最新完整回归退出0：3335 passed / 0 failed / 2合法RUN_E2E skip / 67 subtests passed / 5 warnings，pytest报告耗时679.33s。完整命令、真实开始结束、隔离路径及日志见文末“最终候选复跑：145f9d6（最新）”与`runs/20261023-000644-145f9d6/metadata.json`。期间未改代码/断言或人工排除失败。

下方6f644bc通过、145f9d6首次390px超时均是保留的历史，不是当前失败或当前候选版本。

## 历史结果：6f644bc

- 结论：**PASS**
- 候选提交：`6f644bc`
- 分支：`codex/spec042-offline-evaluation`
- 开始时间（UTC）：`2026-10-22T18:07:59Z`
- 结束时间（UTC）：`2026-10-22T20:25:54Z`
- pytest 报告耗时：`718.29s`（`0:11:58`）
- `regression_exit_code`：`0`
- 统计：`3325 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`

## 执行与隔离

先通过了布局与命名门禁：

```text
.venv/bin/python scripts/check_test_layout.py  # exit 0
.venv/bin/python scripts/check_test_naming.py  # exit 0
```

完整回归使用显式 `.venv/bin/python`，未 source activate，未筛选、分片或人工 skip：

```text
.venv/bin/python -m pytest tests -q \
  -o cache_dir=/private/tmp/spec042-final-regression-g0xlTB/pytest-cache \
  --basetemp=/private/tmp/spec042-final-regression-g0xlTB/pytest-tmp
```

实际运行环境关闭 dotenv 与 Langfuse，`KB_DIR` 为临时根下的 `data/kb`；Qdrant、KB metadata、memory/literature-map/research/agent-tasks/paper-discovery SQLite、文章目录、浏览器 profile、pytest cache/temp 均位于唯一临时根：

`/private/tmp/spec042-final-regression-g0xlTB`

本轮未设置 `MEMORY_DIR`、`RUN_E2E`、模型/路由/embedding 覆盖变量；未停止或写入现有 8000/3000 服务。只读进程检查观察到的网络连接为本机 Ollama `127.0.0.1:11434`，未观察到 8000、3000 或外网连接。

## Skip 与 warnings

2 个 skip 均来自既有 `tests/e2e/test_research_lifecycle_e2e.py` 模块级条件：需要显式 `RUN_E2E=1` 并先启动 8000 服务。本轮按要求不设置 `RUN_E2E`，因此以下两个测试合法跳过，未新增 skip，也未把生产 E2E 纳入全量回归：

1. `test_research_task_create_shows_in_list`
2. `test_research_lifecycle_follow_through`

5 个 warnings 均为既有 SWIG 类型的 `DeprecationWarning`：`SwigPyPacked` 2 次、`SwigPyObject` 2 次、`swigvarlink` 1 次；无测试失败。

## 证据归档

- 原始回归日志：[full-regression.log](runs/20261022-180759-6f644bc/full-regression.log)
- 机器可读元数据：[metadata.json](runs/20261022-180759-6f644bc/metadata.json)
- 完整临时证据根：`/private/tmp/spec042-final-regression-g0xlTB`（保留，未删除）

报告生成未修改业务代码、测试断言或服务配置；本轮不执行部署、不提交、不推送。

## 最新候选追加回归：145f9d6

旧候选 `6f644bc` 的 PASS 证据保留不变。本次针对真实 E2E 修复后的新候选重新执行同一完整隔离回归，未筛选、未分片、未设置 `RUN_E2E`，退出码为 `1`，因此当前 Spec 收口状态为 **BLOCKED**：

- 开始时间（UTC）：`2026-10-22T20:37:24Z`
- 结束时间（UTC）：`2026-10-22T22:17:31Z`
- pytest 报告耗时：`648.27s`（`0:10:48`）
- `regression_exit_code`：`1`
- 统计：`3334 passed / 1 failed / 2 skipped / 67 subtests / 5 warnings`
- 临时证据根：`/private/tmp/spec042-final-regression-bm7F8l`

唯一失败：

```text
tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_drawers_single_pan_and_desktop_boundary[390]
```

失败发生在 `tests/frontend/test_frontend_map_mobile_contract.py:100` 的 Playwright `locator('[data-map-id="map-fixture"]').click()`：定位成功，但元素持续处于 `not stable`，30 秒后抛出 `playwright._impl._errors.TimeoutError`。这是可复现的前端运行时失败；tester 不修改代码、断言或 skip 掩盖它，需由对应开发/评审流程诊断修复后再进行新候选回归。

最新失败证据：

- [145f9d6 full-regression.log](runs/20261022-203724-145f9d6/full-regression.log)
- [145f9d6 metadata.json](runs/20261022-203724-145f9d6/metadata.json)

本轮仍未停止或写入现有 8000/3000 服务，未提交或推送；失败临时根保留供诊断。

## 最终候选复跑：145f9d6（最新）

在保留上述失败证据与 `mobile-regression-diagnosis.md` 的前提下，针对同一候选再次执行完整隔离回归；期间无代码/tests 变更，未设置 `RUN_E2E`，未筛选、分片或人工 skip。本轮通过：

- 开始时间（UTC）：`2026-10-23T00:06:44Z`
- 结束时间（UTC）：`2026-10-23T01:20:05Z`
- pytest 报告耗时：`679.33s`（`0:11:19`）
- `regression_exit_code`：`0`
- 统计：`3335 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`
- 2 个 skip：仍为未设置 `RUN_E2E=1` 的既有两个浏览器 E2E 用例，原因与前述一致
- 临时证据根：`/private/tmp/spec042-final-regression-GGaB59`

本轮日志与 metadata：

- [145f9d6 latest full-regression.log](runs/20261023-000644-145f9d6/full-regression.log)
- [145f9d6 latest metadata.json](runs/20261023-000644-145f9d6/metadata.json)

该 PASS 仅代表本轮真实完整回归结果；此前 `[390]` 失败日志和三次独立精确重跑通过证据均保留，未用 force-click、修改断言或删除 skip 掩盖。
