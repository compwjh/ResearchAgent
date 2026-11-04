# Spec 030 Task10：最终候选后端全量回归

更新至：2026-10-31
角色：backend-tester  
状态：最新候选 `b43bbea0` 全量 pytest 与 coverage 门槛通过，命名/布局及两份变更测试的 Ruff 检查通过。`44752b60` 的全 backend Ruff 与基线差分、targeted findings 仍如实记录；此前 `dd54b11a` 失败及所有历史运行均保留。该结果不替代 Task10 真实 API E2E、前端验证或部署门禁。

## 范围与隔离

按 Task10 和 Gate5/DoD 核对验收范围。仓库根没有 `pytest.ini`、`pyproject.toml`、`.coveragerc` 或 `setup.cfg` pytest/coverage 配置，README 的基本命令为 `.venv/bin/python -m pytest -q`。参考最近已落盘的全量候选命令 [`Spec043 Task11 command.sh`](../../plans/043/task-11-runs/final-regression/backend/command.sh)：收集 `tests`、排除 `tests/frontend`、启用 `offline_isolation`、`--cov=backend`、`--cov-fail-under=80`。本次使用该范围和同一 coverage 门槛，pytest 9.1.1、pytest-cov 7.1.0、Ruff 0.16.6。

七轮全量运行均使用 `env -i`，`PYTHON_DOTENV_DISABLED=1`，`RUN_E2E` 未设置；在线 provider 凭据为空，Ollama/E2E/embedding/reranker 目标指向不可用的 `127.0.0.1:9`。`offline_isolation` guard 拒绝外部 DNS、非 loopback 网络及既有真实服务端口。Research、memory、paper-discovery、KB、下载、缓存、临时目录和 coverage 输出分别隔离在 `/private/tmp/spec030-task10-final-backend-20261030/exit0/` 至 `exit6/`。未启动服务、未调用模型、未访问生产数据库。前端 Node 测试按官方 backend 全量范围排除。

## 首轮候选 exit0（保留历史证据）

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| 命名 | `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | test naming check passed |
| 布局 | `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |
| 收集 | `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q tests --ignore=tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-backend-20261030/exit0/basetemp-collect`（同一隔离环境） | 0 | 3,444 项收集，无收集错误 |
| Backend 全量 + coverage | `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests --ignore=tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-backend-20261030/exit0/basetemp-full --cov=backend --cov-report=term-missing:skip-covered --cov-report=xml:/private/tmp/spec030-task10-final-backend-20261030/exit0/coverage.xml --cov-fail-under=80`（通过 `env -i` 运行，见上文隔离设置） | 0 | **3,441 passed，3 skipped，0 failed，8 warnings，67 subtests passed；239.75s** |
| 导入冒烟 | 隔离环境下 `/Users/wjh/ResearchAgent/.venv/bin/python -c 'import app'`（cwd=`backend`） | 0 | 通过 |
| Backend Ruff | `/Users/wjh/ResearchAgent/.venv/bin/python -m ruff check .`（cwd=`backend`） | 1 | 59 项诊断；与指定基线差分见下节 |

Coverage 汇总：**82.12%**（终端 TOTAL 显示 82%；51,160 statements，9,147 missed），80% 门槛已达到。JSON/XML/原始 coverage 与完整 pytest 日志均保留在隔离 tmp 目录；pytest log：`/private/tmp/spec030-task10-final-backend-20261030/exit0/logs/pytest-full.log`，coverage XML：`/private/tmp/spec030-task10-final-backend-20261030/exit0/coverage.xml`。

3 个 skip 的具体 node/reason 未被官方 `-q` 全量命令打印，本文不推断其身份。8 个 warning 为依赖导入弃用警告：5 条 SWIG 类型缺少 `__module__`，3 条 jieba 正则字符串无效转义；全量退出码不受影响。

## 最终后端候选 exit1

两处新增 `SIM102` 修复经 root 确认独立窄审通过后，对新后端快照使用新的 tmp 目录重跑；未覆盖 `exit0` 日志、coverage 或数据库。前端另有浏览器版本竞态变更，不属于本次后端测试收集范围。

