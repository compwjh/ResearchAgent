# Spec 047 任务计划索引（plans/047）

> 关联：[spec-047](../../specs/047-evaluation-p2-and-observability-fixes.md)（状态 **`已完成`**，D1–D6 已按推荐拍板）
> 评审：[需求评审](../../reviews/047-requirement-review.md)（通过）｜[技术评审](../../reviews/047-tech-review.md)（通过·附强制约束）｜[验收评审](../../reviews/047-acceptance-review.md)（通过·`architect` 已签字，准备度 9/10）
> 适用模板：`docs/sdd/00-sdd-spec-template.md`「规范化流程」六步 ｜ 门禁：`docs/sdd/SDD-GATE-CHECKLIST.md`

## 本目录与 spec「任务计划」表的编号映射

- spec「任务计划」表中 **01 = 编写 spec-047**（以 spec 本身为文档，不另建 task 文件）；实施任务为 **02–08**。
- 本目录按 D6 顺序把实施任务重建为 **task-01 – task-07**，一一对应：

| 本目录编号 | 任务 | 对应 spec 表编号 | 对应决策 |
|---|---|---|---|
| task-01 | 修复 B：两处观测口径 | 02 | D3 |
| task-02 | 修复 C：`--force` 幂等 | 03 | D4 |
| task-03 | 修复 D：`.env` 路由修正 | 04 | D5 |
| task-04 | P2① 人工 gold 集 / `human_agree_rate` | 05 | D2① |
| task-05 | P2② 两套分数口径映射 | 06 | D2② |
| task-06 | P2③ 在线实时评测（含 ADR0002 修订） | 07 | D2③ |
| task-07 | 集成验收收口 | 08 | D6 收口 |

> 下游引用「依赖任务 XX」时，XX 一律指**本目录编号**（task-01…task-07）。

## 任务清单（依赖无环：单向链 01→02→03→04→05→06→07）

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 修复 B：两处观测口径（phase:overhead + 7-score 可用性标记） | [task-01-observability-metrics-fix.md](./task-01-observability-metrics-fix.md) | spec 已确认 | **已完成** |
| 02 | 修复 C：`--force` 幂等（widget_id manifest 按 ID 删/复用） | [task-02-dashboard-force-idempotency.md](./task-02-dashboard-force-idempotency.md) | 01 | **已完成** |
| 03 | 修复 D：`.env` 路由修正 + 重启与回滚验证 | [task-03-ollama-route-correction.md](./task-03-ollama-route-correction.md) | 02 | **已完成** |
| 04 | P2① 人工标注 gold 集 + `human_agree_rate` | [task-04-eval-human-gold.md](./task-04-eval-human-gold.md) | 03 | **已完成** |
| 05 | P2② `quality_score` 与 Langfuse score 口径映射 | [task-05-score-mapping.md](./task-05-score-mapping.md) | 04 | **已完成** |
| 06 | P2③ 在线实时评测（含 ADR0002 同步修订） | [task-06-online-evaluation.md](./task-06-online-evaluation.md) | 05 | **已完成** |
| 07 | 集成验收收口（三份评审、部署取证、复盘） | [task-07-integration-acceptance.md](./task-07-integration-acceptance.md) | 06 | **已完成** |

> **状态纪律（2026-11-09 收口回填）**：Gate1+Gate2 评审通过后 spec 已转 `实施中`（状态台账由主会话追加）；task-01..06 均已执行完毕并有各自 `runs/task-XX/implementation.md` 交接报告，task-07 集成验收收口进行中。各 task 顶部状态由主会话统一回填，以本索引与 spec「任务计划」表为准。

## D6 顺序与逐块验收纪律

顺序 **B → C → D → P2① → ② → ③**（对应 task-01→06），每块**红绿测试 + 当前部署版本真实 API E2E**取证（真实请求 / 响应状态码 / 实体 ID / 最终状态 / 产物路径），证据落 `docs/sdd/plans/047/runs/task-XX/`。`retro045:42`：重启后重新取证才作数。task-07 汇总收口。

## 全局强制约束（来自两份评审，逐条下沉到各 task「明确不做」）

