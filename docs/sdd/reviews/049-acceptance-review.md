# Spec-049 验收评审（Gate 5 · 签字 R）

> 只读评审。唯一产出：本文档。文档只写结论、事实依据（文件:行 / 命令）与验证方式。
> 依据文件：`docs/sdd/specs/049-known-nonblocking-followup-cleanup.md`、`docs/sdd/reviews/049-requirement-review.md`、`049-tech-review.md`、`049-frontend-review.md`、`docs/sdd/plans/049/runs/**`、`artifacts/spec-049-api-sample.md`。

## 1. 结论

**通过。READY。跨端集成验收 PASS。**

| 项 | 结果 | 依据 |
|---|---|---|
| 边界 1–12 | 12 / 12 通过 | §2 |
| C1–C10 | 10 / 10 满足 | §3 |
| 产品使用步骤 | 桌面 4/4、窄屏 3/3、决策项核对齐备、失败恢复 4 行 | §4 |
| 十项人工验收准备度 | 10 / 10（≥9/10） | §4 |
| 单端回归 | 628 passed / EXIT=0 | `frontend-regression.md:3,16-19,79` |
| 全量回归 | 4571 passed、2 skipped、EXIT=0、TOTAL 83.00% | `full-regression.txt:296-297`、`full-regression.exit:1` |
| 真实浏览器 E2E | 31/31 PASS、failed_checks=[]、conclusion=PASS | `browser-e2e.json`（passed=31 / total=31 / conclusion=PASS） |
| 真实 API 案例 | curl 原样响应含实体 ID | `artifacts/spec-049-api-sample.md:16,36,56,76,98-99` |
| 部署验证 | 4×200、live v49/v36、marker 47/34、PASS | `deploy-verification.json:7-10,13-24,26-32` |
| 跨端集成只读复核 | 4×200 | §9 C8 |
| 阻塞项 | 0 | §2、§3、§6 |

VERIFICATION REPORT：Build 不适用（纯前端交互修正，`spec:19,27`）；Types/Lint `node --check` EXIT=0（`frontend-regression.md:44-46`）、ruff `Found 186 errors`（§6 如实登记，历史基线 185 未改）；Tests `4571 passed, 2 skipped, 5 warnings, 69 subtests passed`、0 failed、coverage 83.00%（`full-regression.txt:297,:296`）；Security 无新增端点 / 数据模型 / 外发请求 / 凭据（`spec:19,27,93`）；Diff 7 tracked 文件（`git --no-pager diff --name-only`）；Overall READY。

未宣称「CI 全绿 / branch protection 通过 / 覆盖率门禁达标」：`test -d .github` → ABSENT；`grep -n "^fail_under" .coveragerc` → 0 命中；`grep -rnE "CI 全绿\|branch protection 通过\|覆盖率门禁达标" docs/sdd/reviews/049-*.md docs/sdd/plans/049/` 命中 6 行均为「不虚报」否定式声明（`049-requirement-review.md:48,76`、`049-tech-review.md:112`、`049-frontend-review.md:75`、`plans/049/task-04-verification-and-closure.md:48`、`task-03-nonblocking-ledger.md:42`）。

## 2. 边界 1–12 逐项判定