候选冻结并开始检查：2026-10-30 18:22:55 CST；collect-only 日志完成时间：18:23:25 CST；完整 pytest 日志完成时间：18:27:54 CST（日志文件时间戳）。报告更新记录于 backend-tester 进度日志 18:28:46 CST。

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| 命名 | `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | test naming check passed |
| 布局 | `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |
| 收集 | `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q tests --ignore=tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-backend-20261030/exit1/basetemp-collect`（同一隔离环境） | 0 | 3,444 项收集，无收集错误 |
| Backend 全量 + coverage | `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests --ignore=tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-backend-20261030/exit1/basetemp-full --cov=backend --cov-report=term-missing:skip-covered --cov-report=xml:/private/tmp/spec030-task10-final-backend-20261030/exit1/coverage.xml --cov-fail-under=80`（通过与首轮相同的 `env -i` 隔离设置） | 0 | **3,441 passed，3 skipped，0 failed，8 warnings，67 subtests passed；242.25s** |
| 导入冒烟 | 隔离环境下 `/Users/wjh/ResearchAgent/.venv/bin/python -c 'import app'`（cwd=`backend`） | 0 | 通过 |

最终 coverage：**82.13%**（终端 TOTAL 显示 82%；51,158 statements，9,143 missed），80% 门槛通过。pytest log：`/private/tmp/spec030-task10-final-backend-20261030/exit1/logs/pytest-full.log`；coverage XML：`/private/tmp/spec030-task10-final-backend-20261030/exit1/coverage.xml`。3 个 skip 与 8 个依赖弃用 warning 的说明同首轮；`-q` 未打印 skip node/reason。

## 冻结 API 修复候选 exit2 (`404279dd`)

root 确认读取 API 修复已独立复审通过并提交为 `404279dd`，后端候选冻结后执行同一官方 backend 全量 pytest/coverage 命令。首个启动尝试因 `PYTHONPATH` 未包含官方离线插件目录，在 pytest 插件导入阶段退出 1，尚未收集或运行测试；错误保留于 `/private/tmp/spec030-task10-final-backend-20261030/exit2/logs/pytest-full-setup-failure.log`。随后按官方脚本使用共享插件目录 `/private/tmp/spec043-task11-final-backend-20261028/plugins` 重跑。该失败启动不计入测试结果。

pytest 完成日志时间：2026-10-30 18:38:04 CST；coverage XML 时间：18:38:03 CST。准确命令：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests --ignore=tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-backend-20261030/exit2/basetemp-full --cov=backend --cov-report=term-missing:skip-covered --cov-report=xml:/private/tmp/spec030-task10-final-backend-20261030/exit2/coverage.xml --cov-fail-under=80`，通过与前两轮相同的 `env -i` 离线隔离设置运行。

| 检查 | 退出码 | 结果 |
|---|---:|---|
| Backend 全量 + coverage | 0 | **3,449 passed，3 skipped，0 failed，8 warnings，67 subtests passed；253.05s** |
| Test naming | 0 | `test naming check passed: no spec/task numbers under tests` |
| Test layout | 0 | `test layout: ok` |
| Backend Ruff JSON | 1 | 57 项诊断；与指定基线差分新增 0 项 |

最终 coverage：**82.14%**（51,223 statements，9,147 missed），超过 80% 门槛。pytest log：`/private/tmp/spec030-task10-final-backend-20261030/exit2/logs/pytest-full.log`；coverage XML：`/private/tmp/spec030-task10-final-backend-20261030/exit2/coverage.xml`；隔离数据库与缓存仍仅位于 exit2 目录。`3 skipped` 和 `8 warnings` 的详细 node/reason 未由 `-q` 输出，本报告不推断其身份。

## 新增研究缺口提示规则候选 exit3 (`6f70303f`)

root 确认新增通用研究缺口提示规则已独立复审通过并提交为 `6f70303f`，后端候选冻结后使用与前轮相同的官方隔离 pytest/coverage 参数执行一次全量回归。pytest 日志完成时间：2026-10-30 23:26:04 CST；coverage XML 时间：23:26:03 CST。未覆盖 exit0、exit1 或 exit2 历史日志与 coverage。

准确命令：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests --ignore=tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-backend-20261030/exit3/basetemp-full --cov=backend --cov-report=term-missing:skip-covered --cov-report=xml:/private/tmp/spec030-task10-final-backend-20261030/exit3/coverage.xml --cov-fail-under=80`，通过 `env -i` 运行；环境设置与 exit2 相同，使用官方离线插件目录与独立 exit3 数据/cache/output 根目录。

