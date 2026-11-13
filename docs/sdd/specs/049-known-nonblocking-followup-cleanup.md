# Spec-049 已知非阻塞项定案与刷新旋转反馈修正

> **产出性质**：计划模式纯文档，由主会话（架构师自身）代行落盘；三处留痕「本头部 / 本文『评审记录』段 / `docs/sdd/spec-status-changelog.md` 2026-11-13 条」。
> **文档纪律**：只保留结论、事实依据（文件:行 / 命令）与验证方式。

## 状态

**当前状态：已完成**

> Gate 2 需求评审与技术评审均「通过（附意见）」（P0=0 / P1=0，C1–C10 共 10 条）；Gate 5 `tester` 验收「通过 / READY」签字 R 与 `architect`「批准收口」签字 A 并列、非自批。
> 定案：C 类 7 项保持现状、零改动；交付方式为省略 PR、直接快进推送远端 `main`，不 force push、不新建 PR。

## 一句话目标

把已登记的 9 类非阻塞项（加 1 项只读勘察补充）逐条定案并落盘结论；其中唯一本次实现的偏差「刷新图标旋转由固定 700ms 定时器移除」改为请求 Promise 结束后移除，其余项按「已闭环 / 本次实现 / 保持现状」三类处置，不虚报平台门禁全绿。

## 数据模型

**无变化**。本范围不新增/不修改任何数据库表、字段、枚举、迁移或持久化结构。

| 字段 | 类型 | 约束 |
|---|---|---|
| 不适用 | — | 纯前端交互反馈修正 + 治理结论落盘 |

## 端点 / 接口

**无变化**。不新增、不修改、不删除任何 HTTP 端点；不新增外部 URL、不改请求/响应结构、不改认证与错误码。

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| 不适用（复用既有 `GET /api/literature-maps*` 链路） | 不变 | 不变 | 不变 |

## 只读勘察结论（逐项定案，2026-11-13）

| 编号 | 非阻塞项 | 登记来源 | 勘察事实（文件:行 / 命令） | 定案 |
|---|---|---|---|---|
| NB1 | 单端初判 FAIL、首次全量 EXIT=1，原记录保留 | `048-acceptance-review.md:171`、`final-verification.md:19,67` | 已修复复审 `628 passed / EXIT=0`、最终全量 `4571 passed / EXIT=0 / 83.01%`（`full-regression-final.txt:296-297`）；原 FAIL 记录逐字保留 | **A 已闭环** |
| NB2 | `is-spinning` 由固定 700ms 定时器移除（P2） | `048-acceptance-review.md:172`、`merge-decision.md:81`、`final-verification.md:63` | `frontend/literature-maps.js:1580-1587`；`loadMaps`（`:3224`）与 `selectMap`（`:3470`）均为 `async`，返回 Promise | **B 本次实现** |
| NB3 | Langfuse `:3000` span 导出 transient 告警 | `deploy-verification.json:45`、`048-acceptance-review.md:173` | `LANGFUSE_ENABLED` 默认 `false`（`backend/app/platform/config.py:145-152`）；`deploy/langfuse/` 有启停脚本；`browser-e2e.json` 无告警堆栈落盘 | **C 保持现状** |
| NB4 | 浏览器控制台其它视图 404 | `deploy-verification.json:46`、`048-acceptance-review.md:174` | `browser-e2e.json:571` `"errors": []`；该目录无 404 URL / 堆栈记录 | **C 保持现状** |
| NB5 | 全仓 185 个历史 lint 债务 | `048-acceptance-review.md:175`、`final-verification.md:65` | `.venv/bin/ruff check . --no-cache --output-format concise` → `Found 185 errors`，`97 fixable`；`ruff.toml:35,45` 为既有规则 | **C 保持现状** |
| NB6 | 无真实 CI workflow / 平台 branch protection 未配置 | `048-acceptance-review.md:176`、`merge-decision.md:88-89` | `.github/` 目录不存在；`docs/github.md:16`「规则说明，非真实 workflow」、`:28` 受保护分支条款 | **C 保持现状** |
| NB7 | 覆盖率未设 `fail_under` | `048-acceptance-review.md:177`、`merge-decision.md:90` | `.coveragerc:21`「刻意不设置 fail_under」；本轮实测 `TOTAL 83.01%` | **C 保持现状** |
| NB8 | 窄屏余量 2px / marker `[-1]` 语义 | `048-acceptance-review.md:178`、`final-verification.md:68` | `visibleMap.height 152 ≥ 150`；`re.findall(...)[-1] == "47"/"34"` 共 3 处（`test_frontend_map_groups_exports.py:54-55`、`test_frontend_map_mobile_contract.py:119-120`、`test_literature_map_tabs_and_refresh_icon.py:75-76`）；211 处 `in INDEX` 断言 | **C 保持现状** |
| NB9 | `merge-decision.md` 当时未落盘 / DoD 5 类回填 | `048-acceptance-review.md:179`、`merge-decision.md:63-69` | `merge-decision.md` 已落盘且签字 A；spec-048 `当前状态：已完成`；台账 `实施中 → 已完成` 条已追加；评审记录验收行、引用路径、签字栏均已回填 | **A 已闭环** |
| NB10 | 工作区 10 个未跟踪文件（勘察补充） | `git status --short` 实测 | `plans/048/runs/task-04/api-merge.py`、`api-merge-result.json`、`.env.bak.spec047.20261109043121`、`.codebuddy/backup-untracked-047/`、`.playwright-cli/`、3 个 `.lock`、`artifacts/jd-agent-infra-capability-map.md` | **C 保持现状** |

