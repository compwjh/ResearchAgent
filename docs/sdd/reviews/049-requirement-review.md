# Spec-049 需求评审（Gate 2 · 独立架构师评审）

| 项 | 值 |
|---|---|
| 评审者 | `architect`（架构师评审子代理） |
| 角色 | 架构师（Architect）— Gate 2 需求评审 |
| 模型 | `hy4`（读自 `.codebuddy/agents/architect.md:6` 的 `model` 字段） |
| 分派方式 | `Task(architect)` |
| 日期 | 2026-11-13 |

## 结论

**通过（附意见）** —— 非打回。

- P0 = 0，P1 = 0，P2 = 4；阻塞项 0。
- 附意见按 `SDD-GATE-CHECKLIST.md:73` 沉淀为强制约束清单 C1–C10（10 条，见 `docs/sdd/reviews/049-tech-review.md` §强制约束清单），供主会话回填 spec。
- 准入依据：`docs/sdd/SDD-GATE-CHECKLIST.md:65-73`；spec 状态 `已确认`（`docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:8`）。
- 评审范围（只读）：`docs/sdd/specs/049-known-nonblocking-followup-cleanup.md`、`docs/sdd/plans/049/README.md`、`task-02-refresh-spin-promise.md`、`task-03-nonblocking-ledger.md`、`task-04-verification-and-closure.md`、`docs/sdd/reviews/048-acceptance-review.md` §6、`docs/sdd/plans/048/runs/task-04/final-verification.md` §6、`docs/sdd/reviews/048-tech-review.md` C1–C10、`frontend/**`、`tests/frontend/**`。

## 事实依据（文件:行 / 命令）

### R1 目标与 10 项分类结论

| 检查点 | 事实依据 |
|---|---|
| 一句话目标 | `docs/sdd/specs/049-known-nonblocking-followup-cleanup.md:15`（9 类非阻塞项 + 1 项勘察补充逐条定案；唯一本次实现 NB2 改请求 Promise 结束移除；不虚报平台门禁全绿） |
| 10 项分类表 | `spec:35-46`（NB1–NB10 每行含编号 / 登记来源 / 勘察事实 `文件:行` 或命令 / 定案） |
| 分类小计 | `spec:48`：A 已闭环 2（NB1、NB9）、B 本次实现 1（NB2）、C 保持现状 7（NB3–NB8、NB10） |
| C 类定案 / 交付 | `spec:50-54`（逐条「保持现状，零改动」）；`spec:11,56,83`（省略 PR、fast-forward 推送远端 `main`、不 force push、不新建 PR） |
| 048 事实基线 | `docs/sdd/reviews/048-acceptance-review.md:169-181`（§6 九项，NB2 在 `:172`）、`docs/sdd/plans/048/runs/task-04/final-verification.md:61-63`（§6 700ms P2）、`docs/sdd/reviews/048-tech-review.md:121-134`（C1–C10） |

验证方式：`sed -n '37,46p' docs/sdd/specs/049-known-nonblocking-followup-cleanup.md | wc -l` = 10；`grep -n "分类小计" docs/sdd/specs/049-known-nonblocking-followup-cleanup.md` → 2/1/7；`docs/sdd/plans/049/runs/decision-ledger.md`（`task-03:19` 台账路径，执行后落盘）逐行核对「结论 + 事实依据」。

### R2 边界 1–12 可写成断言