| 边界 | 判定 | 事实依据（文件:行 / 命令） |
|---|---|---|
| 1 | 通过 | `frontend/literature-maps.js:1581` add('is-spinning')、`:1583`/`:1586` 两处 `.finally(() => refreshButton.classList.remove('is-spinning'))`；`1579-1588` 段 `setTimeout=0` / `.finally=2` / `.catch=2`（§9 C1）；`implementation.md:7`；`049-frontend-review.md:54` |
| 2 | 通过 | 三路径静态 `049-tech-review.md:25-27`、`049-frontend-review.md:54`（`:3225-3243`、`:3471-3499`）；`browser-e2e.json` checks `spin_removed_after_response=true`、`spin_not_fixed_700ms=true`、`no_unhandled_rejection=true`；`spin_timeline` 三轮 `spin_add_events=1` / `spin_remove_events=1`；`api-sample.md:107` |
| 3 | 通过 | `browser-e2e.json` `multi_click_3_real_requests=true`、`multi_click_no_spin_residue=true`、`multi_click.clicks=3`、3×`status 200`、`spin_residue=0`；`049-frontend-review.md:56`；`implementation.md:14` |
| 4 | 通过 | `async` 实测 `:3225 loadMaps` / `:3471 selectMap` / `:3460 waitForPendingViewFlush`（§9 C2）；`git --no-pager diff -- frontend/literature-maps.js` 单 hunk `@@ -1577,13 +1577,14 @@`（`049-frontend-review.md:55`）；`node --check` EXIT=0（`frontend-regression.md:44-46`）。实测行号较 `spec:63` 引用 `:3224`/`:3470` 各 +1 行 |
| 5 | 通过 | `049-frontend-review.md:37`（`:1191-1197`、CSS `:615-617`、`:619`）、`:55`；E2E `refresh_aria_label` / `refresh_title_unchanged` / `refresh_no_visible_text` / `mobile_touch_target_ge_44` 全 true；`mobile_refresh_box` 44×44 |
| 6 | 通过 | `v=49` 五处：`frontend/index.html:903`、`tests/frontend/fixtures/literature_map_component.html:1135`、`test_frontend_map_groups_exports.py:53`、`test_frontend_map_mobile_contract.py:97`、`test_literature_map_tabs_and_refresh_icon.py:46`（`js_live == ["49"]`）；`v=48` 残留 0（§9 C3）；`deploy-verification.json:9,14` |
| 7 | 通过 | `frontend/index.html:918-919` 两条 marker 逐字；实算 `re.findall(...)[-1]` = `47 34`（§9 C4）；`grep -rn "in INDEX" tests/frontend \| wc -l` = 211（§9 C5）；`deploy-verification.json:19-24,29-30`；`049-frontend-review.md:38,59` |
| 8 | 通过 | `git diff -- frontend/literature-maps.css` 0 行（§9 C6）；`frontend/index.html:11` `css?v=36`、`:905` `app.js?v=77`；`MAP_CSS_VERSION = 36`（`test_frontend_map_header_actions_readability.py:27`）；`deploy-verification.json:10,17` |
| 9 | 通过 | `grep -c "^def test_" test_literature_map_tabs_and_refresh_icon.py` = 12（`049-frontend-review.md:61`）；`test_frontend_button_affordance_contract.py:52` = 56（`frontend-regression.md:23-25`）；diff 无 assert 删除 / skip / xfail（`049-frontend-review.md:61,100`） |
| 10 | 通过 | `decision-ledger.md:11-20`（NB1–NB10 逐条结论 + 依据）、`:24-37`（确认前后对照）、`:41`（C 类 7 项「保持现状、零改动」）；`test -d .github` → ABSENT；`grep -n "^fail_under" .coveragerc` → 0 命中；CSS diff 0 行；`git status --short` 未跟踪 16 项 = 历史 10 项全在 + 本轮 6 项新增文档（`decision-ledger.md:37`）；ruff 全仓 `Found 186 errors`，其中本轮新增未跟踪 `browser_e2e.py:224:13` B007 1 项、历史基线 185 项未改（§9 C7；数值差异在 §6 如实登记） |
| 11 | 通过 | §1「未宣称」段命令与命中行；`spec:70`；`049-requirement-review.md:48,76`；`049-tech-review.md:112` |
| 12 | 通过 | 真实 API：`artifacts/spec-049-api-sample.md:16,36,56,76`（`curl -s -i` 原样响应）、`:98-99`（`project_id` / `map_id`）、`:106-109`（状态栏、spin、连点 3×200）；`browser-e2e.json` `api` 373 条、`entity_ids`、`api_entity_id_present=true`、31/31 PASS；只读 curl 4×200（§9 C8）；全量 `full-regression.txt:297` `4571 passed`、`full-regression.exit:1` = `0` |

## 3. C1–C10 逐项判定

> 约束唯一落点 `049-tech-review.md:100-113`；Gate 4 复核 `049-frontend-review.md:52-63`（10/10 满足）。

