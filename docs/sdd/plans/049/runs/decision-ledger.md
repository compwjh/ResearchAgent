# Spec-049 非阻塞项决策台账（NB1–NB10）

> **产出性质**：纯文档，由主会话代行落盘；三处留痕「本头部 / spec 变更日志 / `docs/sdd/spec-status-changelog.md` 收口条」。
> 文档只写结论、事实依据（文件:行 / 命令）与验证方式。
> 状态：任务 03 已完成；C 类 7 项零改动。

## 1. 逐项结论

| 编号 | 结论 | 事实依据（文件:行 / 命令） | 是否产生改动 |
|---|---|---|---|
| NB1 | **A 已闭环** | 单端 `628 passed / EXIT=0`（`048-acceptance-review.md:80`）；全量 `4571 passed / EXIT=0 / 83.01%`（`full-regression-final.txt:296-297`）；原 FAIL 记录逐字保留（`frontend-regression.md:114-118,232`） | 否 |
| NB2 | **B 本次实现** | `frontend/literature-maps.js:1579-1588` 删 700ms 定时器、两分支链 `.finally()` 移除 `is-spinning` + `.catch()` 兜底；`v=48 → v=49` 五处同步（`implementation.md` §1）；定向 `12 passed / EXIT=0` | 是（6 文件） |
| NB3 | **C 保持现状** | `LANGFUSE_ENABLED` 默认 `false`（`backend/app/platform/config.py:145-152`）；`deploy-verification.json:45` 登记 transient 告警；`browser-e2e.json` 无告警堆栈 | 否 |
| NB4 | **C 保持现状** | `browser-e2e.json:571` `"errors": []`；`deploy-verification.json:46` 登记「浏览器控制台其它视图 404」；`runs/task-04/` 无 404 URL / 堆栈记录 | 否 |
| NB5 | **C 保持现状** | `.venv/bin/ruff check . --no-cache --output-format concise` → `Found 185 errors`，`97 fixable`；`ruff.toml:35,45` 既有规则 | 否 |
| NB6 | **C 保持现状** | `test -d .github` → ABSENT；`docs/github.md:16`「规则说明，非真实 workflow」、`:28` 受保护分支条款；`merge-decision.md:88-89` | 否 |
| NB7 | **C 保持现状** | `.coveragerc:21`「刻意不设置 fail_under」；`grep -n "^fail_under" .coveragerc` 0 命中；`full-regression-final.txt:296` `TOTAL 83.01%` | 否 |
| NB8 | **C 保持现状** | `visibleMap.height 152 ≥ 150`（`frontend-regression.md:167`）；`re.findall(...)[-1] == "47"/"34"` 6 行 3 文件；`grep -rn "in INDEX" tests/frontend \| wc -l` = 211 | 否 |
| NB9 | **A 已闭环** | `docs/sdd/plans/048/runs/task-04/merge-decision.md` 已落盘且签字 A；`docs/sdd/specs/048-*.md:8` `当前状态：已完成`；台账 `实施中 → 已完成` 条已追加；`048-acceptance-review.md` 验收行与签字栏已回填 | 否 |
| NB10 | **C 保持现状** | `git status --short` 未跟踪清单：`api-merge.py`、`api-merge-result.json`、`.env.bak.spec047.20261109043121`、`.codebuddy/backup-untracked-047/`、`.playwright-cli/`、3 个 `.lock`、`artifacts/jd-agent-infra-capability-map.md` | 否 |

**分类小计**：A 已闭环 2 项（NB1、NB9）；B 本次实现 1 项（NB2）；C 保持现状 7 项（NB3–NB8、NB10，零改动）。

## 2. 确认前后状态对照（只读命令实测，2026-11-13）

| 核对点 | 命令 | 确认前 | 实现后 |
|---|---|---|---|
| `.github/` | `test -d .github` | ABSENT | ABSENT |
| 覆盖率阈值 | `grep -n "^fail_under" .coveragerc` | 0 命中 | 0 命中 |
| lint 债务 | `.venv/bin/ruff check . --no-cache --output-format concise` | `Found 185 errors` | `Found 185 errors` |
| marker `[-1]` 语义 | `python3 -c "import re,pathlib;s=pathlib.Path('frontend/index.html').read_text();print(re.findall(r'literature-maps\.js\?v=(\d+)',s)[-1],re.findall(r'literature-maps\.css\?v=(\d+)',s)[-1])"` | `47 34` | `47 34` |
| `in INDEX` 断言行数 | `grep -rn "in INDEX" tests/frontend \| wc -l` | 211 | 211 |
| tabs 静态契约用例数 | `grep -c "^def test_" tests/frontend/test_literature_map_tabs_and_refresh_icon.py` | 12 | 12 |
| 按钮基线 | `test_frontend_button_affordance_contract.py:52` | 56 | 56 |
| CSS | `git diff -- frontend/literature-maps.css` | 空 | 空 |
| CSS 版本 | `frontend/index.html:11` / `test_frontend_map_header_actions_readability.py:27` | `v=36` / `36` | `v=36` / `36` |
| 未跟踪文件 | `git status --short` | 10 项（见 NB10） | 10 项 + 本轮新增 `docs/sdd/specs/049-*`、`docs/sdd/plans/049/`、`docs/sdd/reviews/049-*`、`docs/sdd/plans/049/runs/` 文档 |

> 收尾修复事实：`browser_e2e.py:224` B007 已修复（`for i` → `for _`）；全仓 ruff 实测 `186 → 185`（`Found 185 errors` / `97 fixable`），本表「实现后」`185` 与实测一致（`:30`）。依据：`browser_e2e.py:224`、`.venv/bin/ruff check . --no-cache --output-format concise`。

## 3. C 类零改动结论

NB3–NB8、NB10 共 7 项：**保持现状、零改动**。未创建 `.github/workflows/**`、未改 `.coveragerc`、未改远端设置、未批量 `ruff --fix`、未启动 Langfuse、未改其它视图、未改 CSS / 窄屏余量 / marker、未提交或清理任何未跟踪文件。

## 4. 交付方式

省略 PR、直接快进推送远端 `main`；不 force push、不新建 PR。

## 5. 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-11-13 | 主会话（代行纯文档） | 任务 03：按 spec「只读勘察结论」表落盘 NB1–NB10 逐项结论与事实依据；采集确认前后状态对照；C 类 7 项写「保持现状、零改动」。 |
