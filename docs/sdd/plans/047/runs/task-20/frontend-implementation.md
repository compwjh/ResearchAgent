# spec-047 task-20 frontend-dev 自测结果（A + B + D）

- 角色：frontend-dev（ECC tdd-guide，TDD：先改测试跑 RED，再改实现跑 GREEN）
- 基线：origin/main 42bbc188；只改 frontend/** 与 tests/frontend/**，未改 backend/**、spec、台账、评审；未 commit / push / 合 main。
- 进展日志：.codebuddy/agent-logs/spec-047/task-20/frontend-dev/20261112-214742.md

## 1. 改动文件与行数

| 文件 | 改动 |
|---|---|
| frontend/index.html | :8 styles.css?v=76→?v=77；:902 research-tasks.js?v=25→?v=26；:913/:914 末尾注释区（:912 之后）新增 2 条纯属性 marker（v=25 / v=76），共 +2 行、2 行修改 |
| frontend/styles.css | :4409 灰卡 -value 色 var(--muted)→var(--muted-strong)；:4411-4413 新增 3 条仅带 needs_ground_truth 限定的 -samples/-detail-row/-params 文字色规则，共 +3 行、1 行修改；非灰卡基础规则 :4396/:4401/:4403/:4404 的 var(--muted) 逐字不动，:root 不动 |
| tests/frontend/test_evaluation_asset_versions.py | :100 / :118 精确 live 断言 [76]→[77]（2 行） |
| tests/frontend/test_evaluation_dataset_count_rendering.py | :86 注释同步 live 口径；:87 精确断言 v=76→v=77（2 行） |
| tests/frontend/test_evaluation_metric_grouping.py | :187 函数名 _77_and_75→_77_and_76；:189 精确断言 v=76→v=77（2 行） |
| tests/frontend/test_research_detail_actions_placement_contract.py | :223 f-string「为 75」→「为 76」+ 断言 ["76"]→["77"]（1 行） |
| tests/frontend/test_memory_return_global_contract.py | :210 同上（1 行） |
| tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py | _live_versions 新增 research-tasks.js 精确分支（+2 行）；:89/:90 同步计数断言 ==3/==0；:127 同步 [77]；末尾追加 R1 静态契约（+50 行，2 个新测试函数） |

共 9 个文件（2 个前端实现 + 7 个前端测试）。冻结断言（5 处 research-tasks.js?v=25 in INDEX、9 处 v=75 in INDEX、not in INDEX 断言、历史 marker、app.js 断言）均未改动。

## 2. 四条命令真实退出码

| 命令 | 退出码 | 结果 |
|---|---|---|
| node --check frontend/app.js | EXIT=0 | 通过（app.js 本任务未改） |
| .venv/bin/python -m pytest -q tests/frontend/ | EXIT=0 | 616 passed in 129.77s (0:02:09) |
| git diff --check | EXIT=0 | 无空白/冲突标记问题 |
| .venv/bin/python scripts/check_test_layout.py | EXIT=0 | 输出 "test layout: ok" |

说明：全量 pytest 因含 node 子进程耗时 2:09，工具前台执行到 46% 触发超时；改后台执行 + 结果文件落盘取回真实退出码（CMD1_EXIT=0 / CMD2_EXIT=0 / CMD3_EXIT=0 / CMD4_EXIT=0，DONE 标志齐备），非跳过、非截断判定。任务预告 check_test_layout.py 可能因 backend-dev 的 C 修复未落地而 EXIT=1；本次实测 EXIT=0，如实记录，未为凑绿改测试或脚本。

TDD RED 记录（实现落地前，定向 6 个改动测试文件）：EXIT=1，10 failed / 48 passed；失败全部为「实现未落地」预期红（live 版本仍 76/25、灰卡 -value 仍 --muted、新规则/marker 缺失），无语法或 collection 错误。

## 3. 三项自查

① 新 CSS 选择器与既有 class 对应、无新 class：
- styles.css :4396/-value、:4401/-samples、:4403/-detail-row、:4404/-params 基础规则存在；新增 4 条灰卡限定规则复用这 4 个既有 class，无新 class。
- app.js :7758/7793/7805/7813/7824 用 className 渲染这些 class（改 CSS 已反向确认被渲染）。
- 结论：通过。

② 版本号与断言同步、marker 位置：
- index.html :8 live styles.css?v=77、:902 live research-tasks.js?v=26；app.js?v=77 不动。
- 6 处精确 live 断言同步为 77：asset_versions.py:100/118、dataset_count_rendering.py:87、metric_grouping.py:189、research_detail_actions_placement_contract.py:223、memory_return_global_contract.py:210；另有 gray_contract.py:127/180 该文件内必要同步。
- 两个新 marker 在 :913/:914（:912 v=75 marker 之后、末尾注释区，均在 </body> 前、不在 <head>），纯属性片段含注释标记、不含 <script/<link 字面串；active_version 取 :8 首个 href="...styles.css?v=" = 77 > 68，未污染。
- 结论：通过。

③ 无 innerHTML：
- 本任务未改 frontend/app.js；新增内容为 HTML 注释 marker、CSS 颜色规则、Python 静态断言，无任何 DOM 写入；frontend/index.html 与新增测试文件内 grep innerHTML 均 0 命中。
- 结论：通过。

## 4. 静态契约（新增断言，test_evaluation_irrelevant_metric_gray_contract.py）
- 4 类灰卡文字色（value/samples/detail-row/params）均为 var(--muted-strong)；灰化规则块内不出现 var(--muted)。
- WCAG 复算 #5a5d66/#f6f6f8 ≥ 4.5:1（实算 6.0947:1，与既有 test_wcag_aa_contrast_for_badge_and_title 裁决值一致）。
- live _live_versions("styles.css") == [77]、app.js == [77]、research-tasks.js == [26]。
- v=25 与 v=76 marker 均恰好 1 条、在 HTML 注释内、不含 <script/<link。

## 5. 风险与阻塞
- 最小必要同步：test_evaluation_irrelevant_metric_gray_contract.py 原有 3 处断言（block.count("var(--muted-strong)")==2、count("var(--muted)")==1、_live_versions("styles.css")==[76]）在 D1/D2 后必然冲突，已同步为 ==3 / ==0 / [77]（期望值同步，非删断言、非改松正则、非 skip/xfail），否则 pytest 无法全绿。该文件是任务明确授权「追加断言」的文件。
- B 与 D2 在同一行（:223 / :210）叠加：f-string 文案按 B 改「为 75」→「为 76」，断言值按 D2 改 ["76"]→["77"]，严格按清单执行，未擅自统一口径。
- 真实浏览器 getComputedStyle 复核属 task-22（tester / 主会话）范围；本任务只做静态契约断言 + WCAG 复算。
- 无阻塞项；未改 backend/**、spec、台账、评审、其它测试；未 git commit / push / 合 main。

## 6. 日志路径
.codebuddy/agent-logs/spec-047/task-20/frontend-dev/20261112-214742.md