| 检查 | 退出码 | 结果 |
|---|---:|---|
| Backend 全量 + coverage | 0 | **3,450 passed，3 skipped，0 failed，8 warnings，67 subtests passed；250.43s** |

最终 coverage：**82.15%**（51,223 statements，9,144 missed），超过 80% 门槛。pytest log：`/private/tmp/spec030-task10-final-backend-20261030/exit3/logs/pytest-full.log`；coverage XML：`/private/tmp/spec030-task10-final-backend-20261030/exit3/coverage.xml`；隔离数据库与缓存仅位于 exit3 目录。3 个 skip 和 8 个 warnings 的详细 node/reason 未由 `-q` 输出，本报告不推断其身份。本轮按 root 指定范围只运行全量 pytest+coverage，未重复 Ruff、命名/布局、独立 collect-only 或 import smoke。

## 最新冻结候选 exit4 (`dd54b11a`)

该候选包含 Intake 数量修复、主题与逐篇选集门禁，以及 memory post-run 绕过修复；root 确认已独立复审并完成部署健康检查。当前 workspace HEAD 为 `dd54b11a`。按已验证的官方隔离命令运行一次 backend 全量 pytest+coverage。pytest 日志完成时间：2026-10-31 00:40:19 CST；coverage XML 时间：00:40:18 CST。exit0 至 exit3 的日志、coverage 和隔离数据库均保留。

准确命令：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests --ignore=tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-backend-20261030/exit4/basetemp-full --cov=backend --cov-report=term-missing:skip-covered --cov-report=xml:/private/tmp/spec030-task10-final-backend-20261030/exit4/coverage.xml --cov-fail-under=80`，使用与 exit3 相同的 `env -i` 隔离变量、官方离线插件目录和 exit4 专用数据库/cache/output。

| 检查 | 退出码 | 结果 |
|---|---:|---|
| Backend 全量 + coverage | 1 | **1 failed，3,466 passed，3 skipped，67 subtests passed；264.66s** |
| 失败测试 | — | `tests/research/test_research_agent_approval_contract.py::test_ollama_adapter_evaluator_allows_title_only_catalog_evidence`；断言第121行要求 prompt 含 `metadata-only`，实际 contract 未包含该文案 |
| Test naming | 0 | `test naming check passed: no spec/task numbers under tests` |
| Test layout | 0 | `test layout: ok` |
| Ruff（仅本次改动的 Python 文件） | 0 | `All checks passed!`；未运行全仓 Ruff，不能据此宣称全仓 lint 全绿 |

coverage：**82.24%**（51,253 statements，9,103 missed），达到80%门槛，但 pytest 因上述单测失败不通过。完整日志：`/private/tmp/spec030-task10-final-backend-20261030/exit4/logs/pytest-full.log`；退出码文件：`/private/tmp/spec030-task10-final-backend-20261030/exit4/logs/pytest-full.exit`；coverage XML：`/private/tmp/spec030-task10-final-backend-20261030/exit4/coverage.xml`。本轮只运行隔离测试与静态检查，不改业务代码，不接触线上数据库、模型、外网或部署。

## 修复后冻结候选 exit5 (`44752b60`)

root 确认 `metadata-only` 提示回归已修复，新增安全分类白名单诊断且拒绝标准不变；候选 `44752b60` 已独立复审并部署。按 exit4 同一官方离线隔离命令跑一次最终 backend 全量 pytest+coverage；不运行真实 E2E。pytest 日志完成时间：2026-10-31 11:41:44 CST；coverage XML 时间：11:41:43 CST；exit0 至 exit4 历史日志和 coverage 均保留。

准确命令：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests --ignore=tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-backend-20261030/exit5/basetemp-full --cov=backend --cov-report=term-missing:skip-covered --cov-report=xml:/private/tmp/spec030-task10-final-backend-20261030/exit5/coverage.xml --cov-fail-under=80`，通过与 exit4 相同的 `env -i` 隔离设置、官方离线插件目录和 exit5 专用 DB/cache/output 执行。