1. **不 push、不合 main**，`origin/main` 仍 `1b26c76c`；不 git commit/push/合 main；不写状态台账。
2. **不跑未授权破坏性 `--force` 真实重跑**（D4 单独授权窗口）；C 的真实重跑降级为隔离项目 / 只读契约验证，不得声称线上已修好。
3. **不破坏 045 已签字契约**：7 numeric score 数量/名/值不变、19.735 证据不变、`derive_metrics` 0 契约不变、diff 口径不变、不迁历史 trace / score。
4. **不建第二套实现**：P2 三项全部复用 `backend/eval_042/` 的 CLI / runner / report / `langfuse_export.post_score`；不新增业务端点 / 映射表 / SSE 事件类型。
5. **隐私与反伪造**：gold 集脱敏（不含 system prompt / 历史对话 / 长期记忆原文，`spec-042:236`）；**不得伪造人工标签**，无真实标注时 `human_agree_rate` 保持 `null`。
6. **ADR0002 同步修订**：P2③ 与 `ADR0002:45-48,62,78-81` 及 `spec-042:76` Q2=A 两处冲突，修订段落落盘前开关保持默认关闭、不进收口。
7. 本轮评审阶段**不改任何业务代码 / 测试 / 配置 / `.env`**；不 mock 冒充真实 E2E、不宣称准备度分数。

## 三维交叉核对入口

- 四个可行性风险逐条结论、P2 三项口径定稿、ADR0002 段落级修订建议 → [技术评审](../../reviews/047-tech-review.md) §3 / §4 / §5。
- 授权边界、六要素、四块验收可测性 → [需求评审](../../reviews/047-requirement-review.md)。
- 各 task 的「实现依据」小节均指向上述评审对应小节，下游只认落盘文档。

## 收口后补充验证（2026-11-09，用户追加授权）

- 上方约束第 2 条「不跑未授权破坏性 `--force` 真实重跑」的**授权条件已满足**（用户原话：「授权你跑」），
  该条作为收口时点陈述保留、不改写；约束第 1 条的「不 git commit」仅约束评审阶段，收口后本地 commit 按 Git 规范执行。
- 新增证据目录 `runs/task-08/`（**非新 task**，不改动上表 task-01..07 编号与状态）：真实连跑两次 `--force`、
  一次性 manifest 迁移、默认模式回归、契约测试与最终状态原始响应；索引 `runs/task-08/force-idempotency-e2e.json`。
- 人工验收详情：`artifacts/spec-047-force-idempotency-manual-e2e.md`（逐步点击、等待条件、失败恢复、产物路径、签字栏）。
- 期间未改业务代码；spec 状态保持 `已完成`；045 `dashboard-contract.json` 的 `DEFECT` 历史证据保持原样。


## 追加范围任务（2026-11-10 用户授权，D7–D12）

> 用户「这个新的spec不要新增号码，归为047的追加功能，你设计好之后就可以开发」。**不新增 spec 编号**；独立 `048-evaluation-effect-visualization.md` 已由主会话删除、`plans/048/` 不存在。
> 本节三项为 spec-047「追加范围（2026-11-10 用户授权）：评测台与多维度打分」的下沉任务；spec 状态 `已完成 → 实施中`（追加范围开发中），收口后回 `已完成`，**原 task-01..07 与六块收口结论保持历史原样、不翻案**。
> 依据：追加范围 [需求评审 §13](../../reviews/047-requirement-review.md)（通过，P0=0）/ [技术评审「追加范围技术评审」](../../reviews/047-tech-review.md)（通过，P0=0）。下游只认落盘文档。
> 分派：task-08 → `backend-dev`，task-09 → `frontend-dev`，task-10 → `tester` + 主会话。

### 追加范围任务清单（依赖单向 08 → 09 → 10；与原 task-01..07 收口链并列、不改写其状态）

| 编号 | 任务 | 任务文档 | 依赖 | 分派角色 | 状态 |
|---|---|---|---|---|---|
| 08 | 评测台后端：指标注册表 / 内置标注集 / 五端点 / 契约测试 | [task-08-evaluation-backend.md](./task-08-evaluation-backend.md) | 原六块已收口（历史，不翻案） | `backend-dev` | **已完成** |
| 09 | 评测台前端：第 9 个「评测」视图 + 静态契约（`?v=N` / XSS） | [task-09-evaluation-frontend.md](./task-09-evaluation-frontend.md) | 08（端点契约） | `frontend-dev` | **已完成** |
| 10 | 评测台真实 E2E / 部署 / 验收（D12 口径） | [task-10-evaluation-e2e.md](./task-10-evaluation-e2e.md) | 08 + 09 | `tester` + 主会话 | **已完成** |