| 约束 | 判定 | 事实依据（文件:行 / 命令） |
|---|---|---|
| C1 | 满足 | `literature-maps.js:1579-1588` `setTimeout=0` / `.finally=2` / `.catch=2`（§9 C1）；三路径 E2E（§2 边界 2）；`049-frontend-review.md:54` |
| C2 | 满足 | `async` `:3225` / `:3460` / `:3471`（§9 C2）；diff 单 hunk；`node --check` EXIT=0；按钮契约 `:1191-1197` 逐字（`049-frontend-review.md:55`） |
| C3 | 满足 | `multi_click` 3 次 3×200 / `spin_residue=0`；diff 无新增 `setTimeout` / 计数变量（`049-frontend-review.md:56,91`） |
| C4 | 满足 | `.catch(() => {})` `:1584` / `:1587`；E2E `no_unhandled_rejection=true`、`unhandled_rejection_count=0`、`page_errors=[]`、`errors=[]`、`no_pageerror=true`（`browser-e2e.json`） |
| C5 | 满足 | 五处 `v=49`（§2 边界 6）；`v=48` 0 命中；`css_live == ["36"]`（`:47`）、`MAP_CSS_VERSION = 36`、`?v=77` 不变（`049-frontend-review.md:58`） |
| C6 | 满足 | marker `:918-919` 逐字；`[-1]` = `47 34`；`in INDEX` = 211；`index.html` diff 单 hunk `@@ -900,7 +900,7 @@`（`049-frontend-review.md:59,98`） |
| C7 | 满足 | CSS diff 空；`is-spinning` CSS `:613` / `:616`；`grep -c "innerHTML"` = 0（§9 C6）；`?v=N` 已升 `v=49` |
| C8 | 满足 | `def test_` = 12、按钮基线 56、diff 无 assert 删除 / skip / xfail、新增 7 行静态契约断言（`049-frontend-review.md:61,100`；`implementation.md:14`） |
| C9 | 满足 | C 类文件不在 7 文件 diff 内；`.github` ABSENT；`fail_under` 0 命中；ruff 历史 185 未改（实测 186 见 §6）；台账 NB1–NB10 10 行；不虚报（§1、§2 边界 11） |
| C10 | 满足 | `implementation.md:95` 无 git 写操作、`git --no-pager log --oneline -1` = `b160c58d`（§9 C9）；真实 API E2E 31/31 + 全量 4571 / EXIT=0 + 准备度 10/10（§1、§4）；交付按定案（§8） |

## 4. 产品使用步骤与十项人工验收准备度

### 桌面 4/4（`spec:103-110`）

| 步 | 判定 | 依据 |
|---|---|---|
| 1 | 通过 | `deploy-verification.json:7-10` 4×200、`browser-e2e.json` `live_js_v49_200` / `live_css_v36_200` / `homepage_live_v49_v36`；只读 curl 4×200（§9 C8） |
| 2 | 通过 | `browser-e2e.json` `desktop_view_hash_route` / `tabs_present` / `refresh_button_exists` / `refresh_icon_node` |
| 3 | 通过 | `spin_added_on_click` / `refresh_triggers_maps_api` / `api_literature_maps_chain` / `spin_removed_after_response` / `spin_not_fixed_700ms` / `spin_duration_matches_promise` / `status_bar_nonempty`；`api-sample.md:106-108` |
| 4 | 通过 | `multi_click_3_real_requests` / `multi_click_no_spin_residue` / `no_unhandled_rejection`；`multi_click` 3×200、`spin_residue=0` |

### ≤760px 窄屏 3/3（`spec:112-118`）

| 步 | 判定 | 依据 |
|---|---|---|
| 1 | 通过 | `mobile_view_hash_route`、`tabs_present`（`browser-e2e.json`） |
| 2 | 通过 | `mobile_touch_target_ge_44`（`mobile_refresh_box` 44×44）、`mobile_no_visible_text`、`mobile_spin_ends` |
| 3 | 通过 | `mobile_no_spin_residue`、`mobile_no_visible_text_residue`、`status_bar_nonempty`、`mobile_spin_ends` |

判定口径：本 spec 窄屏为 3 步（`spec:112-118`）；`049-requirement-review.md:79`（P2-4）登记 048 曾用「4/4 键盘补充」口径，本次按 spec 3/3 判定。

