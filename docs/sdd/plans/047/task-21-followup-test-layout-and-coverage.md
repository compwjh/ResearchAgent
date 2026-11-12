# task-21 追加范围五：测试布局合规（C）与覆盖率采集（E1）

> **产出性质**：纯文档任务书，由主会话代行创建（三处留痕：本头部 / spec 追加范围五 §7 / 状态台账 2026-11-12 收口条）。
> **状态**：`已完成`；**分派**：`backend-dev`（C 的测试文件改名与 fixture 迁移）· 主会话（E1，纯配置与报告）。

## 一、目标与前置条件

前置：task-20 的版本与静态契约已定稿，避免改名测试与新增断言互相踩踏。

目标：C — 4 个 `test_taskNN_*.py` 按能力改名、`tests/conftest.py` 的 `clean_warmup_registry` fixture 等价迁到仓库根 `conftest.py`，使 `scripts/check_test_layout.py` EXIT=0；E1 — 新增 `.coveragerc` 采集配置并跑出本地覆盖率实测报告。

## 二、实施与文件边界

- 4 个 `git mv`（均 `R100`，文件内 0 行改动，docstring 中历史 task 编号按规则保留）：`test_fallback_reproducibility.py` / `test_score_idempotency.py` / `test_observability_decoupling.py` / `test_trace_identity_redaction.py`。
- 根 `conftest.py` 原本已存在且含 spec-038 P3 的 5 个 `autouse=True` fixture，**不可 `git mv -f` 覆盖**；采用等价迁移：把 `tests/conftest.py` 第 31 行起的 fixture 块逐字复制入根文件，`diff -u` EXIT=0 后 `git rm tests/conftest.py`。
- 新增 `.coveragerc`：`source = backend/app`、`branch = False`、`show_missing = True`，忽略 tests / migrations / 缓存；**不设 `fail_under`、不改 pytest 默认 `addopts`**。
- 不改 `backend/**` 业务逻辑、不重写历史归档报告中的旧测试路径、不删断言。

## 三、验收

- `.venv/bin/python scripts/check_test_layout.py` → `test layout: ok` / EXIT=0（原 EXIT=1 / 5 项违规）。
- 4 个改名测试 `39 passed`；conftest 迁移后后端定向 `37 passed`；`pytest --fixtures` 可见 `clean_warmup_registry -- conftest.py:124`。
- 全量回归 `.venv/bin/python -m pytest -q --cov=backend/app --cov-report=term-missing` → EXIT=0，`4559 passed`，`TOTAL 83.02%`。

## 四、风险与回滚

风险：fixture 若被覆盖删除会导致 `tests/system/` / `tests/kb/` 的包装 fixture 失效；已用等价迁移 + `diff -u` 规避。覆盖率配置若设阈值会让主干红灯；刻意不设。回滚：`git revert` 本任务 commit。

## 五、产出与执行结果

- 实现自测报告：`docs/sdd/plans/047/runs/task-20/backend-implementation.md`（已读回校验）。
- 覆盖率报告：`runs/task-20/full-regression-coverage.txt` / `.exit`。
- 进展日志：`.codebuddy/agent-logs/spec-047/task-20/backend-dev/20261112-214806.md`。
- **执行结果：`已完成`**；覆盖率 83.02% 如实登记，未虚报、未改阈值凑绿。