| 边界 | spec:行 | 验证方式（命令 / 断言） |
|---|---|---|
| 1 | `spec:60` | `sed -n '1579,1587p' frontend/literature-maps.js \| grep -c "setTimeout"` = 0；`sed -n '1579,1587p' frontend/literature-maps.js \| grep -c "\.finally"` ≥ 1 |
| 2 | `spec:61` | `sed -n '3224,3242p;3470,3499p' frontend/literature-maps.js` 三路径均 `return`/resolve；E2E 三场景（成功 / catch `'error'` / `requestId` 失配提前 return）均 `is-spinning` 移除 |
| 3 | `spec:62` | E2E 连点 3 次：`is-spinning` 残留 0；`selectMap`/`loadMaps` 调用次数 = 点击次数 3 |
| 4 | `spec:63` | `grep -n "async function loadMaps\|async function selectMap" frontend/literature-maps.js` = `:3224` / `:3470`；`git diff` 不含两函数体 |
| 5 | `spec:64` | `tests/frontend/test_frontend_map_header_actions_readability.py:239,245,266`；`aria-label="刷新状态"` / `prefers-reduced-motion` / ≥44px 静态断言（`docs/sdd/reviews/048-tech-review.md:128-129,133` C4/C5/C9） |
| 6 | `spec:65` | `js_live == ["49"]`（`test_literature_map_tabs_and_refresh_icon.py:46`）；`grep -rn "literature-maps.js?v=48" frontend tests/frontend --include=*.py --include=*.html --include=*.js` = 0 命中；fixture `:1135` = `v=49` |
| 7 | `spec:66` | `frontend/index.html:918-919` 两 marker 逐字；`python -c "import re,pathlib;s=pathlib.Path('frontend/index.html').read_text();print(re.findall(r'literature-maps\.js\?v=(\d+)',s)[-1],re.findall(r'literature-maps\.css\?v=(\d+)',s)[-1])"` = `47 34`；`grep -rn "in INDEX" tests/frontend \| wc -l` = 211 |
| 8 | `spec:67` | `git diff -- frontend/literature-maps.css` 空；`frontend/index.html:11` `css?v=36`；`test_frontend_map_header_actions_readability.py:27` `MAP_CSS_VERSION = 36`；`frontend/index.html:8,905` `?v=77` 不变 |
| 9 | `spec:68` | `grep -rn "skip\|xfail" tests/frontend/` 无新增；`grep -c "^def test_" tests/frontend/test_literature_map_tabs_and_refresh_icon.py` = 12；`test_frontend_button_affordance_contract.py:52` = 56 |
| 10 | `spec:69` | `test -d .github`（不存在）；`grep -n "^fail_under" .coveragerc` = 0 命中；`.venv/bin/ruff check . --no-cache --output-format concise` → `Found 185 errors`；`git status --short` 未跟踪清单对照；台账 10 行 |
| 11 | `spec:70` | 文档核对（人工、非自动化断言）：`grep -rn "CI 全绿\|branch protection 通过\|覆盖率门禁达标" docs/sdd/reviews/049-*.md docs/sdd/plans/049/ docs/sdd/retro/` = 0 命中 → P2-1 |
| 12 | `spec:71` | 真实 API E2E 捕获响应（含实体 ID）+ `is-spinning` 响应结束后移除 + 状态栏更新；`.venv/bin/python -m pytest -q --cov=backend/app --cov-report=term-missing` `EXIT=0` 且通过数 ≥ 4571（`final-verification.md:13`） |

### R3 「明确不做」范围

- `spec:73-84` 共 10 条：`.github/workflows/**` / `.coveragerc` / 远端 branch protection / required checks / PR approval、批量 `ruff --fix` 与 185 个 lint 文件、Langfuse `:3000` / `LANGFUSE_*` / `deploy/langfuse/**` / 其它视图 404、未跟踪文件 / `.env.bak.*`、CSS / `css?v=36` / 窄屏 2px / `?v=` marker / `[-1]` 语义、`backend/**` / 数据模型 / 端点 / 其它视图 / header 作业按钮、Spec-048 历史、`skip`/`xfail`/改松断言、force push / 新建 PR、mock 或内部函数替代真实 API E2E。
- 三处复述：`task-02:44-51`、`task-03:37-43`、`task-04:45-51`。
- 验证方式：`git diff --stat` 白名单（`frontend/literature-maps.js`、`frontend/index.html`、`tests/frontend/fixtures/literature_map_component.html`、3 个测试 `.py`、本轮 `docs/sdd/**`、`docs/sdd/plans/049/**`）外 0 文件；`grep -rn "force\|--force\|gh pr create" docs/sdd/plans/049/` = 0 命中。

