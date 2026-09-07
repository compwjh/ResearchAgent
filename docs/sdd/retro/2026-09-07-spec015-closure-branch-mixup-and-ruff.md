# 复盘：Spec015 收口核对、分支串台与 ruff 引入（2026-09-07）

## 一、收口核对：Spec015 不能转「已完成」

用户要求「spec-015 收口」。核对后发现**不满足** `SDD-GATE-CHECKLIST.md` §3 的 DoD：

| 收口项 | 实际状态 | 是否满足 |
|---|---|---|
| 需求评审 | Task13–17 需求复审 **通过**（`015-catalog-requirement-review.md`） | ✅ |
| 技术评审 | Task13–17 技术复审 **通过**（`015-catalog-tech-review.md`） | ✅ |
| 验收评审 | **整体验收不通过（阻塞）**，QA 已签字，Tech Lead **待签字**（`015-acceptance-review.md`） | ❌ |
| 任务实现 | Task13 约 60%、Task14 已完成，**Task15–17 从未分派、零提交零日志**，Task04 待执行 | ❌ |
| 运行时部署 | A3/A10/A11/A14 等仍受外部数据源与真实环境阻塞 | ❌ |

验收报告本身就写明：「在上述阻塞解除并由 Tech Lead 签字前，Spec015 必须保持 `实施中`，不得标记 `已完成`，不得进入最终提交收口」。因此本次收口的正确动作是**同步文档到真实状态**，而非翻转状态。

**规则化**：「收口」不等于「标记完成」。当 DoD 未满足时，收口 = 状态回填 + 阻塞留痕 + 复盘，状态保持不变。

## 二、发现：Spec017 的工作落在 Spec015 分支上（严重）

核对 `git log` 时发现：

- 当前分支 `feature/spec-015-security-paper-discovery` 上，最近 6 个提交全部是 **`refactor(spec-017)` / `docs(spec-017)`**（`778cd48`、`47669e5`、`742ba15`、`0c2ac56`、`50d7977`、`a804cac`）。
- `git merge-base --is-ancestor 778cd48 main` → **main 不含该提交**，即 017 的成果既没合回主干，也没有独立分支。
- 当前未提交的 `backend/app/api/routes_paper.py` / `routes_article.py`（从 `routes.py` 拆出）同样属于 **Spec017 Task03「拆分 API 与平台装配」的第二批**，与 Spec015 无直接关系。

后果：分支名与内容严重不符，Reviewer 按分支名判断范围会误判；017 若长期不合入，产物有丢失风险。

**规则化**：
1. 开始实现前先 `git branch --show-current` 并核对分支名与 spec 编号一致；不一致则先建/切分支，不要「就在这个分支上顺手改」。
2. 提交前用 `git log --oneline -5` 检查本分支最近提交的 scope 前缀，发现串台立即停止并纠正。
3. 跨 spec 的工作必须落在自己的分支上，不得以「改动相关」为由借用他人分支。

## 三、引入 ruff：0.16 默认规则集是个陷阱

- 实测（在 `/tmp` 建临时文件对照）：**ruff 0.16.6 的默认 `select` 早已不是传统的 `E4,E7,E9 + F`**，默认就会报 `UP045`、`BLE001`、`I001`、`S110` 等，全仓直接 1069 条。
- 这意味着不写配置时，**ruff 升级一个小版本检查结果就会静默变化**，基线不可复现。
- 处理：新建 `ruff.toml` 显式固定 `select`，并把未启用规则的原因（`UP` 存量 630+、`RUF` 中文误报 1713、`S` 存量 610）写进注释，作为后续加严的路线图。
- `line-length` 定 120 而非默认 88：实测 23790 行，P50=37 / P90=80 / P95=93 / P99=121，用 88 会误伤 1601 行。

**规则化**：lint 工具的「默认规则」不等于「合理规则」。引入前先在项目外跑一次对照，摸清默认集与存量基线，再决定 `select`。

## 四、两个容易误判的操作坑

### 1. `git diff --stat` 会把未提交的历史改动一起算进来

执行导入排序后看到「51 files changed, 285 insertions(+), **1577 deletions(-)**」，几乎误判为工具删了代码。实际核对：删除量集中在 `routes.py`(1099)、`routes_system.py`(93)、`common.py`(78)，是 Spec017 路由拆分**尚未提交**的改动，与本次排序无关；抽样无关文件确认只是纯重排。

**规则化**：工作区有未提交改动时，`git diff --stat` 不能作为「本次改动范围」的证据。先用 `git diff --numstat | sort -k2 -rn` 定位删除量来源，再抽样核对。

### 2. F401 不能只看 ruff 的输出就删

18 条 `F401` 里有 4 条看起来像「有意保留的 re-export」（如 `paper_import_batch_service` 导入 `ITEM_FAILED`、`PaperImportError`、`PaperImportResult`）。判定方法是**查有没有别的模块按名从该模块导入**，而不是看 ruff 报什么：

- 测试里 `PaperImportError, PaperImportResult` 是从 `paper_import` 导入的，不是从 `batch_service`；
- `routes_paper.py` / `common.py` 从 `batch_service` 只导入 `PaperImportBatchService`、`PaperImportBatchServiceError`。

确认无人消费后才删。另外 `test_api.py` 的 `import json`，文件里 16 处 `json` 全是 `client.post(..., json={...})` 关键字参数与 `.json()` 调用，与模块无关。

**规则化**：删「未使用导入」前，必须 grep「是否有其它模块从本模块按名导入该符号」；命中即为 re-export，需 `noqa: F401` 或 `__all__`，不可直接删。

## 五、本轮动作与验证

- 引入 ruff（`ruff.toml`、`requirements-dev.txt`、`.gitignore` 加 `.ruff_cache/`）。
- 导入排序修复 58 处；删除确认无引用的死导入 18 处。lint 基线 199 → 122。
- 全量回归 **626 passed / 0 failed**，三步操作前后一致，无回归。
- Spec015 文档收口：状态改 `实施中` 并写明不满足 DoD 的理由；任务表回填 Task13/14；评审记录回填真实结论（消除「待评审（未执行）」占位）；`spec-status-changelog.md` 追加 3 条；本表变更日志补 5 条。

## 六、下一步（阻塞项，需用户决策）

1. **分支纠正**：017 的已提交与未提交改动都在 015 分支上，需决定是切出 `feature/spec-017-...` 分支搬运，还是沿用当前分支完成 017 后一并处理。
2. **Spec015 欠账**：`_listing_for` 新正则无回归测试（`015-backend-review.md` 的 HIGH），列为 015 下一提交的强制项。
3. **顺序**：按用户既定顺序，先完成 017 → 全量回归 → 再回来做 015 Task15/16。
