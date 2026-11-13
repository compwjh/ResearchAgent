# Spec-048 合并裁决（Gate 5 · 独立架构师签字）

| 项 | 值 |
|---|---|
| 评审者 | `architect` |
| 角色 | 架构师（合并裁决） |
| 模型 | `hy4`（读自 `.codebuddy/agents/architect.md:6` 的 `model` 字段） |
| 分派方式 | `Task(architect)` |
| 日期 | 2026-11-13 |
| Spec | `048-literature-map-create-tab-and-refresh-icon.md` |
| Spec 状态（裁决时点） | `实施中`（待 Gate 5 双签后由主会话转 `已完成`） |
| 裁决结论 | **批准收口** |

> 本文件为 `Task(architect)` 独立只读评审的唯一产出。禁止改 spec、业务代码、测试、台账、历史评审文档；不执行 push / 建 PR / 合并 / force push（由主会话按用户授权执行）。结论基于真实文件事实（Read / Grep / Bash 只读命令），附 `文件:行` 依据，不使用「应该没问题」式表述。裁决权仅体现在本结论文档。

## ① 需求 / 技术评审结论复核

**结论：两份 Gate 2 评审仍为「通过（附意见）」，未被后续实施、缺陷修复、二次升版推翻；强制约束 C1–C10 逐条被满足 10/10。**

| 评审 | 落盘结论 | P0 / P1 | 复核 |
|---|---|---|---|
| 需求评审 `048-requirement-review.md:13` | **通过（附意见）** | 0 / 0（P2=5 已沉淀为 C1–C10，`048-requirement-review.md:100`） | 目标清晰、边界 1–10 可测、明确不做 9 条如实计数（`:58`）、产品步骤可操作；状态机与 Gate 1/2 准入一致。仍成立。 |
| 技术评审 `048-tech-review.md:13` | **通过（附意见）** | 0 / 0（`:115-117`） | 六维度（数据模型无变化 / tab 复用口径 / aria-label / `?v=N` / 样式作用域 / 分派）基于代码事实核对通过；无后端写入与外发 URL，并发 / 事务 / 外键 / SSRF 面不触发（`:34,:101`，为事实判定而非豁免）。仍成立。 |

C1–C10 逐条复核（依据 `048-frontend-review.md` §4 `:79-92` 首轮 10/10、§「二次升版复核」 `:162-177` 复核 10/10，以及 `frontend-regression.md` §四 `:85-98` / §七 `:207-222` 单端独立核对 10/10）：