### R4 产品使用步骤

- 桌面 4 步 `spec:92-97`；窄屏 3 步 `spec:103-105`；失败恢复 4 行 `spec:114-119`；决策项核对 `spec:109-110`；产物路径 `spec:123-128`；每步含「操作 / 结果 / 等待条件 / 下一步」。
- 验证方式：`docs/sdd/reviews/048-acceptance-review.md:187`（桌面 4/4 + 窄屏 4/4 + 十项准备度 10/10）；`task-04:29`（桌面 1440×900 + 375×812 checks、截图 + JSON 落盘）；`docs/sdd/plans/049/runs/task-04/` 产物。

### R5 十项准备度与真实 API E2E

- 十项准备度阈值：`task-04:57`「≥9/10、无 P0/P1、无 API E2E 失败」；`048-acceptance-review.md:187`「10/10（≥9/10）」；`grep -n "准备度" docs/sdd/specs/049-known-nonblocking-followup-cleanup.md` = 0 命中 → P2-2。
- 真实 API E2E：`spec:71`（边界 12）、`spec:84`（不以 mock / 内部函数调用替代）、`task-04:29`（捕获真实 API 响应含实体 ID）、`final-verification.md:37`（E2E 18/18、88 个真实 API 响应、非 mock 非内部函数）、`task-04:47`。
- 验证方式：`task-04:28-30` 命令表；`docs/sdd/reviews/049-acceptance-review.md`（`spec:164` 预告路径）落盘。

## P0 / P1 / P2 判定

| 级别 | 数量 | 条目（事实依据 → 验证方式 → 约束） |
|---|---|---|
| P0 | 0 | 无目标缺失 / 范围失控 / 验证方式不可操作 |
| P1 | 0 | 边界 1–12 均有可执行断言或只读命令；分类小计 2/1/7 与 `spec:48` 一致 |
| P2 | 4 | 见下 |

- **P2-1（边界 11 为文档声明型）**：`spec:70` 为「不虚报」声明，验证方式为人工核对而非自动化断言。验证方式：`grep -rn "CI 全绿\|branch protection 通过\|覆盖率门禁达标" docs/sdd/reviews/049-*.md docs/sdd/plans/049/ docs/sdd/retro/` = 0 命中。→ **C9**。
- **P2-2（十项准备度阈值未落在 spec 正文）**：阈值在 `task-04:57` / `048-acceptance-review.md:187`，`grep -n "准备度" docs/sdd/specs/049-*.md` = 0 命中。验证方式：`docs/sdd/reviews/049-acceptance-review.md` 判定行按 ≥9/10 落盘。→ **C10**。
- **P2-3（边界 7 / NB8 的「211 处」口径）**：`grep -rn "in INDEX" tests/frontend \| wc -l` = 211（205 行含 `assert` + 6 行非 `assert`）；`grep -ro "in INDEX" tests/frontend \| wc -l` = 214（3 行各含 2 次）。验证方式：按行数 211 核对，字面串 214 不参与判定。→ **C6**。
- **P2-4（窄屏步骤数与验收判定口径）**：`spec:103-105` 为 3 步；`048-acceptance-review.md:187` 判定口径为「窄屏 4/4（键盘补充通过）」。验证方式：`task-04:29` 桌面 + 窄屏 checks 全 PASS 且判定栏写明口径。→ **C10**。

## 结论生效条件

- 本「通过（附意见）」以 `docs/sdd/reviews/049-tech-review.md` 的 C1–C10 为下游硬约束；`frontend-dev` / `frontend-reviewer` / `frontend-tester` / `tester` 只认落盘文档。
- `spec:162-164` 评审记录三行按真实结论回填；验收评审（`049-acceptance-review.md`）保持「待评审（未执行）」至 Gate 5。