**分类小计**：A 已闭环 2 项（NB1、NB9）；B 本次实现 1 项（NB2）；C 保持现状 7 项（NB3–NB8、NB10，零改动）。

### C 类定案（2026-11-13）

| 编号 | 结论 |
|---|---|
| NB3、NB4、NB5、NB6、NB7、NB8、NB10 | 保持现状，零改动 |

交付方式：省略 PR、直接快进推送远端 `main`；不 force push、不新建 PR。

## 边界（每条之后会变成一条测试）

1. `bindEvents()` 中 `refreshButton.classList.add('is-spinning')` 之后，**不再存在** 700ms `setTimeout` 移除逻辑；改由 `selectMap(...)` / `loadMaps(...)` 返回 Promise 的 `finally` 移除。
2. 请求成功、`catch` 内 `setStatus(...'error')`、`requestId` 失配提前 `return` 三条路径下 Promise 都 resolve，`is-spinning` 均被移除；**无永久旋转**。
3. 快速连点刷新不累积定时器、不残留 `is-spinning`；重复点击仍逐次触发状态刷新（`selectMap` / `loadMaps` 调用次数与点击次数一致）。
4. `selectMap`（`literature-maps.js:3470`）与 `loadMaps`（`:3224`）保持 `async`；不得改为同步、不得改其返回值语义、状态文案或既有 `catch` 处理。
5. 刷新按钮 `id` / `title` / `aria-label="刷新状态"` / 无可见文字 / `prefers-reduced-motion` 降级 / ≥44px 触摸目标逐字不变（Spec-048 C4/C5/C9 不回退）。
6. 改动 JS 后 `frontend/index.html` live `literature-maps.js?v=48 → v=49`；`tests/frontend/fixtures/literature_map_component.html` 同步；`js_live == ["49"]` 与 fixture 精确断言同步。
7. **不新增任何 `?v=` marker**：`index.html` 末尾纯属性注释仍为 `src="...js?v=47"` / `href="...css?v=34"`，且仍是全文最后一次出现；3 处 `re.findall(...)[-1] == "47"/"34"` 原样通过、211 处 `in INDEX` 断言不受影响。
8. `literature-maps.css` 内容与 `css?v=36` 不变、`MAP_CSS_VERSION = 36` 不变；`app.js?v=77` / `styles.css?v=77` 不变。
9. 不改松 / 删 / skip / xfail 任何断言；`test_literature_map_tabs_and_refresh_icon.py` 12 条与 `test_frontend_button_affordance_contract.py` 基线 `56` 保持。
10. NB1–NB10 逐条有「结论 + 事实依据（文件:行 / 命令）」落盘；**C 类 7 项零改动**：`.github/` 仍不存在、`.coveragerc` 不变、远端设置不变、未跟踪文件不变、ruff 错误数不变、CSS 不变。
11. 本 spec 不得虚报「CI 全绿 / branch protection 通过 / 覆盖率门禁达标」。
12. 收口前跑通当前部署版本的**真实 API E2E**：点击刷新按钮，捕获真实 API 响应、`is-spinning` 在响应结束后移除、状态栏更新；最终全量回归 `EXIT=0` 且通过数不少于 `4571`。