| 约束 | 是否仍满足 | 事实依据 |
|---|---|---|
| **C1** tab DOM 仅 `renderShell()` 内 `createElement` 动态生成、位置 header 后 / grid 前、不动深度研究 tablist | 满足 | `literature-maps.js:958,997-1035,1369`；`index.html` 仅版本/marker，无静态 tab（`048-frontend-review.md:47,:81`） |
| **C2** 闭包内 `activateMapTab()` 只改属性不重建、键盘同步 tabIndex、不跨文件直调 / 不改 `research-tasks.js` | 满足 | `literature-maps.js:1558-1577,1603-1616`；新增测试 `test_literature_map_tabs_and_refresh_icon.py:108-122` 逐字守函数体（`:48,:82`） |
| **C3** `createPanel` 迁入 create tabpanel、id/refs/h3 不变、取消/成功/离开回 maps tab、`:270/:284` 隐藏断言成立 | 满足 | `literature-maps.js:1103-1104,1180,1379,1619,1758,3306,8197`（`:49,:83`） |
| **C4** 保留 refresh id/title、新增 `aria-label="刷新状态"`、移除可见文字、事件链走 `bindEvents`、可重复点击 | 满足 | `literature-maps.js:1191-1198,1385,1581-1587`（`clearTimeout`+重设，`048-frontend-review.md:50,:84`） |
| **C5** CSS `<span>` + `:before/:after`、无 innerHTML/SVG/图标字体、`is-spinning` 可观察、reduced-motion/:disabled 降级 | 满足 | `literature-maps.js:1196,1582`；`literature-maps.css:604-612`；Grep innerHTML/@font-face 0 命中（`:85`） |
| **C6** `HEADER_ACTION_IDS` 移 new、expected/pairs 同步、刷新改判「无文字+aria-label」、三态/尺寸/对比度逐字保留 | 满足 | `readability.py:27,31-35,235-284`；`:148-199` 三态/36px/44px/9.09:1 逐字未动（`:62,:86`）；B1 基线 58→56 精确同步（非放宽） |
| **C7** `get_by_role('tab', name='新建地图')` 同步、`:270/:284` 隐藏断言仍在 | 满足 | `contract.py:140,249,263,277,291,310,320` 共 7 处定位对齐 role 变更（`:87`），冻结断言逐字未动 |
| **C8** js 47→48 / css 34→35→36（二次升版）、marker 末尾纯属性、`MAP_CSS_VERSION` 同步、app.js/styles.css 不动 | 满足 | `index.html:11,903,918-919`；`version-bump.md` §三 4 批 7 文件 8 处；`re.findall(...)[-1]` 实算 js=47/css=34 保持（`048-frontend-review.md:140-143,:173`） |
| **C9** 新增选择器带 `#literature-maps-view` 前缀、不改全局基类、media 补齐 44px/滚动/reduced-motion、不误开抽屉 | 满足 | `literature-maps.css:589-620`；B2 修复 `:604` 带前缀且位于 ≤760px 块内；`openMobilePanel('list', ...)` 仅 `:1722` 由地图列表按钮触发（`:89,:144-146`） |
| **C10** 分派锁定前端四角色、两处改动串行、`node --check` 与三项自查齐全、不越界后端 | 满足 | task-02/03/04 报告记录 02→03 串行；`node --check` EXIT=0；缺陷/升版批次 git diff 仅 `frontend/**` + `tests/frontend/**`（`:90,:175`） |

**需求/技术评审通过条件成立**：C1–C10 在首轮代码评审、二次升版复核、单端复审三轮均判 10/10，无一条被后续改动破坏。

## ② 验收材料复核

| 材料 | 命令 / 文件 | 退出码 / 结论 | 通过数 / 覆盖率 |
|---|---|---|---|
| **最终候选全量回归** | `.venv/bin/python -m pytest -q --cov=backend/app --cov-report=term-missing`（`final-verification.md:11`） | `full-regression-final.exit` = **0** | `full-regression-final.txt` 末行 **`4571 passed, 2 skipped, 5 warnings, 69 subtests passed in 895.87s`**；`TOTAL 51890 8815 83.01%` |
| 前一轮失败（如实保留不翻案） | `full-regression-coverage.txt` / `.exit` | **EXIT=1** | `2 failed, 4569 passed`，B1/B2 已定向修复后重跑全量通过（`final-verification.md:19`） |
| **前端单端全量** | `.venv/bin/python -m pytest -q tests/frontend/`（`frontend-regression.md:141`） | **0**（复审） | **628 passed / 0 failed**；初判 `626 passed / 2 failed / EXIT=1` 逐字保留、不翻案（`:232`） |
| 定向佐证 | B1 / B2 / 新增静态契约 / `node --check` / `check_test_layout.py` / `git diff HEAD --check`（`final-verification.md:23-31`） | 全部 **0** | 1 / 1 / 12 passed；`test layout: ok` |
| **真实浏览器 E2E** | `browser-e2e.json`（Chromium，桌面 1440×900 + 375×812 窄屏） | `"conclusion":"PASS"`，`failed_checks:[]`、`errors:[]` | **18/18 PASS**；`"page":` 实测 **88 个真实 API 响应**（grep 计数 = 88，与 `deploy-verification.json:37` `api_responses_captured=88` 一致），含实体 ID，非 mock、非内部函数 |
| **部署验证** | `deploy-verification.json`（`./deploy/start.sh -d`，8000 端口） | `"conclusion":"PASS"` | `/api/health` `/` `/assets/literature-maps.css?v=36` `/assets/literature-maps.js?v=48` **4×200**（`:13-16`）；live `css?v=36` / `js?v=48` 生效，2 条 marker 仍在末尾注释区 |

