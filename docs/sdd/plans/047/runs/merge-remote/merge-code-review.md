# spec-047 远程合并 — 独立 Code Review / 开发主管审批结论

> 依据 `docs/github.md` 第 11 条「PR 必须由开发主管（或另一 Agent）审查并批准，至少 1 个 approval」与 `docs/sdd/pr-template.md:4,13,33-34` 合并门禁出具。
> 本报告为**独立只读审查**，不构成对合并的批准（结论见第七节）。

## 一、头部四项

| 项 | 内容 |
|---|---|
| **评审者** | `architect` 子代理（独立 Code Review / 开发主管批准者），与实现方（主会话 / dev）分离 |
| **角色** | `architect` —— 对应 `docs/github.md:11` 所要求的「开发主管（或另一 Agent）」独立审查者；对 PR 合并做裁决 |
| **模型** | 腾讯混元 Hy（Tencent Hunyuan Hy） |
| **分派方式** | 由主会话以 Task 方式派发的**独立审查子代理**；只读工具集（无 Write），仅产出本报告 + 进展日志，不改代码 / 配置 / 评审历史 / E2E 证据 |

## 二、审查对象与证据时点

- 分支 `feature/spec-047-merge-remote`，HEAD = `49486e7f`（=`origin/main`），基线 `1b26c76c`（主干其后前进 5 个 UX/KB 提交）。
- 待审对象：`git merge --squash` 产生的已暂存待提交单条变更。`git diff --cached --stat` = `309 files changed, 65543 insertions(+), 237 deletions(-)`；未暂存改动 0（全部在 index）。
- 回归证据时点（**如实记录两次读取，全程未预判**）：首次读取 `docs/sdd/plans/047/runs/merge-remote/full-regression.txt` 仅 26→41 行、进度约 42%→65%、进度条已现多处 `F`、**无最终汇总行**；终局读取为 230 行、含 `FAILURES` 段与 `PYTEST_EXIT=1`。两次均未据未完成状态宣称通过。
- 本审查**未重复跑全量回归**（仅 Read 主会话已落盘的回归结果）、未跑真实 API 打分、未重启服务、未 commit / push / 合 main。
- 定向「7 个前端契约文件 69 passed」为主会话背景陈述，本次**未独立复跑**；且该子集不含 `test_research_task_search.py` 与 `tests/kb/test_kb_upload_closure_matrix.py`，**无法覆盖全量 6 failed**。回归结果中的 `69 subtests passed` 是 pytest subtests 计数，与定向数字巧合，不得混用。

## 三、逐条核实结论（每条附证据）

### 要点 1 — 5 处冲突解决是否保住双方功能

| # | 文件 | 策略 | 核实结论 | 证据 |
|---|---|---|---|---|
| ① | `frontend/research-tasks.js` | 取主干版本 | **形式上一致，但造成功能回退（见 P0-1）** | `git diff --cached -- frontend/research-tasks.js` 空、`staged-change=0`、`git diff HEAD --` 空 → 主干版本原样保留。但三分支符号对比：旧分支 `research-task-search`=8 / `runTaskIdLookup`=2 / `bindTaskSearch`=2，主干与合并后均 **0** |
| ② | `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` | 取主干版本 | **形式上一致，但造成哈希失配（见 P1-1）** | staged diff 空；文件存在 30189B / 765 行。三方哈希：主干矩阵 main.py=`85c9beb1…`、旧分支矩阵=`cfeea4e5…`、合并后矩阵=`85c9beb1…`，而合并后 main.py=`cfeea4e5…` → 失配 |
| ③ | `frontend/styles.css` | 双方 union | **通过** | `git diff --cached` 仅在 `:4370` 后追加 56 行 `#evaluation-view …` 评测 CSS；主干 `.truncate/.hash-inline/.clamp-3/button` 规则作上下文行保留、无 `-` 删除行；选择器前缀互不重叠 |
| ④ | `docs/sdd/reviews/045-acceptance-review.md` | 双方 union | **通过** | 主干 175 行（含「## 开发主管签字（留空…）」）之后追加 190 行我方完整验收报告 + 架构师签字 + 收口状态；文件现 364 行，两份历史报告都在 |
| ⑤ | `frontend/index.html` | 定制 | **通过** | cached diff 唯一 `-` 行为 `app.js?v=74`→`app.js?v=77`，其余全 `+`（评测 nav/视图 + 搜索栏 + 兼容 marker），主干 DOM 无删除行。实查 live：`index.html:8 styles.css?v=75`、`:902 research-tasks.js?v=25`、`:903 literature-maps.js?v=47`、`:905 app.js?v=77`；`grep -nE '<!--.*(<script|<link)'` 命中 0 → 兼容 marker 为纯属性片段、不污染 `_live_versions` 正则 |