### 决策项核对与失败恢复

- 决策项核对可操作：`spec:120-123`；`decision-ledger.md:11-20,24-37,41`；`git status --short` 16 项。
- 失败恢复表 4 行「现象 → 恢复动作」可操作：`spec:125-132`（图标永久旋转 / 仍是固定 700ms / 版本或 marker 断言失败 / 服务不可达）。

### 十项人工验收准备度（定义 `048-acceptance-review.md:156-165`；阈值 `task-04-verification-and-closure.md:57` ≥9/10）

| # | 准备度项 | 判定 | 依据 |
|---|---|---|---|
| 1 | 桌面 4 步可执行、主路径可复现 | 通过 | §4 桌面 4/4 |
| 2 | ≤760px 窄屏 3 步可执行 | 通过 | §4 窄屏 3/3 |
| 3 | 键盘切 tab / 表单值不丢（Spec-048 不回退） | 通过（静态契约） | `049-frontend-review.md:37,55`（`activateMapTab :1558`、tab DOM `:1552-1616` 逐字不变）；本轮无独立键盘 E2E check |
| 4 | 刷新旋转 / 状态刷新 / 无文字残留 | 通过 | `browser-e2e.json` `spin_added_on_click` / `status_bar_nonempty` / `refresh_no_visible_text` |
| 5 | 服务可启动 + `/api/health` 200 | 通过 | `deploy-verification.json:7`；只读 curl 200（§9 C8）；`api-sample.md:22` |
| 6 | live `v=49` / `css?v=36` 生效 200 + marker 说明 | 通过 | `deploy-verification.json:9-10,13-24`；`[-1]` = `47 34`（§9 C4） |
| 7 | 失败恢复清单可执行 | 通过 | `spec:125-132` 4 行 |
| 8 | 产物路径真实、无关键产物缺失 | 通过 | `spec:134-142`；14 个目标文件存在性核对；`refresh-desktop.png` / `refresh-mobile.png`；`browser-e2e-run1.json` 保留 |
| 9 | 单端 / 全量回归全绿、无 P0/P1、无 API E2E 失败 | 通过 | `frontend-regression.md:3`、`full-regression.txt:297`、`049-frontend-review.md:11-15`、`browser-e2e.json` `failed_checks=[]` |
| 10 | 三份独立评审结论真实、C1–C10 10/10、阻塞项 0 | 通过 | `049-requirement-review.md:13`、`049-tech-review.md:13`、`049-frontend-review.md:9,16`；§3 |

**准备度 10 / 10（≥9/10）。**

## 5. 首跑 FAIL 处置（如实登记，不翻案、不隐藏）

| 项 | 事实 | 依据 |
|---|---|---|
| 首跑结果 | `28/29`、`conclusion=FAIL`、`failed_checks=["spin_not_fixed_700ms"]` | `browser-e2e-run1.json`（passed=28 / total=29 / conclusion=FAIL；`:16` `spin_not_fixed_700ms: false`、`:2339` failed_checks） |
| 判定口径诊断 | 首跑判据 `0<elapsed<600` 与 run1 实测 `elapsed_ms` `3918.78`（desktop-first）/ `3698.1`（mobile），即 3.7–3.9s，不符；旧判定式源码未单独留存 | `browser-e2e-run1.json` `spin_timeline.desktop_first.elapsed_ms=3918.78`、`mobile.elapsed_ms=3698.1`；`grep -rn "600" browser_e2e.py` 0 判定字面命中（E2E 脚本未跟踪、无 .bak） |
| 口径修正 | `abs(elapsed_ms - 700) > 100`，native + throttled 双条件；旧 700ms 实现下该判据必 FAIL | `browser_e2e.py:208-210` |
| 新增 2 条更严断言 | `refresh_triggers_maps_api`、`spin_duration_matches_promise`（`\|spin_duration_ms_js - elapsed_ms\| < 500`）；checks 29 → 31 | `browser_e2e.py:211-214`；`browser-e2e.json` 与 `browser-e2e-run1.json` checks 键集合差（新增 2、删除 0） |
| 未改业务代码 | tracked diff 7 文件，frontend JS 无二次改动 | §9 C9；`implementation.md:95` |
| 未放宽断言 | run1 的 29 项 check 名在 final 中全部保留（删除 0），无 skip / xfail / assert 放宽 | `049-frontend-review.md:61,100`；checks 键集合差 |
| 首跑证据保留 | `browser-e2e-run1.json`（2341 行）与两张截图保留 | `ls docs/sdd/plans/049/runs/task-04/`；`api-sample.md:148` |
| 正式结果 | `31/31 PASS`、`conclusion=PASS`、`failed_checks=[]` | `browser-e2e.json` |