**三份评审真实结论（复核）**：需求评审 `048-requirement-review.md`「通过（附意见）」、技术评审 `048-tech-review.md`「通过（附意见）」、前端代码评审 `048-frontend-review.md`「APPROVE」+ 末尾「二次升版复核 **APPROVE 保持**」；单端回归 `frontend-regression.md` 初判 FAIL → 复审 **PASS**。四份均为有正文、有 `文件:行` 依据的真实结论，非占位。spec「评审记录」段 `:171-175` 与之对应（验收评审行除外，见 ③）。

**双签是否并列（如实披露）**：`docs/github.md` / `SDD-GATE-CHECKLIST.md` §Gate 5（`:106-111`）要求「`tester` 子代理出报告 + `architect` 签字」并列。截至本裁决时点，全仓 `find` 无 `048-acceptance-review.md` 文件（spec 评审记录 `:173` 标注「待评审（未执行）」，`final-verification.md:58` 与复盘 `retro/2026-11-12-spec048-literature-map-tabs-closure.md:15` 已预列该报告/分工）。按用户 2026-11-13 当次收口安排，**tester 验收报告另行出具**：本报告仅为 `architect` 一方的独立合并裁决签字（Gate 5 签字 A），**不代签 tester、不自批**；Gate 5 双签以 tester 报告与本报告并列为准。本代理不自行转 spec 状态。此点不影响本报告基于验收证据作出的批准结论，但不虚报「双签已齐」。

## ③ 收口清单 DoD 逐项核对

依据 `SDD-GATE-CHECKLIST.md` §3（`:128-138`）与 `AGENTS.md:129`（收口即 DoD）、`:49-58`（Task 与 Spec 回归边界）。**逐项如实核对，未满足项不掩饰、不虚报**：

| DoD 项 | 核对结果 | 说明（基于文件事实） |
|---|---|---|
| spec「任务计划」/ `plans/048/README.md` / task 文件状态一致、所有必需 task 均 `已完成` | **未完全满足（非阻塞偏差）** | spec 任务计划 `:165-167` 仍为 02 `进行中` / 03 `待执行` / 04 `待执行`；README `:11-13` 为 02/03 `已完成`、04 `进行中`；task-02/03 头部 `已完成`、task-04 头部 `进行中`；README 头部 `:3` spec 状态仍写 `待确认`（spec 正文 `:8` 为 `实施中`）。属收口阶段主会话回填的状态同步，本代理只读不改。 |
| spec 状态 → `已完成`（验收未签字保持 `实施中`） | **按规则保持 `实施中`（正确）** | `SDD-GATE-CHECKLIST.md:111,133`「验收未签字不得转 `已完成`」；当前 tester 报告未落盘，spec 保持 `实施中` 与规则一致。本代理不自行转状态。 |
| `spec-status-changelog.md` 已追加本次状态流转条目 | **部分满足（收口条待回填）** | 台账尾部 2 条 048 条目：`:805`「新建→待确认」、`:807`「待确认→已确认→实施中」；尚无「实施中→已完成」收口条（与当前状态一致，双签后由主会话追加）。 |
| spec「评审记录」三行结论均为真实结论、无「/」无占位 | **部分满足（验收行占位）** | 需求/技术/代码评审/单端回归 4 行为真实结论（`:171,172,174,175`）；验收评审行 `:173` 为「待评审（未执行）」占位，且引用的 `048-acceptance-review.md` 当前不存在。随 tester 报告出具后回填。 |
| spec「变更日志」补齐每行（时间/角色/动作） | **满足（收口行待补）** | `:196-198` 三行均含时间/角色/动作；收口行由主会话随双签追加（纯文档代行三处留痕）。 |
| spec 中引用的每个文档路径真实存在 | **6/7 满足（1 处断链）** | 实核 7 条引用：`048-requirement-review.md`、`048-tech-review.md`、`048-frontend-review.md`、`runs/task-04/frontend-regression.md`、`SDD-GATE-CHECKLIST.md`、`retro/2026-11-12-spec048-literature-map-tabs-closure.md` 6 条 OK；**`048-acceptance-review.md` MISSING**（验收报告待出具）。另 `artifacts/spec-048-literature-map-tabs-manual-e2e.md` 存在。 |
| 复盘已落盘 | **满足** | `docs/sdd/retro/2026-11-12-spec048-literature-map-tabs-closure.md` 已落盘（04:11），含 §1 交付 / §2 证据 / §3 踩坑 7 条 / §4 范围外 / §5 结论。 |