**结论**：③④⑤ 保住双方功能；①②「取主干」的**决策本身**分别引入功能回退与哈希失配（详见第六节 P0-1 / P1-1），不能视为「已保住双方功能」。

### 要点 2 — 冲突标记与 app.js 评测功能

- **无残留冲突标记**：全仓 staged `git grep --cached -n -E '^(<<<<<<<|=======$|>>>>>>>)'` → `exit=1`（0 命中）；4 个前端文件（`index.html`/`styles.css`/`research-tasks.js`/`app.js`）同样 0 命中。初扫 `=======` 命中项均为历史日志 / pytest / `.py` 源文件的分隔线误报，已用精确锚点澄清。
- **app.js 评测功能仍在**：`app.js:7746 renderEvaluationMetricCard`、`app.js:7939 submitEvaluationScore`、`app.js:7908/8027 appendEvaluationGroupedRows`、`app.js:7873-7880` 分组 class（`evaluation-metric-group/title/cards`）。
- **补充发现（负面）**：合并后 `index.html:249-255` 保留了搜索栏 DOM（6 个 `research-task-search*` id），但 `frontend/*.js` 中 `research-task-search` 命中 0（`grep -rnE 'research-task-search' frontend/` 仅见 index.html）→ **孤儿 DOM**，与要点 1①相互印证。

### 要点 3 — 4 类测试断言修改是否「只同步期望值、未删断言 / 未放宽 / 未绕过」

- **通过的部分**（`git diff --cached` 相对主干的净改动）：
  - `test_frontend_button_affordance_contract.py`：仅 +2 行注释 + `BASELINE_COUNTS["index.html"] 25→28`；`UNDECORATED = re.compile(r"(?<![\w.-])secondary-button(?![\w-])(?!\s+btn-outline)")`（`:42`）与 `test_every_real_button_carries_btn_outline`（`:93`）**逐字未动** → **未改松正则**。
  - `test_memory_return_global_contract.py`：仅 +1 行注释 + `live_app == ["74"]→["77"]`；`live_css == ["75"]` 未动。
  - 4 个评测契约文件相对旧分支：`styles.css?v=73→v=75` 共 4 处（`test_evaluation_asset_versions.py` 2 处、`test_evaluation_dataset_count_rendering.py` 1 处、`test_evaluation_metric_grouping.py` 1 处），均为期望值同步、无断言删除。
  - **btn-outline 是真加到按钮上**：`git diff --cached -- frontend/index.html` 中 3 个新增 `secondary-button`（`research-task-search-retry` / `evaluation-runs-refresh` / `evaluation-compare-button`）**全部带 `btn-outline`**；当前 index.html `secondary-button` 总数 28、带 `btn-outline` 28、不带者 0（与 `BASELINE_COUNTS=28` 自洽）。
- **未通过的部分（漏同步，见 P0-2）**：主干自带契约 `test_research_detail_actions_placement_contract.py`（`git cat-file -e HEAD:…` = `IN-MAIN`，`staged=0`）`:224 assert live_app == ["74"]` 未同步；`:219` 等 `in INDEX` 字符串断言因 v=74 纯属性 marker（`index.html:911`）保留而可过，但精确正则断言必挂。`test_research_tab_width_stability_contract.py:126` 为字符串 `in INDEX`（可过），`test_frontend_literature_map_contract.py:30-35` 为 `>=59/>=57` 下界（可过）。经 `grep -rnE '(live_app|live_css)\s*==\s*\[' tests/frontend/*.py` 全扫，仅此一处精确期望值过期。

### 要点 4 — 反伪造 / 不降级红线未被合并破坏