## Gate 2 强制约束（C1–C10；唯一落点 `docs/sdd/reviews/049-tech-review.md:100-113`）

- **C1 定时器移除 / `.finally` 三路径覆盖**：删除 `literature-maps.js:1580-1584` 的 `refreshSpinTimer` / `clearTimeout` / `setTimeout(..., 700)`；在 `:1585-1586` 的 `selectMap(id)` / `loadMaps()` 调用链接 `.finally(() => refreshButton.classList.remove('is-spinning'))`。验证：`sed -n '1579,1587p' ... | grep -c "setTimeout"` = 0、`grep -c "\.finally"` ≥ 1 + 三场景 E2E。
- **C2 保持 `async` 与既有语义**：`loadMaps`（`:3224`）/ `selectMap`（`:3470`）保持 `async`，返回值 / 状态文案 / `catch` / 按钮 `id` / `title` / `aria-label` / 无可见文字 / reduced-motion / ≥44px 逐字不变。验证：`git diff` 仅 `:1579-1587` 段、`node --check` EXIT=0。
- **C3 连点不残留 / 禁止第二套**：连点不累积定时器、不残留 `is-spinning`，调用次数 = 点击次数；不新增第二套定时器 / 计数器 / 请求封装。验证：E2E 连点 3 次残留 0、`git diff` 无新 `setTimeout` / 计数变量。
- **C4 reject 兜底**：`.finally` 链须对 `selectMap` 的 reject 兜底（`:3472` `await waitForPendingViewFlush` 在 try 外），不得产生 unhandled rejection。验证：E2E console 0 unhandled rejection。
- **C5 升版 `v=49` 五处同步 + 常量冻结**：`index.html:903`、fixture `:1135`、`test_literature_map_tabs_and_refresh_icon.py:46`（`js_live == ["49"]`）、`test_frontend_map_groups_exports.py:53`、`test_frontend_map_mobile_contract.py:97` 同步；`css_live == ["36"]`、`MAP_CSS_VERSION = 36`、`?v=77` 不变。验证：`grep -rn "literature-maps.js?v=48" frontend tests/frontend` = 0 命中、`pytest -q tests/frontend/` EXIT=0。
- **C6 marker 冻结 / `[-1]` 语义 / 211 行断言**：`index.html:918-919` 两条纯属性 marker 不新增 / 不移动 / 不删除；6 行 `[-1] == "47"/"34"` 逐字不动；`in INDEX` 按行数 211 核对（字面串 214 不参与判定）。验证：实算 `re.findall(...)[-1]` = `47 34`、`grep -rn "in INDEX" tests/frontend | wc -l` = 211。
- **C7 CSS / 常量 / 三项必查**：`literature-maps.css` 与 `css?v=36` 不变、`MAP_CSS_VERSION = 36` 不变、窄屏 2px 余量不变、不新增 `?v=` marker；`is-spinning` 在 CSS 有选择器、`?v=N` 已升 `v=49`、`innerHTML` 0 命中。
- **C8 断言不放宽 + 基线保持**：不改松 / 删 / skip / xfail 任何断言；tabs 12 条、按钮基线 `56` 保持。验证：`grep -c "^def test_"` = 12、`git diff -- tests/frontend/` 无 assert 删除 / 放宽。
- **C9 C 类零改动 + 台账 + 不虚报**：`.github/` 仍不存在、`.coveragerc` 无生效 `fail_under`、ruff `Found 185 errors` 不变、未跟踪清单不变；NB1–NB10 逐条「结论 + 事实依据」落盘，C 类写「保持现状」不得写「已修复」；不虚报门禁达标。验证：`git diff --stat` 白名单外 0 文件。
- **C10 分派 / 真实 API E2E / 交付**：含 `.js` / `.html` / `.py` 的实现一律 `Task(frontend-dev)`；收口跑真实 API E2E（点击刷新、捕获真实响应含实体 ID、`is-spinning` 响应结束后移除、连点 3 次无残留）、十项准备度 ≥9/10、全量 `EXIT=0` 且通过数 ≥ 4571；交付省略 PR、fast-forward 直接推送远端 `main`，不 force push、不新建 PR。