> **追加范围全局约束**（沿用两份追加评审）：① 真实多维度打分，非 mock/占位，RAG 与意图两维度必真实出分；② 不可用指标 `degraded`/`needs_ground_truth`/`unavailable` 必带 `reason`，`reranker` 当前 `available=false` 如实降级不伪造收益；③ 标注集 `source:"builtin-fixture"`/`synthetic:true`/`label_source`，不冒充人工标注或真实业务数据；④ 复用既有实现（`retrieve.hybrid_search`/`intent.detect_skill`/`eval_042` 判官），禁第二套；⑤ 前端升 `?v=N`、保留旧版兼容标记、禁 `innerHTML`；⑥ 端点稳定错误体、只读白名单目录、防路径穿越；⑦ 不新建 spec 编号、不写状态台账（主会话）、不改 ADR0002 正文（实现阶段同批追加）；⑧ 不 push、不合 main，`origin/main` 仍 `1b26c76c`。

## 追加范围二（2026-11-10 用户二次授权）

> 详见 [spec-047 追加范围二](../../specs/047-evaluation-p2-and-observability-fixes.md) 与
> [OpenEvals 指标可行性矩阵](../../notes/047-openevals-metric-feasibility.md)。**不新增 spec 编号**。
>
> - **范围 A `artifacts/` 目录自解释治理：已执行完成**（纯文档代行）。9 个裸 `artifacts/task-NN/`
>   迁入 `artifacts/spec-032/task-NN/`；契约见 `artifacts/README.md`；Spec032/032.1 引用与断链已同步。
> - **范围 B 评测指标体系细化：`已完成`**。用户 2026-11-10「我确认 你开发吧」；需求评审 §14 与技术评审
>   「追加范围二」均通过（P0=0/P1=0）；需求/技术/验收三道门禁与架构师签字齐备，
>   状态 `待确认 → 已确认 → 实施中 → 已完成`。
> - 原 task-01..07 与追加范围 task-08..10 的状态、三份评审签字结论全部保持历史原样，不翻案。

### 追加范围二任务清单（依赖 11 → 12 → 13；跨端拆两次分派）

| 编号 | 任务 | 任务文档 | 分派角色 | 状态 |
|---|---|---|---|---|
| 11 | 后端：22 指标注册表 / 联合判官 / 规则类指标 / 契约测试 | [task-11-evaluation-metric-expansion.md](./task-11-evaluation-metric-expansion.md) | `backend-dev` | **已完成** |
| 12 | 前端：按 `group` 分组渲染 / 对比按组 / `?v=75` 升级 | [task-12-evaluation-grouped-view.md](./task-12-evaluation-grouped-view.md) | `frontend-dev` | **已完成** |
| 13 | 真实 API / 浏览器 E2E、部署验证、验收签字与收口 | [task-13-evaluation-metric-e2e.md](./task-13-evaluation-metric-e2e.md) | `tester` + 主会话 | **已完成** |

> 单端改动只跑单端回归；跨端实现拆两次分派。证据落 `docs/sdd/plans/047/runs/task-13/`，
> 人工验收详情按 `artifacts/README.md` 目录契约命名 `artifacts/spec-047-*.md`。

## 追加范围三（2026-11-11 用户第三次授权）

> 详见 [spec-047 追加范围三](../../specs/047-evaluation-p2-and-observability-fixes.md)（状态 **`已完成`**：API E2E PASS 18/18、浏览器 E2E PASS、全量回归 `4379 passed / PYTEST_EXIT=0`、验收 §15 与合并裁决签字生效、部署验证 200）。
> **不新增 spec 编号 / `plans/048/`**；用户 2026-11-11「确认，你实施吧」→ `待确认 → 已确认 → 实施中`。
> 需求评审 [§15](../../reviews/047-requirement-review.md)（通过，P0=0/P1=0）与技术评审
> [「追加范围三技术评审」](../../reviews/047-tech-review.md)（通过，P0=0/P1=4）均已落盘；
> 4 项 P1 的书面裁决见 **spec §13.1**（Go/No-Go 硬判据统一 900s、超时常量收敛单一真源、
> `call_ollama` 可选 `num_predict` 唯一例外、chat 集唯一数据源与两层 `synthetic` 口径），
> 均属已确认范围内小缺陷、不退回 `待确认`。
> 原 task-01..13 的状态、追加范围一/二收口结论与三份评审签字全部保持历史原样、不翻案。