- `backend/app/evaluation/contracts.py:181-204` `build_metric`：`if status != COMPUTED: value = None` 且 `if not payload_detail.get("reason"): raise ValueError(...)` → 非 computed 一律 `value=null` + `detail.reason` 必填；`uncomputed_metric` 复用同一入口。`metrics.py:576,582,597,686,798-838` 保留「不回退冻结 output、不静默记 0、不写 100 冒充」「批量判官全部不可用整批不出分」等文案。
- **22 key / 5 group**：`.venv/bin/python` 静态复算 `METRIC_KEYS=22`、`METRIC_GROUPS distinct=5`（`answer_quality/generation/intent/retrieval/safety`），`contracts.py:39/88/198` 定义齐备。
- **五端点**：`routes_evaluation.py:40/45/50/55/60` = `/evaluation/options`(GET)、`/score`(POST)、`/runs`(GET)、`/runs/{run_id}`(GET)、`/compare`(GET)。
- **跨 dataset 早退**：`service.py:163/179/189/235` 各 `dataset_id != …` 早退 + `service.py:288`「跨 dataset 一律早退：不加载 042 轨迹、不发任何生成 / 判官调用（原口径逐字保留）」。
- **未被合并改动**：`git diff <旧分支> -- backend/app/evaluation/ backend/app/api/routes_evaluation.py` 为空（评测后端原样带入）。
- **结论**：要点 4 通过；本次 6 个失败无一落在评测反伪造 / 不降级红线。

### 要点 5 — `docs/sdd/pr-template.md` 合并门禁逐项结论与偏差披露

| 门禁 | 依据 | 实测 | 结论 |
|---|---|---|---|
| ① CI 全绿 | `pr-template.md:4`、`github.md:13,16-23` | 本仓**无真实 workflow**：`.github/workflows/` 目录不存在；以本地全量回归作证据 → `full-regression.txt:225-230`：`6 failed, 4542 passed, 2 skipped …` / `PYTEST_EXIT=1` | **不满足（红灯）** |
| ② 覆盖率 ≥80% | `pr-template.md:4,26`、`github.md:21` | `pyproject.toml/setup.cfg/.coveragerc/pytest.ini/tox.ini` 均不存在，无 `addopts/fail_under/--cov`，回归命令不带 `--cov` → **未量化、无阈值证据** | **不满足（未量化，如实标注，不虚报）** |
| ③ 至少 1 个 approval | `github.md:11`、`pr-template.md:33-34` | 本次独立审查已执行（满足「有人审」），但**结论为「打回」，不构成 Approve**；且门禁为三项合取，①②已不满足 | **本次不批准** |

**偏差披露建议**（若后续修复后重新提交审批，须在 PR / changelog 逐条落盘、不得静默跳过，见 `github.md:23`）：
1. 明确写「本仓未配置真实 CI workflow，`github.md:16` 属规则预留；CI 全绿以本地 `.venv/bin/python -m pytest -q` 退出码 + 通过计数替代」，并附**修复后重跑**的 `PYTEST_EXIT=0` 与 `N passed, 0 failed` 尾行。
2. 明确写「项目无覆盖率采集 / 阈值配置，覆盖率门禁**未量化、未验证**，不宣称 ≥80%」，不得虚报。
3. 至少 1 个**结论为通过**的独立 approval 落盘后方可合并；不得由实现方自批。
4. 严禁以「改松断言 / 删 test / skip / xfail / 改 `UNDECORATED` 正则 / 重算失败快照迁就实现」的方式凑绿（呼应 `regression-guard` 高频清单第 12 条：测试断言不得恒真、不得可静默失效）。

## 四、全量回归终局与 6 个失败定性（均为合并集成缺陷）

`full-regression.txt:64-204` `FAILURES` 段 + `:218-230` 汇总：