**补充：AGENTS.md 回归边界符合性**：`:53`「全量回归只在 Spec 收口阶段启动、最终候选必须通过」——本轮 `full-regression-final.exit=0` 满足；`:54`「最终验收材料必须记录命令、退出码、通过数量、阻塞项」——`final-verification.md` §1/§7 满足；`:56`「收口前必须跑通当前部署版本真实 API 端到端成功案例并落盘」——`browser-e2e.json` 88 个真实 API 响应 + `deploy-verification.json` 4×200 满足；`:58`「准备度 ≥90% 且无 P0/P1、无 API E2E 失败、无关键产物缺失」——18/18 PASS、阻塞项 0 满足。

**DoD 小结**：§3 七条中，完全满足 3 条（spec 状态按规则保持 `实施中`、变更日志每行齐备、复盘已落盘）；标注「未完全满足 / 部分满足 / 6-7 满足」的 4 条（任务计划状态一致、台账收口条、评审记录验收行、引用路径）待收口回填；连同 `AGENTS.md:129`「验收签字栏已填」共 5 类回填项，均为收口阶段由主会话回填的状态同步与 tester 报告另行出具。**这 5 类回填项不属 P0/P1 技术阻塞，不构成对本次合并裁决的打回**，但如实登记、不以「应该没问题」带过。主会话在执行快进推送前应完成这些回填（本代理不代行）。

## ④ P0 / P1 / P2 清单与阻塞项

| 级别 | 数量 | 来源与说明 |
|---|---|---|
| **P0（阻断）** | **0** | 需求评审 `:98`、技术评审 `:115`、前端评审 `:96` / 复审 `:181`、`final-verification.md:72` 一致；无硬编码凭据 / SQL 拼接 / XSS / 路径穿越 / 认证绕过；无 API E2E 失败、无冲突标记、无断链产物。 |
| **P1（高）** | **0** | 三份评审 + 单端复审一致；B1 为精确基线同步、B2 为真实 `padding` 修复，均非放宽断言 / 非伪造（`:166-167`）。 |
| **P2（观察项，非阻塞）** | **1** | `P2-1`：`is-spinning` 用固定 700ms 定时器移除（`literature-maps.js:1584`），旋转时长与真实请求时长不严格同步，属视觉反馈措辞偏差、非功能/安全缺陷（`048-frontend-review.md:102,:183`）；建议后续在 Promise `finally` 移除。 |
| **合并阻塞项** | **0** | 全量回归 EXIT=0、单端 628 passed、E2E 18/18、部署 4×200、C1–C10 10/10、三份评审真实通过；`final-verification.md:70-72` 阻塞项 0。 |

## ⑤ 门禁偏差如实披露

按 `docs/github.md` §合并门禁（`:13`：CI 全绿 / 覆盖率 ≥80% / ≥1 approval）与 §CI（`:16` 明示「规则说明，非真实 workflow」）、§受保护分支（`:28`）核对。**以下 4 条逐条写明「以本地可验证证据替代、不虚报平台门禁全绿」**：