首跑 FAIL 不翻案、不隐藏；正式结果为修正判定口径后的真实浏览器 E2E。

## 6. 已知非阻塞项（如实列出，结论「保持现状、零改动」）

| # | 项 | 事实依据 | 结论 |
|---|---|---|---|
| 1 | 首跑 FAIL 记录 | `browser-e2e-run1.json` 28/29 FAIL（§5） | 保持现状、零改动 |
| 2 | Langfuse `:3000` transient | `spec:39`、`decision-ledger.md:13`、`048-acceptance-review.md:173` | 保持现状、零改动 |
| 3 | 其它视图 404 | `api-sample.md:141-146`（`console_errors` 8 条、4 个去重 404 URL）、`decision-ledger.md:14` | 保持现状、零改动 |
| 4 | 185 个历史 lint | `spec:41`、`decision-ledger.md:15,30`、`049-frontend-review.md:103` 记 `Found 185 errors`；Gate 5 全仓复核 `Found 186 errors`，多出 1 项为本轮新增未跟踪 `browser_e2e.py:224:13` B007（单文件 `Found 1 error`），历史 185 项未修改、未 `ruff --fix` | 保持现状、零改动（实测数值差异如实登记，不虚报 185） |
| 5 | 无真实 CI workflow / branch protection | `test -d .github` → ABSENT（`spec:42`、`decision-ledger.md:16`） | 保持现状、零改动 |
| 6 | 覆盖率未设 `fail_under` | `grep -n "^fail_under" .coveragerc` 0 命中；`full-regression.txt:296` 实测 83.00%（`spec:43`、`decision-ledger.md:17`） | 保持现状、零改动 |
| 7 | 窄屏 2px 余量 | `decision-ledger.md:18`（`visibleMap.height 152 ≥ 150`）、`frontend-regression.md:31` | 保持现状、零改动 |
| 8 | marker 既有脆弱性 | `spec:44`、`decision-ledger.md:18`（`re.findall(...)[-1]` 6 行 / `in INDEX` 211） | 保持现状、零改动 |
| 9 | 10 个未跟踪文件 | `decision-ledger.md:20,37`（NB10 历史 10 项）；`git status --short` 当前 16 项 = 历史 10 项全在 + 本轮 6 项新增文档，历史项未清理 / 未提交 | 保持现状、零改动 |

共 9 项。以上均不写成「已修复」，不虚报门禁达标。

## 7. 签字栏

- **验收签字 `tester`（跨端验收总控）· 签字 R**：通过（见 §1）。本签字仅代表跨端验收判定，不代表合并裁决。
- **开发主管签字 `architect` · 签字 A**：批准收口（`Task(architect)` 独立裁决，P0=0 / P1=0 / P2=0；落点 `docs/sdd/plans/049/runs/task-04/merge-decision.md` §2）。签字 R 与签字 A 并列、非自批。

## 8. 交付边界

| 项 | 结论 | 依据 |
|---|---|---|
| 交付方式 | 省略 PR、直接快进推送远端 `main` | `spec:11,56,96`、`decision-ledger.md:45`、`plans/049/README.md:20`、`task-04-verification-and-closure.md:50` |
| 不 force push | 是 | 同上；`grep -rnE -- "--force\|gh pr create" docs/sdd/plans/049/` 命中行均为否定式声明，无实际命令 |
| 不新建 PR | 是 | 同上 |
| 当前 git 状态 | HEAD `b160c58d` 未变、无 add / commit / push | `git --no-pager log --oneline -1`（§9 C9）、`git status --short`、`implementation.md:95` |

