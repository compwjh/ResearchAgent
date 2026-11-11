## 分支与关联 Spec

- 源分支：`feature/spec-047-merge-remote`（基于 `origin/main` `49486e7f`）
- 目标：`main`，**squash merge**
- 关联 Spec：`spec-047` — [docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md](../../specs/047-evaluation-p2-and-observability-fixes.md)
- Spec 状态：主体追加范围三 `已完成`（本地 `2e073374` 已验收）；新增 UI 子范围另案处理，不在本 PR 范围内
- `Refs: spec-047`；本地单条提交 `d75aae7f`

## 变更摘要

远程 `main` 在 `1b26c76c` 之后前进 5 个 UX/KB 提交，本 PR 把已验收的 spec-047 评测 P2 与观测修复成果以 squash 形式集成，并保留主干 UX 重构：

- 评测后端（`backend/app/evaluation/**`、`routes_evaluation.py`）、三份 gold 集、反伪造 / 不降级红线、22 key / 5 group 分组视图原样带入。
- 5 处合并冲突全部解决，详见 `docs/sdd/plans/047/runs/merge-remote/conflict-resolution.md`：
  - `frontend/research-tasks.js` 用共同祖先做三方 union，保住主干 keyed-diff 复用渲染 / 操作按钮 / tab 重构，同时恢复研究任务搜索 / ID 直查 / 复制任务 ID。
  - 018 `upload-closure-matrix.json` 与合并后的 `routes_kb.py` / `main.py` 同源（未回退后端、未改哈希测试）。
  - `styles.css`、`045-acceptance-review.md` 双方内容 union；`index.html` 合并 live 版本并保留历史兼容 marker，3 个新增按钮补齐 `btn-outline`。
- 仅同步 4 类前端契约期望值（`styles.css?v=75` / `app.js?v=77` / 按钮冻结计数 28 / `live_app == ["77"]`），未删断言、未改正则、未 skip/xfail。

## 自测结果

| 项 | 结果 |
|---|---|
| `lint` | `node --check frontend/research-tasks.js` exit 0；`git grep --cached` 冲突标记 0 命中 |
| `test` | 全量 `.venv/bin/python -m pytest -q` → **`4548 passed, 2 skipped, 69 subtests passed, PYTEST_EXIT=0`**（`docs/sdd/plans/047/runs/merge-remote/full-regression-rerun.txt`） |
| 定向 | `frontend-dev-selfcheck.md`：3 个 Node harness + 5 文件 pytest `59 passed`，5/5 exit 0；`test_kb_upload_closure_matrix.py` `2 passed` |
| 覆盖率 | **未量化、未验证，不虚报 ≥80%**（见下方门禁偏差披露） |
| `build` | 本仓无构建步骤；静态资源契约由上述前端测试覆盖 |

## 评审引用（合并门禁前置）

- 需求评审：`docs/sdd/reviews/047-requirement-review.md`
- 技术评审：`docs/sdd/reviews/047-tech-review.md`
- 验收评审：`docs/sdd/reviews/047-acceptance-review.md`
- 独立 Code Review 首轮：`docs/sdd/plans/047/runs/merge-remote/merge-code-review.md` — 结论**打回**（6 个集成失败）
- 修复后复审：`docs/sdd/plans/047/runs/merge-remote/merge-code-review-approval.md` — 结论**通过（Approve）—— 批准合并**，P0-1 / P0-2 / P1-1 逐条核实已真修复，无凑绿行为

## 开发主管 Approval

- [x] 已审查代码与 spec 一致性，批准合并（独立 `architect` 只读复审，非实现方自批；报告见上）

## 合并门禁偏差披露（按 `docs/github.md:23` 落盘，不静默跳过）

1. **CI 全绿**：本仓**无真实 CI workflow**（`.github/workflows/` 不存在，`docs/github.md:16` 属规则预留）。以本地全量回归替代：`PYTEST_EXIT=0` / `4548 passed` / `0 failed`。
2. **覆盖率 ≥80%**：项目无 `pyproject.toml` / `.coveragerc` / `pytest.ini` 的 `--cov` / `fail_under` 配置，本轮未采集，**未量化、未验证，不宣称达标**。开发主管依据「规则预留 + 不可执行 + 已落盘披露」裁决为非阻断，并建议后续补 `pytest-cov` + `fail_under`。
3. **至少 1 个 approval**：已由独立 `architect` 出具结论为**通过**的复审报告，满足「有人审 + 审查通过」。

## 残留风险（复审裁决为非阻断）

- `research-tasks.js` 净增 223 行，但 live 引用仍为主干 `?v=25`（被 3 个契约冻结）：已有浏览器缓存可能命中旧脚本，部署层需强制刷新，或另起任务统一升版并同步契约。本 PR 不擅自扩大范围。
- Langfuse `127.0.0.1:3000` 连接拒绝为导出 span 的预期告警，非用例失败。
- `git diff --cached --check` 的历史空白告警来自 `045/runs/**` 原始 SSE 日志与历史报告，保持证据逐字不改写；代码文件 0 告警。

## Commit 说明

单条 `feat(spec-047): 集成评测 P2 与观测修复成果到主干`（`d75aae7f`），合并时 squash 为一条进入 `main`。