## 明确不做（划出范围，防 AI 自由发挥）

- **不创建 `.github/workflows/**`、不改 `.coveragerc`、不改远端 branch protection / required checks / PR approval**。
- **不批量 `ruff --fix`**、不改 185 个历史 lint 涉及的任何文件。
- **不启动 / 不改 Langfuse `:3000`、不改 `LANGFUSE_*` 配置与 `deploy/langfuse/**`；不改其它视图 404**。
- **不提交 / 删除 / 清理工作区未跟踪文件**，不触碰 `.env.bak.*` 备份。
- **不改 CSS、不升 `literature-maps.css?v=36`、不改窄屏 2px 余量**；不新增 `?v=` marker、不改 `re.findall(...)[-1]` 断言语义。
- **不改 `backend/**`、数据模型、端点、其它视图、其它 header 作业按钮**。
- **不改 Spec-048 的 `已完成` 状态、不翻案历史 FAIL 记录、不重开 Gate 1/2/5、不改历史评审文档正文**；只在 `plans/049/` 新建本轮文档。
- **不改松 / 删 / skip / xfail 任何断言**，不靠放宽断言凑绿。
- **不 force push、不新建 PR**；闭环后以 fast-forward 直接快进推送远端 `main`。
- **不以内部函数调用或 mock 替代真实 API E2E**；不以「应该没问题」代替落盘证据。

## 产品使用步骤（由产品经理在 spec 确认后填写）

> 本范围**不新增产品功能**，用户可见行为变化仅「刷新图标旋转时长改为与请求同步」。自然语言入口不是本范围改动，标记「不适用」，不做形式化验证。

### 桌面路径（≥1024px）

| 步 | 操作 | 点击后提示 / 结果 | 等待条件 | 下一步 |
|---|---|---|---|---|
| 1 | `./deploy/start.sh -d` 启动，浏览器打开 `http://127.0.0.1:8000/`，硬刷新 `Cmd+Shift+R` | `/api/health` 返回 `{"status":"ok"...}`；源代码首个 live 链接为 `literature-maps.js?v=49` / `literature-maps.css?v=36` | 三栏工作区渲染完成 | 步 2 |
| 2 | 左栏点「文献地图」，确认「地图」tab 默认高亮 | 画布卡片头部工具区有无文字转圈图标按钮 | 地图列表与画布可见 | 步 3 |
| 3 | 悬停图标 → 点击一次 | tooltip「刷新状态」；点击后图标加 `is-spinning` 开始旋转；状态栏 / 列表刷新 | **等旋转停止**（应在对应 API 响应结束后移除，非固定 700ms） | 步 4 |
| 4 | 连续快速点击 3 次 | 每次都触发刷新、旋转不残留、按钮不禁用卡死；请求失败时旋转同样结束 | 所有请求结束、无永久旋转 | 桌面路径完成 |

### ≤760px 窄屏路径

| 步 | 操作 | 点击后提示 / 结果 | 等待条件 | 下一步 |
|---|---|---|---|---|
| 1 | DevTools 设备模式设 ≤760px，hash 路由 `#literature-maps-view` 进视图 | 两个 tab 横向可见可点、默认「地图」 | tab 可点击 | 步 2 |
| 2 | 点画布头部转圈图标按钮 | 触摸目标 ≥44px、图标旋转、无可见文字残留 | 等旋转结束 | 步 3 |
| 3 | 再点一次 | 旋转再次开始并正常结束 | 状态栏更新 | 窄屏路径完成 |

### 决策项核对（验收场景）

- 打开 `plans/049/runs/decision-ledger.md`，确认 NB1–NB10 每条都有结论与事实依据；C 类逐条结论为「保持现状」，不得写成「已修复」。
- 核对 `.github/` 仍不存在、`.coveragerc` 无 `fail_under`、`git status --short` 未跟踪文件清单与确认前一致（除本轮新增的 `docs/sdd/**` / `plans/049/**` 文档）。

### 失败恢复