### 追加范围三任务清单（依赖 14 → 15 → 16；跨端拆两次独立分派）

| 编号 | 任务 | 任务文档 | 分派角色 | 状态 |
|---|---|---|---|---|
| 14 | ≥100 条真实样本 + 生成脚本 + 批量化 + 常量调整 + Go/No-Go 基准 | [task-14-evaluation-samples-and-batching.md](./task-14-evaluation-samples-and-batching.md) | `backend-dev` | **已完成** |
| 15 | 紧凑卡片 + `<details>` 折叠 + `?v=77` / `?v=73` + 静态契约 + 选项区样本数 | [task-15-evaluation-compact-cards.md](./task-15-evaluation-compact-cards.md) | `frontend-dev` | **已完成** |
| 16 | 真实 API / 浏览器 E2E、部署验证、验收签字与收口 | [task-16-evaluation-samples-e2e.md](./task-16-evaluation-samples-e2e.md) | `tester` + 主会话 | **已完成** |

> 单端改动只跑单端回归；`backend-dev` 与 `frontend-dev` 各独立分派，不派通吃 agent。
> 证据落 `docs/sdd/plans/047/runs/task-14/`（Go/No-Go 基准）、`runs/task-15/`（前端交接）与 `runs/task-16/`（E2E），
> 人工验收详情按 `artifacts/README.md` 契约命名 `artifacts/spec-047-*.md`。
> 本节为纯文档改动，由主会话代行，三处留痕见 spec §13.3。

## 追加范围四（2026-11-12 用户提出）：不相关指标灰色弱化

> 详见 [spec-047 追加范围四](../../specs/047-evaluation-p2-and-observability-fixes.md)（状态 **`已完成`**：单端 `614 passed`、最终全量 `4557 passed / PYTEST_EXIT=0`、真实 Chromium E2E 7 步 PASS、部署验证 4×200、验收 §16 与合并裁决双签批准收口）。
> **不新增 spec 编号 / `plans/048/`**；用户「你处理下合并。然后再实现这个task」→ `待确认 → 已确认 → 实施中`。
> 远程合并已完成（PR #4 squash → `origin/main` `cdbb83cc`），设计按合并后 live `styles.css?v=75` / `app.js?v=77` 重基线，
> 升版目标改为 `styles.css?v=75 → ?v=76`。
> 需求评审 [§16](../../reviews/047-requirement-review.md)（通过，P0=0/P1=0）与技术评审
> [「追加范围四技术评审」](../../reviews/047-tech-review.md)（通过，P0=0/P1=2）均已落盘；
> 两项 P1 的书面裁决见 **spec 追加范围四 §13**（V3 徽章 WCAG 达标色值 `#5f626c`；精确 live 断言 6 处清单；
> `v=75` 纯属性 marker 须置于 `index.html` 末尾注释区）。
> 原 task-01..16 状态、追加范围一/二/三收口结论与三份评审签字全部保持历史原样、不翻案。

### 追加范围四任务清单（依赖 17 → 18 → 19；纯前端单端分派）

| 编号 | 任务 | 任务文档 | 分派角色 | 状态 |
|---|---|---|---|---|
| 17 | 灰阶视觉契约 V1–V7 + `styles.css?v=76` + 6 处精确断言 + 新增静态契约用例 | [task-17-evaluation-irrelevant-metric-gray-style.md](./task-17-evaluation-irrelevant-metric-gray-style.md) | `frontend-dev` | **已完成** |
| 18 | 前端代码评审 + 单端回归（版本 / XSS / WCAG / 反伪造复核） | [task-18-evaluation-gray-style-review.md](./task-18-evaluation-gray-style-review.md) | `frontend-reviewer` · `frontend-tester` | **已完成** |
| 19 | 真实浏览器 E2E + 部署验证 + 验收签字 + 台账 / 复盘 / 本地 commit | [task-19-evaluation-gray-style-e2e.md](./task-19-evaluation-gray-style-e2e.md) | `tester` · `architect` · 主会话 | **已完成** |