实际推送由 Gate 5 合并裁决签字 A 后执行；本分派未执行任何 git 写操作。

## 9. 附：本次只读复核命令与输出（验证方式汇总）

| 编号 | 命令 | 输出 |
|---|---|---|
| C1 | `sed -n '1579,1588p' frontend/literature-maps.js \| grep -c "setTimeout"` / `grep -c "\.finally"` / `grep -c "\.catch"` | 0 / 2 / 2 |
| C2 | `grep -n "async function loadMaps\|async function selectMap\|async function waitForPendingViewFlush" frontend/literature-maps.js` | `:3225` / `:3471` / `:3460` |
| C3 | `grep -rn "literature-maps.js?v=48" frontend tests/frontend --include=*.py --include=*.html --include=*.js` | 0 命中（EXIT=1）；`v=49` 4 处字面 + `:46` 数字断言 |
| C4 | `python3 -c "import re,pathlib;s=pathlib.Path('frontend/index.html').read_text();print(re.findall(r'literature-maps\.js\?v=(\d+)',s)[-1],re.findall(r'literature-maps\.css\?v=(\d+)',s)[-1])"` | `47 34` |
| C5 | `grep -rn "in INDEX" tests/frontend \| wc -l` | 211 |
| C6 | `git diff -- frontend/literature-maps.css \| wc -l`；`grep -c "innerHTML" frontend/literature-maps.js` | 0 / 0 |
| C7 | `test -d .github`；`grep -n "^fail_under" .coveragerc`；`.venv/bin/ruff check . --no-cache --output-format concise \| grep -i Found`；`.venv/bin/ruff check docs/sdd/plans/049/runs/task-04/browser_e2e.py --no-cache` | ABSENT / 0 命中 / `Found 186 errors.` / `Found 1 error.`（`:224:13 B007`） |
| C8 | `curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8000/<4 url>` | 200 / 200 / 200 / 200 |
| C9 | `git --no-pager diff --name-only`；`git --no-pager log --oneline -1`；`git status --short \| grep -c '^??'` | 7 文件 / `b160c58d` / 16 |
| C10 | `tail -12 docs/sdd/plans/049/runs/task-04/full-regression.txt`；`cat docs/sdd/plans/049/runs/task-04/full-regression.exit` | `TOTAL 51890 8820 83.00%`、`4571 passed, 2 skipped, 5 warnings, 69 subtests passed` / `0` |

## 10. 收尾修复记录

| 项 | 结论 / 事实 | 事实依据（文件:行 / 命令）与验证结果 |
|---|---|---|
| B007 修复 | `docs/sdd/plans/049/runs/task-04/browser_e2e.py:224` 修复前 `for i in range(3):` → 修复后 `for _ in range(3):`；仅该 1 行变化（changed_line_indices=[224]，total_lines=362） | `browser_e2e.py:224`；单行替换校验输出 |
| ruff 实测 | 全仓 `186 → 185`：`Found 186 errors` → `Found 185 errors` / `97 fixable`；单文件 `Found 1 error`（`:224:13 B007`）→ `All checks passed!` | `.venv/bin/ruff check . --no-cache --output-format concise`；`.venv/bin/ruff check docs/sdd/plans/049/runs/task-04/browser_e2e.py --no-cache` |
| E2E 重跑 | `31/31 PASS`、`conclusion=PASS`、`failed_checks=[]`、`EXIT=0` | `.venv/bin/python docs/sdd/plans/049/runs/task-04/browser_e2e.py`；`browser-e2e.json`（passed=31 / total=31 / failed_checks=[] / conclusion=PASS） |
| 首跑 FAIL 证据 | 保留不动：`browser-e2e-run1.json` sha 前后一致 `1a21cbde…`、2341 行、`28/29`、`conclusion=FAIL` | `shasum -a 256` 前后对比；`browser-e2e-run1.json` |
| 结论 | `通过 / READY` 保持 | §1 |
| 签字 | 签字 R 保持 | §7:138 |

原 §6:127 的 `Found 186 errors` 记录逐字保留，不改写。开发主管签字 A 已由主会话收口动作回填（见 §7:139），与签字 R 并列、非自批。