| 检查 | 退出码 | 结果 |
|---|---:|---|
| Backend 全量 + coverage | 0 | **3,476 passed，3 skipped，0 failed，8 warnings，67 subtests passed；273.82s** |

coverage：**82.25%**（51,286 statements，9,102 missed），超过80%门槛。pytest log：`/private/tmp/spec030-task10-final-backend-20261030/exit5/logs/pytest-full.log`；退出码文件：`/private/tmp/spec030-task10-final-backend-20261030/exit5/logs/pytest-full.exit`；coverage XML：`/private/tmp/spec030-task10-final-backend-20261030/exit5/coverage.xml`。本轮仅运行隔离后端 pytest+coverage；真实 E2E 由 root 并行执行，本报告不重复或替代它。

## 测试 lint 修复后候选 exit6 (`b43bbea0`)

候选仅修改 `tests/research/test_report_content_rendering.py` 与 `tests/research/test_report_quality.py` 两个 Python 文件；生产代码仍与 `44752b60` 相同。按 root 指定沿 exit4 的官方隔离命令运行一次最终全量 backend pytest+coverage。测试日志完成时间：2026-10-31 11:56:01 CST；coverage XML 时间：11:56:00 CST；exit0–exit5 证据均保留。

准确命令：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests --ignore=tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-backend-20261030/exit6/basetemp-full --cov=backend --cov-report=term-missing:skip-covered --cov-report=xml:/private/tmp/spec030-task10-final-backend-20261030/exit6/coverage.xml --cov-fail-under=80`，沿用 exit4 的 `env -i` 隔离配置、官方离线插件目录及 exit6 专用数据库/cache/output。

| 检查 | 退出码 | 结果 |
|---|---:|---|
| Backend 全量 + coverage | 0 | **3,476 passed，3 skipped，0 failed，8 warnings，67 subtests passed；273.24s** |
| Test naming | 0 | `test naming check passed: no spec/task numbers under tests` |
| Test layout | 0 | `test layout: ok` |
| 两份变更测试 Ruff | 0 | `All checks passed!` |

coverage：**82.25%**（51,286 statements，9,103 missed），达到80%门槛。pytest log：`/private/tmp/spec030-task10-final-backend-20261030/exit6/logs/pytest-full.log`；退出码文件：`/private/tmp/spec030-task10-final-backend-20261030/exit6/logs/pytest-full.exit`；coverage XML：`/private/tmp/spec030-task10-final-backend-20261030/exit6/coverage.xml`。本轮只检查两份变更测试的 Ruff，不重跑全仓 Ruff/基线差分；production 候选未变化，按 root 指示沿用 exit5 结论。

## Ruff 基线差分

为定位而非修复存量 lint，使用 `git archive 7ef70517 ruff.toml backend` 在 `/private/tmp/spec030-task10-final-backend-20261030/baseline-source/` 生成临时源码快照，没有切换 checkout 或覆盖工作树。当前与基线均使用同一 `.venv` 的 Ruff 0.16.6、相同 `ruff check . --output-format=json` 命令及各自源码内 `ruff.toml`。

| 版本 | Ruff 诊断 | 命令退出码 |
|---|---:|---:|
| 基线 `7ef70517b1386f7d344df6af386b986013dbd91f` | 58 | 1 |
| 首轮候选 `exit0` | 59 | 1 |
| 最终候选 `exit1` | 57 | 1 |
| 冻结候选 `exit2` (`404279dd`) | 57 | 1 |
| 最新候选 `exit3` (`6f70303f`) | 未运行 | — |
| 最新候选 `exit4` (`dd54b11a`) | 未运行全仓；改动 Python 文件 Ruff 通过 | — |
| 最新候选 `exit5` (`44752b60`) | 57 | 1 |

首轮多重集差分曾新增 2 项、消除 1 项：

- 新增：`backend/app/research/application/report_quality.py:191`，`SIM102`；`backend/app/research/application/report_quality.py:561`，`SIM102`。该模块在指定基线中不存在，属于当前 Spec030 候选新增实现，不能归为旧 lint。
- 消除：`backend/app/api/routes_research.py` 的 `I001` 导入排序诊断（基线行 33）。

修复并独立复审后，exit1 与冻结 exit2 候选相对基线均新增 **0 项**、消除 1 项（`routes_research.py` 的 `I001`）；exit2 的 57 项诊断均已有基线对应项。`ruff check .` 仍 exit 1，表示 exit2 仓库快照保留 57 个已有 backend lint 诊断；没有批量修改存量，也不把整体 Ruff 命令的 exit 1 冒报为 PASS。exit3 未运行 Ruff，不能将 exit2 的差分结论延伸为 `6f70303f` 的 lint 结论。exit4 仅检查自 exit3 以来变更的 Python 文件，不能替代全仓 Ruff 或基线差分。

### `44752b60` 静态补核

工作树 HEAD 在检查时已前进至 `6cd5d2d1`。为只核对指定候选，使用 `git archive 44752b60` 在 `/private/tmp/spec030-task10-final-backend-20261030/candidate-44752b60-source/` 建立临时源码快照；未切换或修改共享 checkout。命名检查 `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` 与布局检查 `... check_test_layout.py` 均退出码0。

在该快照 backend 目录运行全局 `/Users/wjh/ResearchAgent/.venv/bin/python -m ruff check . --output-format=json`：退出码1，共57项；对同一 Ruff 0.16.6、相同命令的基线58项做路径规范化多重集比较，比较键明确为 `(相对文件路径, rule code, message)`，忽略行号迁移，结果新增0项、消除1项（`app/api/routes_research.py` 的 `I001`）。JSON 输出与退出码保留在 `/private/tmp/spec030-task10-final-backend-20261030/static-44752b60/`。这表示全仓 Ruff 仍有诊断，不是全绿。

再对从 `7ef70517` 到 `44752b60` 改动的 Python 文件运行 targeted Ruff，命令退出码1，共6项诊断。按路径、rule、message核对文件在 baseline 是否存在后，分类如下：

| 相对路径 | Rule | Message | `7ef70517` 核对 |
|---|---|---|---|
| `backend/app/api/routes_research.py:620` | `SIM105` | Use `contextlib.suppress(TypeError, ValueError)` instead of `try`-`except`-`pass` | baseline 存在相同路径、rule、message；存量 backend 诊断 |
| `tests/frontend/test_evidence_report_frontend_contract.py:3` | `I001` | Import block is un-sorted or un-formatted | baseline 文件存在，且对 baseline 版本单独运行 Ruff 得到相同诊断；此项属于前端测试，不计入 backend Ruff 差分或验收范围 |
| `tests/research/test_report_content_rendering.py:1` | `I001` | Import block is un-sorted or un-formatted | 文件在 baseline 不存在；Spec030 新增测试诊断 |
| `tests/research/test_report_content_rendering.py:28,104` | `B905` | `zip()` without an explicit `strict=` parameter | 文件在 baseline 不存在；Spec030 新增测试诊断（两处） |
| `tests/research/test_report_quality.py:1` | `I001` | Import block is un-sorted or un-formatted | 文件在 baseline 不存在；Spec030 新增测试诊断 |

因此，在这6项 targeted diagnostics 中，1项是已有 backend 存量，1项是 baseline 已存在的前端测试诊断，另4项属于 Spec030 新增的 research test 文件；4项不在全局 backend `ruff check .` 路径内。`git ls-tree` 确认 production `backend/app/research/application/report_quality.py` 在 baseline 不存在，候选中也没有 production `report_content_rendering.py`（只有 `tests/research/test_report_content_rendering.py`）。当前 production `report_quality.py` 与 `report_generation.py` 单独 Ruff 均退出码0。此前报告中的 I001 实际位于 `tests/research/test_report_quality.py`，不是 production `report_quality.py`；exit0 中曾有的两个 production `SIM102` 也已在后续候选修复，本次不再出现。targeted findings 未修复。

## 验收判断与后续

- 冻结候选 `dd54b11a` backend 全量 pytest：**FAIL（1 个失败）**；coverage 82.24%，超过80%门槛。
- 失败用例为 `test_ollama_adapter_evaluator_allows_title_only_catalog_evidence`，需要 worker prompt 中包含 `metadata-only`，当前 contract 未包含。其余3,466项通过、3项skip。
- exit4 命名、布局及变更 Python 文件 Ruff：**PASS**；未运行全仓 Ruff。全仓 Ruff 基线差分最近一次证据来自 exit2 (`404279dd`)，不延伸为 exit4 结论。
- 冻结候选 `44752b60` 全量 pytest 与 coverage 门槛：**PASS**（3,476 passed、3 skipped、coverage 82.25%）；其后另行完成了静态补核，结果见下文。
- `44752b60` 静态补核：命名/布局均 **PASS**；全 backend Ruff exit1、57诊断，相对 `7ef70517` 新增0、消除1；changed-Python Ruff exit1、6诊断，逐项见上文。
- 最新候选 `b43bbea0` 全量 pytest 与 coverage：**PASS**（3,476 passed、3 skipped、coverage 82.25%）；test naming/layout 和两份变更测试 Ruff 均 **PASS**。本候选生产代码与 `44752b60` 一致，未重复全仓 Ruff/基线差分。
- 本报告最新全量结果覆盖冻结候选 `b43bbea0` 和 backend/non-frontend tests。前端浏览器版本竞态所在的 `tests/frontend` 被官方后端全量命令排除，本报告不覆盖它。
- 本角色未运行真实自然语言 API E2E、真实模型调用、部署验证或浏览器人工验收；root 已另行报告部署健康检查 HTTP 200，并独立处理真实 E2E。这些证据不由 pytest/coverage 代替。

Progress log：`.codebuddy/agent-logs/spec-030/task-10/backend-tester/20261030-181300.md`。

## Spec 030 最终候选前端全量契约回归（frontend-tester）

日期：2026-10-31

检查候选：`b43bbea0`（执行 R3 时 HEAD；前端生产文件在本轮检查期间未改动）

范围：完整 `tests/frontend`、`frontend/research-tasks.js` 的 Node 语法，以及 Spec030 报告 feedback 的 DOM/CSS/版本/XSS 契约。共享解释器为 `/Users/wjh/ResearchAgent/.venv/bin/python`（Python 3.11.16，pytest 9.1.1）；Node 为 `/Users/wjh/.nvm/versions/node/v24.20.0/bin/node`（v24.20.0）。`command -v node` 已确认此路径，且三轮隔离 `PATH` 均显式包含 Node 目录。

### 隔离方式

所有轮次均以 `env -i` 启动；显式设置 `PYTHON_DOTENV_DISABLED=1`、`PYTHONDONTWRITEBYTECODE=1`、`PYTHONNOUSERSITE=1`，不继承 shell 中的凭据或 `.env` 配置。pytest cache 关闭，HOME、XDG cache、TMPDIR、basetemp 和日志均位于 `/private/tmp/spec030-task10-final-frontend-20261031/`。加载既有 `/private/tmp/spec043-task11-final-backend-20261028/plugins/offline_isolation.py`：外部 DNS/连接及常用真实服务端口被拒绝；根 `conftest.py` 将 memory 与 capability DB 隔离到每例临时目录。未安装软件、未启动服务、未触生产 DB 或模型。R2/R3 通过 `PLAYWRIGHT_BROWSERS_PATH` 只读复用已存在的 Chromium：`/Users/wjh/Library/Caches/ms-playwright`。

### 三轮完整结果

三轮均运行完整目录，没有挑选或排除测试。精确 pytest 参数均为 `-q -ra tests/frontend -p no:cacheprovider -p offline_isolation`。

| 轮次 | 精确启动命令 | 退出码与结果 | 说明 |
|---|---|---|---|
| R1 | `set -o pipefail; env -i HOME=/private/tmp/spec030-task10-final-frontend-20261031/home PATH=/Users/wjh/.nvm/versions/node/v24.20.0/bin:/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp/spec030-task10-final-frontend-20261031/tmp XDG_CACHE_HOME=/private/tmp/spec030-task10-final-frontend-20261031/cache PYTHONPATH=/private/tmp/spec043-task11-final-backend-20261028/plugins PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -ra tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-frontend-20261031/basetemp 2>&1 \| tee /private/tmp/spec030-task10-final-frontend-20261031/logs/pytest-frontend.log` | **1**；259 passed，100 skipped，29 failed | R1 的 100 个 skip 全由 `-ra` 明确报告为隔离 HOME 下 Playwright Chromium executable 不存在；26 个未 skip 的浏览器用例因此失败，另 3 个为下列静态断言。Node 路径已在 `PATH` 中，不是 Node 缺失。 |
| R2 | `set -o pipefail; env -i HOME=/private/tmp/spec030-task10-final-frontend-20261031/home PATH=/Users/wjh/.nvm/versions/node/v24.20.0/bin:/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp/spec030-task10-final-frontend-20261031/tmp XDG_CACHE_HOME=/private/tmp/spec030-task10-final-frontend-20261031/cache PLAYWRIGHT_BROWSERS_PATH=/Users/wjh/Library/Caches/ms-playwright PYTHONPATH=/private/tmp/spec043-task11-final-backend-20261028/plugins PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -ra tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-frontend-20261031/basetemp-r2 2>&1 \| tee /private/tmp/spec030-task10-final-frontend-20261031/logs/r2/pytest-frontend.log` | **1**；259 passed，100 skipped，29 failed；61.28s | 浏览器 binary 已找到；全部 100 个 skip 的 `-ra` 原因是 Playwright `TargetClosedError`。失败日志同时记录 Chromium `MachPortRendezvousServer` `Permission denied (1100)`；26 个未 skip 的浏览器用例未能运行。 |
| R3 | `set -o pipefail; env -i HOME=/private/tmp/spec030-task10-final-frontend-20261031/home PATH=/Users/wjh/.nvm/versions/node/v24.20.0/bin:/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp/spec030-task10-final-frontend-20261031/tmp XDG_CACHE_HOME=/private/tmp/spec030-task10-final-frontend-20261031/cache PLAYWRIGHT_BROWSERS_PATH=/Users/wjh/Library/Caches/ms-playwright PYTHONPATH=/private/tmp/spec043-task11-final-backend-20261028/plugins PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -ra tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-frontend-20261031/basetemp-r3 2>&1 \| tee /private/tmp/spec030-task10-final-frontend-20261031/logs/r3/pytest-frontend.log` | **1**；385 passed，0 skipped，3 failed；115.34s | 经 root 授权，仅该次 pytest 进程使用受控提升权限；Chromium 浏览器用例实际运行，R3 没有 skip。浏览器只从既有安装路径读取；没有更改系统或浏览器安全设置。 |

R1/R2 的 100 个 skip 与 Node 无关：R1 每条 skip 原因都指向隔离 HOME 下缺少浏览器 executable；R2 每条原因都是浏览器 launch 后 `TargetClosedError`，并有上述 Mach port 拒绝证据。R3 `-ra` 报告 0 skipped，验证了 Node 路径和 Chromium 权限均不再造成静默跳过或启动失败。R1/R2/R3 原始完整日志分别保存在上表 tee 路径。

### R3 未通过的三项静态合同

| 测试节点与断言行 | 期望 | 当前生产文件证据 |
|---|---|---|
| `tests/frontend/test_frontend_management_contract.py::test_keeps_static_asset_versions_and_scoped_css`，测试行 79 | `href="/assets/styles.css?v=66"` | [frontend/index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:8) 当前 stylesheet 为 `v=67`。紧接着的测试行 80 期待 app.js v66，与 [frontend/index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:807) 相符。 |
| `tests/frontend/test_paper_issue_ui_contract.py::test_report_action_uses_an_explicit_versioned_generation_button`，测试行 65 | `/assets/research-tasks.js?v=16` | [frontend/index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:804) 当前脚本版本为 `v=21`。 |
| `tests/frontend/test_paper_issue_ui_contract.py::test_report_action_failure_restores_the_previous_report_for_retry`，测试行 83 | 函数体含字面文案 `旧报告保持不变` | [frontend/research-tasks.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/research-tasks.js:2145) 保存 `previousReport`，错误恢复路径在 [frontend/research-tasks.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/research-tasks.js:2246) 恢复报告对象；当前实现没有该字面文案。 |

三项失败已回报 root，由 frontend-dev 同步已确认的当前版本/文案合同；本角色没有修改或弱化断言。R3 是修订前 `b43bbea0` 的全量结果，后续冻结候选 `58803f8c` 的最终复测见下文 R4；R4 结果取代 R3 作为最终前端回归结论。

### 静态核对

| 项目 | 结果 | 证据 |
|---|---|---|
| JavaScript 语法 | PASS，退出码 0 | `/Users/wjh/.nvm/versions/node/v24.20.0/bin/node --check frontend/research-tasks.js` |
| DOM/class 与 CSS 作用域 | PASS | `research-report-feedback` DOM 在 `frontend/index.html:331`，JS 使用点 `frontend/research-tasks.js:2823`；动态 `.research-report-quality-metric` 在 JS 行 2838 与 CSS 行 3724 对应；新样式限定 `#research-view`，`frontend/styles.css:3719–3727`。 |
| 资源版本 | PASS | [frontend/index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:804) `research-tasks.js?v=21`；[frontend/index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:8) `styles.css?v=67`。 |
| XSS | PASS | `rg -n 'innerHTML' frontend/research-tasks.js` 退出码 1、无命中；生成的指标 label/value 在 `frontend/research-tasks.js:2839–2840` 经 `textContent` 写入，其余文案经 `setText`。 |

