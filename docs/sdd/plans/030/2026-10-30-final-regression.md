# Spec 030 Task10：最终候选后端全量回归

日期：2026-10-30  
角色：backend-tester  
状态：最新冻结后端候选 `dd54b11a` coverage 门槛通过，但全量 pytest 有 1 个失败。变更文件 Ruff 与测试命名/布局检查通过；历史全量证据均保留。该结果不替代 Task10 真实 API E2E、前端验证或部署门禁。

## 范围与隔离

按 Task10 和 Gate5/DoD 核对验收范围。仓库根没有 `pytest.ini`、`pyproject.toml`、`.coveragerc` 或 `setup.cfg` pytest/coverage 配置，README 的基本命令为 `.venv/bin/python -m pytest -q`。参考最近已落盘的全量候选命令 [`Spec043 Task11 command.sh`](../../plans/043/task-11-runs/final-regression/backend/command.sh)：收集 `tests`、排除 `tests/frontend`、启用 `offline_isolation`、`--cov=backend`、`--cov-fail-under=80`。本次使用该范围和同一 coverage 门槛，pytest 9.1.1、pytest-cov 7.1.0、Ruff 0.16.6。

五轮全量运行均使用 `env -i`，`PYTHON_DOTENV_DISABLED=1`，`RUN_E2E` 未设置；在线 provider 凭据为空，Ollama/E2E/embedding/reranker 目标指向不可用的 `127.0.0.1:9`。`offline_isolation` guard 拒绝外部 DNS、非 loopback 网络及既有真实服务端口。Research、memory、paper-discovery、KB、下载、缓存、临时目录和 coverage 输出分别隔离在 `/private/tmp/spec030-task10-final-backend-20261030/exit0/`、`exit1/`、`exit2/`、`exit3/` 与 `exit4/`。未启动服务、未调用模型、未访问生产数据库。前端 Node 测试按官方 backend 全量范围排除。

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

首轮多重集差分曾新增 2 项、消除 1 项：

- 新增：`backend/app/research/application/report_quality.py:191`，`SIM102`；`backend/app/research/application/report_quality.py:561`，`SIM102`。该模块在指定基线中不存在，属于当前 Spec030 候选新增实现，不能归为旧 lint。
- 消除：`backend/app/api/routes_research.py` 的 `I001` 导入排序诊断（基线行 33）。

修复并独立复审后，exit1 与冻结 exit2 候选相对基线均新增 **0 项**、消除 1 项（`routes_research.py` 的 `I001`）；exit2 的 57 项诊断均已有基线对应项。`ruff check .` 仍 exit 1，表示 exit2 仓库快照保留 57 个已有 backend lint 诊断；没有批量修改存量，也不把整体 Ruff 命令的 exit 1 冒报为 PASS。exit3 未运行 Ruff，不能将 exit2 的差分结论延伸为 `6f70303f` 的 lint 结论。exit4 仅检查自 exit3 以来变更的 Python 文件，不能替代全仓 Ruff 或基线差分。

## 验收判断与后续

- 冻结候选 `dd54b11a` backend 全量 pytest：**FAIL（1 个失败）**；coverage 82.24%，超过80%门槛。
- 失败用例为 `test_ollama_adapter_evaluator_allows_title_only_catalog_evidence`，需要 worker prompt 中包含 `metadata-only`，当前 contract 未包含。其余3,466项通过、3项skip。
- exit4 命名、布局及变更 Python 文件 Ruff：**PASS**；未运行全仓 Ruff。全仓 Ruff 基线差分最近一次证据来自 exit2 (`404279dd`)，不延伸为 exit4 结论。
- 本报告最新全量结果覆盖冻结候选 `dd54b11a` 和 backend/non-frontend tests。前端浏览器版本竞态所在的 `tests/frontend` 被官方后端全量命令排除，本报告不覆盖它。
- 未运行真实自然语言 API E2E、真实模型调用、部署验证或浏览器人工验收；这些仍是 Task10 / Gate5 后续门禁，不由 pytest/coverage 代替。

Progress log：`.codebuddy/agent-logs/spec-030/task-10/backend-tester/20261030-181300.md`。