> 纯前端单端改动：只派 `frontend-dev`，后端 dev / reviewer / tester 一律不分派，单端回归只跑 `tests/frontend/`。
> 证据落 `docs/sdd/plans/047/runs/task-17/`（实现交接）、`runs/task-18/`（评审与回归）、`runs/task-19/`（E2E snapshot / 截图 / `gray-style-e2e.json`）。
> 本节为纯文档改动，由主会话代行，三处留痕见 spec 追加范围四 §13。
> 收口证据：`runs/task-17/implementation.md`、`runs/task-18/frontend-regression.md`、`runs/task-19/gray-style-e2e.json` / `deploy-verification.json` / `full-regression.txt` / `merge-decision.md`；验收签字见 `docs/sdd/reviews/047-acceptance-review.md` §16。本节状态回填由主会话代行（纯文档，三处留痕见 spec 追加范围四 §13）。

## 追加范围五（2026-11-12 用户提出）：遗留项清理

> 详见 [spec-047 追加范围五](../../specs/047-evaluation-p2-and-observability-fixes.md)（状态 **`已完成`**：最终候选全量 `4559 passed / EXIT=0`、覆盖率 `TOTAL 83.02%`、真实 Chromium 复核、部署 5×200 PASS、双签批准收口）。
> **不新增 spec 编号 / `plans/048/`**；用户「遗留你也改一下」+ 连续「请继续」→ `待确认 → 已确认 → 实施中 → 已完成`。
> 基线 `origin/main 42bbc188`（PR #5 squash）；分支 `feature/spec-047-followup-cleanup`。
> 原 task-01..19 状态、追加范围一/二/三/四收口结论与历史评审签字全部保持原样、不翻案、不重开门禁。

### 追加范围五任务清单（依赖 20 → 21 → 22；跨端拆两次独立分派）

| 编号 | 任务 | 任务文档 | 分派角色 | 状态 |
|---|---|---|---|---|
| 20 | A 静态资源缓存版本 + B P2 文案 + D 灰卡文字对比度与 `styles.css?v=77` | [task-20-followup-frontend-cleanup.md](./task-20-followup-frontend-cleanup.md) | `frontend-dev` | **已完成** |
| 21 | C 测试布局合规 + E1 `.coveragerc` 覆盖率采集 | [task-21-followup-test-layout-and-coverage.md](./task-21-followup-test-layout-and-coverage.md) | `backend-dev` · 主会话 | **已完成** |
| 22 | 独立评审 + 单端 / 全量回归 + 浏览器复核 + 部署验证 + 验收签字 + 台账 / 复盘 / 本地 commit | [task-22-followup-acceptance-and-closure.md](./task-22-followup-acceptance-and-closure.md) | `architect` · `tester` · `frontend-reviewer` · 主会话 | **已完成** |

> 收口证据：`runs/task-20/frontend-implementation.md`、`backend-implementation.md`、`full-regression-coverage.txt` / `.exit`、`r1-computed-style.txt`、`deploy-verification.json`、`final-verification.md`、`merge-review.md`；
> 验收签字 [`docs/sdd/reviews/047-acceptance-review.md` §17](../../reviews/047-acceptance-review.md)、代码评审 [`047-followup-frontend-review.md`](../../reviews/047-followup-frontend-review.md)、复盘 [`2026-11-12-spec047-followup-cleanup-closure.md`](../../retro/2026-11-12-spec047-followup-cleanup-closure.md)。
> 本节与 3 份 task 文档为纯文档改动，由主会话代行（三处留痕：各文档头部 / spec 追加范围五 §7 / 状态台账 2026-11-12 收口条）；含 `.py` / `.js` / `.html` / `.css` 的实现一律由 `frontend-dev` / `backend-dev` 分派。
> 闭环后仅本地 commit，**不 push、不合 main、不 force push**，`origin/main` 保持 `42bbc188`。