| # | 失败用例 | 性质 | 根因（证据） | 是否合并引入 |
|---|---|---|---|---|
| 1 | `test_research_detail_actions_placement_contract.py::test_asset_versions_are_synchronised` (:224) | 契约漂移 | `live_app ['77'] != ['74']`；主干契约 `staged=0` 未随 `index.html:905` v=77 同步 | 是 |
| 2 | `test_research_task_search.py::test_filter_state_and_pure_function_are_wired` (:69) | 功能回退 | `state.taskQuery` 等不在合并后 `research-tasks.js` | 是 |
| 3 | `test_research_task_search.py::test_debounce_and_race_guard_are_present` (:81) | 功能回退 | `taskSearchDebounceTimer` 等不在 | 是 |
| 4 | `test_research_task_search.py::test_direct_lookup_layer_distinguishes_404_network_and_keeps_list` (:94) | 功能回退 | `未找到该任务` 等不在；`:95 RESEARCH.index("async function runTaskIdLookup")` 亦不成立 | 是 |
| 5 | `test_research_task_search.py::test_card_shows_and_copies_full_task_id` (:116) | 功能回退 | `任务 ID：`/`dataset.copyTaskId` 等不在 | 是 |
| 6 | `tests/kb/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered` (:84) | 快照失配 | `backend/app/main.py` 实际 `cfeea4e5…` ≠ 矩阵冻结 `85c9beb1…`；矩阵取主干、main.py 取我方，二者组合不自洽 | 是 |

- 交叉验证：`.venv/bin/python` 只读静态复算 `live_app=['77']`、`live_css=['75']`；三分支 `research-tasks.js` 符号计数（旧分支 8/2/2，主干与合并后 0/0/0）；三方 `main.py` sha256（旧分支矩阵/文件同为 `cfeea4e5…`，主干同为 `85c9beb1…`，合并后交叉）→ 静态推导与 `FAILURES` 输出逐项吻合。
- 与历史基线区分：`docs/sdd/plans/047/runs/task-13/full-regression.txt` 尾部为 `1 failed, 4306 passed`（`test_frontend_map_feasibility.py` + Langfuse:3000 连接拒绝，属环境性），与本次 6 个失败**不同集合**；本次失败全部可由合并决策直接解释，非历史遗留。

## 五、`git diff --cached --check` 告警

`35` 条告警，去重后均为 `docs/sdd/plans/045/runs/**` 历史 SSE 原始日志 / `docs/sdd/plans/047/task-*.md` / `runs/task-13/*.txt` 的空白与行尾 + 2 个测试文件空白行；`grep -E '\.(js|py|css|html):'` 的命中均为以 `+` 开头的 diff 内容行（非代码文件告警）。主会话「代码文件 0、为保持证据逐字可复核未改写」的说明成立，本审查**不改动这些证据**。

## 六、P0 / P1 阻塞项与可执行修复

> 全部为**阻断合并**项：修复后须重跑全量回归达 `PYTEST_EXIT=0` / `0 failed` 并留盘，再重新提交本审批。

- **P0-1（功能回退 + 4 个失败）**：`frontend/research-tasks.js` 冲突解决采用「取主干版本」，丢弃了旧分支的研究任务搜索 / ID 直查 / 复制任务 ID 实现（`research-task-search` 8→0、`runTaskIdLookup` 2→0、`bindTaskSearch` 2→0、`dataset.copyTaskId` 等全失），但 `frontend/index.html:249-255` 定制 union 保留了搜索栏 DOM → **孤儿 DOM、功能残缺**，并使旧分支新增契约 `test_research_task_search.py` 4 个用例失败。
  - **可执行修复**：将 `research-tasks.js` 改为**双方内容 union**（保留主干「操作按钮移入详情卡片右上角 / 稳定主 tab 布局 / keyed diff 复用节点」重构 **且** 恢复旧分支搜索/直查/复制实现），或由 dev 判定以旧分支版本为基线再回填主干 UX 重构；随后 `node --check frontend/research-tasks.js`，并**同时**验证主干新增契约（`test_research_detail_actions_placement_contract.py`、`test_research_tab_width_stability_contract.py`、`test_frontend_button_affordance_contract.py`）与 `test_research_task_search.py` 全部通过。**禁止**删除 `test_research_task_search.py` 或改松其断言来凑绿——这些测试锁的是真实功能边界。