| 现象 | 恢复动作 |
|---|---|
| 图标永久旋转 | 核对 Promise `finally` 是否覆盖 `catch` 与 `requestId` 失配提前 return 路径；截图 + 记录 API 响应状态，暂停验收并上报，不以硬刷页面凑通过 |
| 仍是固定 700ms 节奏 | 核对源码 live 是否 `v=49`（`v=48` 为旧缓存）；硬刷新后重试；仍不符则记录阻塞 |
| 版本 / marker 断言失败 | 核对是否误新增 `?v=` marker 或未同步 fixture / 精确断言；不得改松断言，回 `task-02` 定向修复 |
| 服务不可达 | `curl http://127.0.0.1:8000/api/health`；`connection refused` 用 `./deploy/start.sh -d`（占用改 `PORT=8300`）重启，仍失败记录阻塞、不宣称通过 |

### 产物查看路径

| 产物 | 路径 |
|---|---|
| 分类决策台账 | `docs/sdd/plans/049/runs/decision-ledger.md` |
| 定向 / 单端 / 全量回归 | `docs/sdd/plans/049/runs/` |
| 真实浏览器 E2E 与截图 | `docs/sdd/plans/049/runs/` |
| 三份评审 / 状态台账 / 复盘 | `docs/sdd/reviews/049-*.md`、`docs/sdd/spec-status-changelog.md`、`docs/sdd/retro/` |
| 对应 spec 小节 | 本文件「边界」「只读勘察结论」 |

## 执行配置（由架构师填写，落盘可查）

> 型号列读自 `.codebuddy/agents/<role>.md` 的 `model` 字段（2026-11-13 复核，10 个角色均为 `hy4`）；架构师行填「自身」，不写死代号。选型依据 `docs/sdd/MODEL_REGISTRY.md`「角色 agent 当前档位（唯一真源）」。
> 五行齐全；本项目**不存在 `pm` / `tech-lead` / `junior-dev`**，跨端改动拆两端分别分派。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 `architect` | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、需求与技术评审、Gate 5 合并裁决、计划模式只读勘察 |
| 产品步骤 `doc-updater` | `hy4`（读自 `.codebuddy/agents/doc-updater.md`） | 按 agent 档位 | `Task(doc-updater)` | 复核人工验收步骤与失败恢复（本 spec 已给初稿） |
| 前端开发 `frontend-dev` | `hy4`（读自 `.codebuddy/agents/frontend-dev.md`） | 按 agent 档位 | `Task(frontend-dev)` | **仅** `frontend/literature-maps.js` 的 `finally` 修正 + `index.html` / fixture / 精确断言同步；三项自查（class↔CSS / `?v=N` 已升 / 无 `innerHTML`） |
| 前端评审与单端回归 `frontend-reviewer` · `frontend-tester` | `hy4`（分别读自两 agent 的 `model`） | 按 agent 档位 | `Task(frontend-reviewer)` / `Task(frontend-tester)` | DOM 契约 / 版本号 / XSS 三项必查；`tests/frontend/` 单端回归与静态契约核对 |
| 跨端验收总控 `tester` | `hy4`（读自 `.codebuddy/agents/tester.md`） | 按 agent 档位 | `Task(tester)` | 真实浏览器 E2E、部署验证汇总、产出 `049-acceptance-review.md` |

> **分派边界**：含 `.js` / `.html` / `.py` 的实现一律先分派 `frontend-dev` 再落地，禁止主会话先写代码后补记分派；纯文档（spec / plans / 台账 / 评审）由主会话代行并按三处留痕记录。
> **范围**：C 类 7 项零改动，本 spec 不分派平台配置实现。

## 任务计划

> 任务 01 = 编写本 spec（不另建 task 文件）。`plans/049/` 已建档，链接真实可跳转；所有 task 状态与 README、task 头部同步。

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-049（本文件） | 本文件 | — | 完成 |
| 02 | 刷新旋转改为 Promise `finally` 移除 + 版本/断言同步 | [`task-02-refresh-spin-promise.md`](../plans/049/task-02-refresh-spin-promise.md) | 01 | 已完成 |
| 03 | NB1–NB10 分类决策台账落盘 | [`task-03-nonblocking-ledger.md`](../plans/049/task-03-nonblocking-ledger.md) | 01 | 已完成 |
| 04 | 定向 / 全量回归、真实 API E2E、评审、部署与复盘 | [`task-04-verification-and-closure.md`](../plans/049/task-04-verification-and-closure.md) | 02, 03 | 已完成 |

