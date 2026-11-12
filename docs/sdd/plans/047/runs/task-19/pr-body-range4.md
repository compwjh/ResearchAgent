## 分支与关联 Spec

- 源分支：`feature/spec-047-unrelated-metric-greyout`（基于 `origin/main` `cdbb83cc`）
- 目标：`main`，**squash merge**
- 关联 Spec：`spec-047` — [docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md](../../specs/047-evaluation-p2-and-observability-fixes.md) 文末「追加范围四：不相关指标灰色弱化」
- Spec 状态：**`已完成`**（验收 §16 + 合并裁决双签批准收口）；`Refs: spec-047`
- 本地提交 `6406609a`，合并时 squash 成单条进入 `main`

> 前一次远程合并见 PR #4（`cdbb83cc`）；本 PR 只带追加范围四成果，不重开主体门禁。

## 变更摘要

用户「如果是不相关的指标就用灰色表示」：`needs_ground_truth` 卡片原用紫色强调，与真实出分卡同样醒目；改为纯 CSS 中性灰。

- `frontend/styles.css:4406-4410`：5 条带 `[data-status="needs_ground_truth"]` 限定的规则 —— 左边框 `#c9cbd3`、背景 `#f6f6f8`、徽章 `#e9eaee` / `#5f626c`、标题 / `<summary>` `var(--muted-strong)`、数值 `var(--muted)`。
- `frontend/index.html`：live `styles.css?v=75 → ?v=76`、`app.js?v=77` 不动；`:912` 新增 `v=75` **纯属性片段**兼容 marker，置于末尾注释区（不污染 `active_version` 正则）。
- 6 处精确 live 断言同步为 `v=76` / `["76"]`（只改期望值）；新增 `tests/frontend/test_evaluation_irrelevant_metric_gray_contract.py` 锁 V1–V7、WCAG、三状态基础色值、marker 与 DOM 契约。
- **`frontend/app.js` 与 `backend/**` 逐字零改动**：灰卡仍显示 `—` / `detail.reason` / `样本数：0` / 可展开明细，不隐藏、不降级、不伪造 0 分；`computed` 绿 / `degraded` 橙 / `unavailable` 红逐字不变。
- 技术评审两项 P1 由 spec 追加范围四 §13 书面裁决闭环：V3 徽章色值改 WCAG 达标 `#5f626c`（5.0630:1，原 `#6b6e78` 仅 4.2330:1）；精确断言清单由 4 处补齐为 6 处。

## 自测结果

| 项 | 结果 |
|---|---|
| `lint` | `node --check frontend/app.js` EXIT=0；`git diff --check` 0；无残留冲突标记 |
| `test`（单端） | `.venv/bin/python -m pytest -q tests/frontend/` → **`614 passed / 0 failed / EXIT=0`**（`runs/task-18/frontend-regression.md`） |
| `test`（最终全量） | `.venv/bin/python -m pytest -q` → **`4557 passed, 2 skipped, 69 subtests passed / PYTEST_EXIT=0`**（`runs/task-19/full-regression.txt`） |
| `build` | 本仓无构建步骤；静态资源契约由前端测试覆盖 |
| 覆盖率 | **未量化、未验证，不虚报 ≥80%**（见门禁偏差披露） |
| 真实浏览器 E2E | Chromium 7 步 PASS：22 卡（10 灰 + 12 computed）、灰卡 V1–V6 `getComputedStyle`、computed 绿 / degraded 橙未灰化、灰卡信息可见、`<details>` 可展开、切 `rag-retrieval` 后 `recall@k` 恢复 computed 绿；证据 `runs/task-19/gray-style-e2e.json` + 截图 / snapshot 4 项 |
| 部署验证 | `runs/task-19/deploy-verification.json`：`/api/health`、首页、`styles.css?v=76`、`/api/evaluation/options` **4×200** |
| WCAG | V3 `5.0630:1`、V4 `6.0947:1`，均 ≥4.5:1；作废 `#6b6e78` 在 `styles.css` 0 命中 |

## 评审引用（合并门禁前置）

- 需求评审：`docs/sdd/reviews/047-requirement-review.md` §16 — **通过**（P0=0 / P1=0）
- 技术评审：`docs/sdd/reviews/047-tech-review.md`「追加范围四」 — **通过，附强制约束**（P0=0 / P1=2，裁决见 spec §13）
- 验收评审：`docs/sdd/reviews/047-acceptance-review.md` §16 — **通过**（P0=0 / P1=0，十项人工验收准备度 **10/10**，`tester` 验收签字 R 已填）
- 代码评审：`docs/sdd/reviews/047-frontend-gray-style-review.md` — **APPROVE**（P0=0 / P1=0 / P2=1）
- 收口裁决：`docs/sdd/plans/047/runs/task-19/merge-decision.md` — **批准收口**（`architect` 签字 A）
- 本次合并独立审批：`docs/sdd/plans/047/runs/task-19/merge-to-main-approval.md` — **通过（Approve）—— 批准合并**（P0=0 / P1=0）

## 开发主管 Approval

- [x] 已审查代码与 spec 一致性，批准合并（独立 `architect` 只读审查，实现方未自批；报告见上）

## 合并门禁偏差披露（按 `docs/github.md:23` 落盘，不静默跳过）

1. **CI 全绿**：本仓**无真实 CI workflow**（`.github/workflows/` 不存在，`docs/github.md:5,16` 定性为规则预留）。以本地等价门禁替代：最终全量 `PYTEST_EXIT=0` / `4557 passed`、单端 `614 passed`、部署 4×200、Chromium E2E PASS；**不虚报「CI 全绿」**。
2. **覆盖率 ≥80%**：无 `--cov` / `fail_under` 实配、本轮未采集，**未量化、未验证、不宣称达标**。开发主管裁决不构成放行阻断，依据：门禁生效前提不存在、PR #4 同等先例、本次不新增被测源码行（`app.js`/后端零改动）、已有更强等价验证、`github.md:23` 显式落盘豁免；豁免为一次性、有条件，接入 CI 后须补 `pytest-cov` + `fail_under`。
3. **至少 1 个 approval**：由本轮独立 `architect` 出具结论为**通过**的落盘报告满足；平台级 branch protection 未配置，approval 以报告为准（如实披露）。

## 残留风险（复审裁决为非阻断，另案处理）

- 合并后 `research-tasks.js?v=25` 未随净增 223 行升版：已有浏览器缓存可能命中旧脚本，建议另起任务统一升版并同步契约。
- V5/V7 沿用 `--muted` 在灰底 3.0365:1（既有基线退化，spec §13 R1 裁决不扩范围、未用 `opacity`/`filter` 补救）。
- P2：两处 f-string 失败提示仍写「为 75」；`scripts/check_test_layout.py` EXIT=1 的 5 项为既有历史编号测试，非本 PR 引入。
- Langfuse `:3000` 未启动（导出 span 告警）、浏览器控制台 4 个 404 来自其它视图历史会话资源。