1. **无真实 GitHub Actions workflow**：实核 `.github/workflows/` 目录不存在（`find` 无文件），`docs/github.md:16` 自述为「规则说明，非真实 workflow」，平台 CI 无法运行、无法给出平台绿灯。**替代**：以本地实跑 `pytest` 全量（`4571 passed` / EXIT=0）、`pytest tests/frontend/`（`628 passed` / EXIT=0）、`node --check`（EXIT=0）、`check_test_layout.py`（`test layout: ok`）、`git diff HEAD --check`（0）、`npm`/定向 12 passed 的可复现落盘输出替代；不虚报「CI 全绿」。
2. **平台 branch protection 未配置**：`docs/github.md:28` 要求 `main` 受保护、禁直接 push / force，但平台侧未落地 branch protection 规则、无强制 status check。**替代**：以本地独立三份评审（需求/技术/前端）、单端复审、本架构师裁决签字、状态台账留痕替代平台强制检查；不虚报「branch protection 通过」。
3. **覆盖率未设 `fail_under`**：`.coveragerc:21` 明确「刻意不设置 fail_under」，全仓扫描无阈值配置；本轮实测 `TOTAL 83.01%`（`full-regression-final.txt` 末行），为**如实量化值、非阈值门禁判定结果**。**替代**：以本地 `--cov` 实测报告 + 逐文件明细落盘替代平台覆盖率门禁；不改阈值凑绿、不虚报「覆盖率门禁达标」。
4. **按用户当次指示省略 PR 流程与强制 approval**：`docs/github.md:11-13` 要求 PR + 至少 1 个 approval + squash merge；用户 2026-11-13 明确指示开发完成后省略 PR 流程、直接快进推送（`spec:11,:76`，台账 `:807`）。**替代**：以本地独立评审结论 + 本裁决签字 + 全量/单端/E2E/部署证据 + 台账状态流转条目替代平台 PR approval 与合并门禁；不虚报「PR approval 已通过 / 平台合并门禁全绿」。

## ⑥ 架构师签字栏

**批准收口**

本人作为 `Task(architect)` 独立只读架构师，基于上述 ①–⑤ 全部文件事实，对 Spec-048（文献地图新建入口 tab 化与刷新状态图标化）作出 Gate 5 合并裁决：验收证据齐备、需求/技术评审通过条件 C1–C10 10/10 满足、P0=0 / P1=0 / 阻塞项 0、门禁偏差逐条如实披露，**验收签字确认：批准收口**。

- 评审者：`architect`（架构师 · 合并裁决）
- 模型：`hy4`（读自 `.codebuddy/agents/architect.md:6`）
- 分派方式：`Task(architect)`
- 签字：`architect (hy4)` · 2026-11-13
- **双签并列声明**：本签字仅为 Gate 5 的 `architect` 一方裁决（签字 A）；**tester 验收报告 `048-acceptance-review.md` 另行出具**，与本报告并列构成双签，**非自批**。本代理不代签 tester、不自行把 spec 状态从 `实施中` 转为 `已完成`（由主会话在双签齐备并完成 ③ 所列状态/台账回填后执行）。
- 本报告为只读裁决文档，未改 spec / 业务代码 / 测试 / 台账 / 历史评审文档；未执行任何 git / push / 合并 / force push 操作。

## ⑦ 交付边界

按用户 2026-11-13 当次指示（覆盖 spec 初稿「闭环后仅本地 commit / 不主动 push」口径，`spec:11,:76`、台账 `:807`、复盘 `:4`）：

- 收口后**以 fast-forward 直接推送远端 `main`**；
- **不 force push、不新建 PR**（省略 PR 流程与强制 approval，见 ⑤.4）；
- **Spec-047 追加范围五成果（`c6abb7a6`）随同一交付一并快进推送**，不另开 PR、不并入本 spec 的需求范围；
- 推送动作由主会话按用户授权执行，本代理不执行、不代行、不扩大交付范围。