## 评审记录

- 需求评审：`docs/sdd/reviews/049-requirement-review.md` — **通过（附意见）**（`Task(architect)` 独立只读，P0=0 / P1=0 / P2=4）
- 技术评审：`docs/sdd/reviews/049-tech-review.md` — **通过（附意见）**（`Task(architect)` 独立只读，P0=0 / P1=0 / P2=5，强制约束 C1–C10 共 10 条已回填本 spec）
- 验收评审：`docs/sdd/reviews/049-acceptance-review.md` — **通过 / READY**（`Task(tester)` 签字 R，边界 12/12、C1–C10 10/10、准备度 10/10）；`docs/sdd/plans/049/runs/task-04/merge-decision.md` — **批准收口**（`Task(architect)` 签字 A，P0=0 / P1=0 / P2=0，双签并列非自批）

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-11-13 | 架构师（自身，主会话代行纯文档） | 计划模式只读勘察：`048-acceptance-review.md` §6 九项、`final-verification.md` §6、`merge-decision.md` §③⑤、`deploy-verification.json:44-50`、`browser-e2e.json:571`、`docs/github.md:11-29`、`.coveragerc:21`、`ruff.toml:35,45`、`backend/app/platform/config.py:145-152`、`frontend/literature-maps.js:1579-1587,3224,3470`、`tests/frontend/` 版本与 `[-1]` 断言、`git status --short`、`.github/` 缺失；按 `00-sdd-spec-template.md` 编写本 spec 并建档 `plans/049/`。置 `待确认`。 |
| 2026-11-13 | 用户 + 主会话 | 用户确认并定案：C 类 7 项保持现状、零改动；交付方式为省略 PR、直接快进推送远端 `main`，不 force push、不新建 PR。状态 `待确认 → 已确认`；spec / 台账 / plans 同步定案结论。 |
| 2026-11-13 | `architect`（Gate 2） | `Task(architect)` 独立只读评审产出 `049-requirement-review.md`「通过（附意见）」与 `049-tech-review.md`「通过（附意见）」，P0=0 / P1=0，C1–C10 共 10 条沉淀为本 spec「Gate 2 强制约束」段；评审记录三行按真实结论回填。状态 `已确认 → 实施中`，任务 02 / 03 同步 `进行中`。 |
| 2026-11-13 | `frontend-dev` / `frontend-reviewer` / `frontend-tester` | 任务 02：`literature-maps.js:1579-1588` 删 700ms 定时器、两分支链 `.finally` + `.catch` 兜底；`v=48 → v=49` 五处同步；tabs 既有函数内新增静态契约断言（12 条保持）。`049-frontend-review.md` `APPROVE`（C1–C10 10/10，P0/P1/P2 全 0）；`frontend-regression.md` 单端 `628 passed / EXIT=0`。任务 03：`runs/decision-ledger.md` 落盘 NB1–NB10 结论与确认前后状态对照。 |
| 2026-11-13 | `tester` / `architect`（Gate 5）+ 主会话 | 全量 `4571 passed / 2 skipped / 83.00% / EXIT=0`；真实 Chromium E2E `31/31 PASS`（首跑 `28/29 FAIL` 证据保留，判定口径修正后新增 2 条更严断言）；部署 4×200；`artifacts/spec-049-api-sample.md` 真实 API 成功案例落盘；本轮新增 E2E 脚本 B007 修复使 ruff `186 → 185` 回到基线。`049-acceptance-review.md`「通过 / READY」签字 R、`merge-decision.md`「批准收口」签字 A，双签并列非自批。任务 02/03/04 与 README / task 头部同步 `已完成`；复盘与最终验证汇总落盘；状态 `实施中 → 已完成`。 |

---
**六条自检**：①每条边界均可写成静态契约或浏览器断言；②spec 只描述需求与定案、task 承载实施细节；③`plans/049/` 四个链接真实存在、依赖 01→02/03→04 无环；④「明确不做」把范围划死；⑤执行配置五行齐全且型号读自 agent 真源；⑥产品使用步骤可映射到边界 1–3、5、12。
**收口自检**：见 `docs/sdd/SDD-GATE-CHECKLIST.md` §3（状态已转、changelog 已记、三份评审结论为真实结论、引用路径真实存在、复盘已落盘）。