- **P0-2（契约漂移 + 1 个失败）**：`test_research_detail_actions_placement_contract.py:224` `assert live_app == ["74"]` 与已同步策略不一致（主会话已同步 `test_memory_return_global_contract.py` 的同类断言，却漏了本文件）。
  - **可执行修复**：**只同步期望值** `["74"]→["77"]`（可加一行注释说明 v=74 保留为纯属性兼容 marker），与 `test_memory_return_global_contract.py:209` 口径一致；`:219` 的 `in INDEX` 断言与 `test_research_tab_width_stability_contract.py:126` 无需改动（marker 已保留）。不删断言、不放宽正则。修复前建议 `grep -rnE '(live_app|live_css)\s*==\s*\[' tests/` 全仓再扫一遍，避免第二处漏网。
- **P1-1（快照失配 + 1 个失败）**：冲突②「取主干 018 矩阵」与 `backend/app/main.py`（我方版本，含评测路由注册）组合不自洽，导致 `test_inventory_hashes_are_stable_and_write_entrypoints_are_registered:84` 失败。
  - **可执行修复**：二者必须同源——由于 `main.py` 的评测路由注册是我方交付内容需保留，应把 018 矩阵的 `backend/app/main.py` 冻结 sha256 同步为我方 `cfeea4e5…`（即采用旧分支矩阵版本 `cfeea4e5…` 或按合并后 main.py 重算该条），并按 018 既有约定处理 `inventory_git_revision` 等历史字段；**不得**回退 `main.py`（会丢评测端点），**不得**改测试跳过哈希校验。修复后 `python -m pytest tests/kb/test_kb_upload_closure_matrix.py -q` 应通过。

## 七、合并裁决结论

> ## 结论：**打回（Request Changes）** —— 不予批准合并
>
> - 硬依据：`docs/sdd/pr-template.md:4` 与 `docs/github.md:13`「必须同时满足 ① CI 全绿 ② 覆盖率 ≥80% ③ 至少 1 个 approval，任一不满足则阻断，**不得绕过**」。本地全量回归 `PYTEST_EXIT=1` / `6 failed`（`full-regression.txt:225-230`），门禁①明确不满足；门禁②未量化；本次独立审查结论为打回，不构成 Approve。三项合取不成立。
> - 6 个失败全部为本次合并引入的集成缺陷（P0-1 / P0-2 / P1-1），非历史遗留、非环境抖动；其中 P0-1 涉及**真实功能回退**（研究任务搜索实现丢失、孤儿 DOM）。
> - 按 `docs/github.md:23`「门禁失败必须阻断并落盘原因」，本报告即为落盘原因。
> - **放行前置条件**：完成第六节三组修复 → 重跑 `.venv/bin/python -m pytest -q` 达 `0 failed` 并落盘（含退出码与通过计数）→ 补齐第五节门禁偏差三项披露 → 重新提交独立 approval（结论为通过）。在此之前**不得** commit / push / 合 main。
> - 说明：要点 1③④⑤、要点 2（冲突标记/app.js 评测函数）、要点 3（已同步断言 + btn-outline 真加）、要点 4（反伪造/不降级红线）均核实通过；本裁决**仅因门禁①红灯与 P0/P1 集成缺陷**打回，不否定其余冲突解决与评测红线的正确性。

## 八、纪律声明

- 本角色**仅产出本报告** `docs/sdd/plans/047/runs/merge-remote/merge-code-review.md` 与系统强制进展日志；**未改任何代码 / 测试 / 配置 / spec / 台账 / 评审历史 / E2E 证据**；未改写 `045-acceptance-review.md`、018 矩阵、历史 SSE 日志、`full-regression.txt`。
- **未**执行真实 API 打分、**未**重启服务、**未**重复跑全量回归（仅只读 Read 已落盘回归结果，另以只读 `.venv/bin/python -c` 做静态字符串/哈希复算，非运行 pytest 用例）、**未** `git commit` / `push` / 合 main / `reset` / `stash` / `clean`。
- 全量回归结论为**终局实测**（`PYTEST_EXIT=1`），无预判通过、无虚报全绿；覆盖率门禁如实标注「未量化」，未虚报 ≥80%。
- 报告与日志创建/追加后均 `Read` 读回校验。

## 九、进展日志

`.codebuddy/agent-logs/spec-047/merge-remote/architect/20261112-032356.md`
