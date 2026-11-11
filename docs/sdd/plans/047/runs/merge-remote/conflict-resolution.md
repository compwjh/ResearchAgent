# spec-047 远程合并 — 冲突解决编排记录

> 分支 `feature/spec-047-merge-remote`，基于 `origin/main` `49486e7f`；把旧分支
> `feature/spec-047-evaluation-p2-and-observability-fixes`（本地 commit `2e073374`）的成果用
> `git merge --squash` 集成为单条待提交变更。本文记录合并编排策略，不属于业务实现。

## 一、远端同步

- 用户澄清：远端不是新分支，而是 `origin/main` 在 `1b26c76c` 之后前进了 5 个提交至 `49486e7f`。
- SSH 公钥通道 `git@github.com: Permission denied (publickey)`；改用已登录的 `gh` HTTPS token：
  `git -c 'url.https://github.com/.insteadOf=git@github.com:' fetch origin --prune`。

## 二、5 处冲突的解决策略（首轮）

| 文件 | 策略 | 复核后处置 |
|---|---|---|
| `frontend/research-tasks.js` | 首轮误取主干版本 | **已纠正为三方 union**（见第三节），恢复搜索/ID 直查/复制任务 ID |
| `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` | 首轮误取主干版本 | **已纠正为旧分支版本**：其 `routes_kb.py=2e3abfd0…`、`main.py=cfeea4e5f…` 与合并后实际文件逐字一致；未回退 `main.py`、未改哈希测试 |
| `frontend/styles.css` | 双方 union | 保留：主干按钮/truncate/clamp 规则 + 旧分支 `#evaluation-view` 评测 CSS 均在 |
| `docs/sdd/reviews/045-acceptance-review.md` | 双方 union | 保留：主干 045 报告 + 旧分支 045 完整验收报告与签字均在 |
| `frontend/index.html` | 定制 union | 保留：live `app.js?v=77`（我方）+ `styles.css?v=75`（主干）+ `research-tasks.js?v=25` / `literature-maps.js?v=47`（主干），历史版本一律保留为纯属性兼容 marker；3 个新增裸 `secondary-button` 补齐 `btn-outline` |

## 三、`research-tasks.js` 的三方 union（P0-1 修复）

以共同祖先 `1b26c76c` 为 base，`git merge-file` 合并旧分支（ours，含搜索层）与主干（theirs，含 keyed-diff UX 重构），共 4 处冲突，逐处裁决：

1. **冲突 1（`createTaskCard` 的 `details.textContent`）**：取 theirs。主干已把文本赋值移入 `updateTaskCard`，复用节点原地更新，避免重复赋值。
2. **冲突 2（卡片尾部 + 搜索层 + 渲染入口）**：三者拼接 —— 主干「无条件创建 `.research-open-session` 按钮 + `updateTaskCard(item, task)`」+ 旧分支「任务 ID 行 + 复制任务 ID 按钮（从 `dataset.copyTaskId` 读值，避免 keyed 复用 stale）」+ 旧分支完整搜索层（`normalizeTaskQuery` / `taskQueryHaystack` / `filterSessionsByQuery` / `isCurrentLookupRequest` / `applyTaskIdLookupResult` / `copyTaskIdToClipboard` / `renderTaskSearchCount` / `renderTaskSearchStatus` / `runTaskIdLookup` / `scheduleTaskIdLookup` / `bindTaskSearch` / `applyTaskQuery`）+ 主干 `taskCardChildren` 与 `renderTaskList(options = {})` 签名。
3. **冲突 3（`renderTaskList` 主体）**：以主干 keyed-diff 逐字保留，只在其前加 `const visible = filterSessionsByQuery(state.taskQuery, tasks)` 与 `state.taskSearchCount` / `renderTaskSearchCount()`，并把 `onlyTaskId` 查找、`ordered` 映射、空态与状态计数 5 处引用从全量 `tasks` 改为 `visible`。无搜索词时 `visible` 是 `tasks.slice()`，主干复用/焦点保持行为完全等价。
4. **冲突 4（`boot`）**：两侧绑定都保留 —— `bindResearchTabs(); bindModeGuard(); bindNavigation(); bindNotifications(); bindTaskSearch();`

`state` 的 3 个搜索字段、3 个常量与 `api` exports 均被 `git merge-file` 自动 union，无需手工干预。产物经 `node --check` 与 4 个静态/Node 契约验证后由 `frontend-dev` 原样落地。

## 四、契约与门禁

- `tests/frontend/test_research_detail_actions_placement_contract.py`：仅把精确期望值 `live_app == ["74"]` 同步为 `["77"]`（`v=74` 仍作为纯属性兼容 marker）；未删断言、未改正则。
- 全量回归 `full-regression-rerun.txt`：`4548 passed, 2 skipped, 69 subtests passed`，`PYTEST_EXIT=0`。
- 首轮独立审查 `merge-code-review.md` 结论打回；修复后复审 `merge-code-review-approval.md` 结论**通过（批准合并）**，并逐条披露「无真实 CI workflow」「覆盖率未量化、不虚报 ≥80%」两项门禁偏差。

## 五、残留风险（由复审裁决为非阻断）

- 合并后 `frontend/research-tasks.js` 净增 223 行，但 live 引用仍是主干的 `?v=25`（被 3 个契约冻结）；已有浏览器缓存可能命中旧脚本，部署层需强制刷新或另起任务统一升版。本次合并范围内不擅自扩大改动。
- Langfuse `127.0.0.1:3000` 连接拒绝为导出 span 的预期告警，非用例失败。
- `git diff --cached --check` 的历史空白告警来自 `045/runs/**` 原始 SSE 日志与历史报告，保持证据逐字不改写。