进度日志：`.codebuddy/agent-logs/spec-030/task-00/frontend-tester/20261031-121331.md`。

### 最终复测 R4（冻结候选 `58803f8c`）

root 完成独立 review 并冻结 `58803f8c`；提交只更新上述三个静态合同预期及交接/评审文档，`frontend/**` 与 `backend/**` 生产文件未变。当前 HEAD 为 `58803f8c`，前端与后端目录工作树干净。复用 R3 已验证的隔离环境、Node PATH、offline guard 和现有 Chromium 路径；全部 388 项实际执行。

准确命令：

```sh
set -o pipefail; env -i HOME=/private/tmp/spec030-task10-final-frontend-20261031/home PATH=/Users/wjh/.nvm/versions/node/v24.20.0/bin:/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp/spec030-task10-final-frontend-20261031/tmp XDG_CACHE_HOME=/private/tmp/spec030-task10-final-frontend-20261031/cache PLAYWRIGHT_BROWSERS_PATH=/Users/wjh/Library/Caches/ms-playwright PYTHONPATH=/private/tmp/spec043-task11-final-backend-20261028/plugins PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -ra tests/frontend -p no:cacheprovider -p offline_isolation --basetemp=/private/tmp/spec030-task10-final-frontend-20261031/basetemp-r4 2>&1 | tee /private/tmp/spec030-task10-final-frontend-20261031/logs/r4/pytest-frontend.log
```

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `tests/frontend` 全量回归 | **0** | **388 passed，0 skipped，0 failed；112.29s** |
| `/Users/wjh/.nvm/versions/node/v24.20.0/bin/node --check frontend/research-tasks.js` | **0** | JavaScript 语法通过 |

R4 的 `pytest -ra` 日志没有 `SKIPPED` 条目，Chromium 启动成功；此前 R3 失败的 browser cases 在 R4 均实际运行并通过。所有测试环境约束与上文隔离方式相同；只读复用已安装 Chromium，没有安装依赖、改系统设置、启动服务或访问真实 DB/模型。R4 日志：`/private/tmp/spec030-task10-final-frontend-20261031/logs/r4/pytest-frontend.log`。最终前端全量回归 **PASS**。
