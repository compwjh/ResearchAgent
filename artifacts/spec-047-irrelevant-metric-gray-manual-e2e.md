# spec-047 追加范围四：不相关指标灰色弱化 — 人工验收详情

> 状态：已通过 Agent 真实浏览器 E2E 与部署验证，交用户人工复核。
> 服务：`http://127.0.0.1:8000`（PID 50865，`RERANKER_ENABLED=false ./deploy/start.sh -d`）；
> 若端口 8000 被占用，用 `PORT=8300 ./deploy/start.sh -d` 并替换下方地址。

## 一、可复现步骤（六要素）

1. **入口**：浏览器打开 **`http://127.0.0.1:8000/#evaluation-view`**（左侧主导航第 9 项「▦ 评测」也可进入）。
   若此前打开过旧页面，先硬刷新 `Cmd+Shift+R`，确认首页源码第 8 行为 `styles.css?v=76`。
2. **快速回看（推荐，无需等待打分）**：在「运行历史」区域点
   `eval-009223dbf9f649f4bc3426376431e0b6`（`chat-quality`，22 项）。
   **点击后提示**：立刻渲染 5 个分组标题 + 22 张指标卡，状态栏不再显示「尚未评分」。
3. **等待条件与提示**：回看是即时渲染，无等待；若要新打分，选 `chat-quality` + `qwen3.5:9b` + `baseline`
   点「开始评分」，状态栏显示「评分中… / 正在 / 100 条样本」，约 8–10 分钟（27B 模型可能超时，属已知限制）。
4. **下一步（验收点）**：
   - 「检索质量」「意图识别」两组共 **10 张 `needs_ground_truth` 卡**呈中性灰：灰左边框、浅灰背景、灰徽章、灰标题；
   - 「回答质量」「生成可用性」「安全」组的 **12 张 `computed` 卡仍为绿色左边框**，醒目不变；
   - 点灰卡的「参数与明细」仍可展开，`—` / `样本数：0` / `原因：该评测集没有 relevant_doc_ids…` 均清晰可读；
   - 运行历史改点 `eval-cc2b4b91d8ad4c0ba07aafbd99016fe3`（`rag-retrieval`）后，`召回率@k` 恢复绿色 computed；
   - 改点 `eval-a79a15cbd4c64fce964167bbe23abc88` 可看到 `degraded` 卡仍为橙色，未被灰化。
5. **失败恢复**：
   - 若仍见紫色卡片 → 确认首页 live 为 `styles.css?v=76` 并硬刷新 `Cmd+Shift+R`；
   - 若灰卡文字难读 / 被隐藏 / `degraded` 被灰化 → 属 P0/P1，回滚 `styles.css:4406-4410` 五条灰化规则并回到「待确认」重新确认视觉契约；
   - 若服务未启动 → `RERANKER_ENABLED=false ./deploy/start.sh -d`，再 `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/health` 应为 200。
6. **产物查看路径**：
   - 浏览器结构化证据 `docs/sdd/plans/047/runs/task-19/gray-style-e2e.json`、`gray-cards.png`、`gray-initial.yaml`、`gray-final.yaml`、`computed-style-raw.txt`；
   - 部署验证 `docs/sdd/plans/047/runs/task-19/deploy-verification.json`；
   - 实现交接 `docs/sdd/plans/047/runs/task-17/implementation.md`、单端回归 `docs/sdd/plans/047/runs/task-18/frontend-regression.md`；
   - 评审 `docs/sdd/reviews/047-frontend-gray-style-review.md`、需求 §16 / 技术「追加范围四」、验收 §16；
   - 最终全量回归 `docs/sdd/plans/047/runs/task-19/full-regression.txt`。

## 二、人工验收准备度十项检查

| # | 检查项 | 结论 | 证据 |
|---|---|---|---|
| 1 | 需求目标与范围清晰、用户可见行为可测 | PASS | 需求评审 §16 通过 |
| 2 | 数据模型 / 接口无越界改动 | PASS | 技术评审、`git diff -- frontend/app.js` 为空 |
| 3 | 三份评审（需求 / 技术 / 验收）有真实结论 | PASS | 需求 §16、技术「追加范围四」、验收 §16 |
| 4 | 独立代码评审 + 单端回归通过 | PASS | frontend-reviewer APPROVE；`614 passed` |
| 5 | 最终候选全量回归通过 | PASS | `4557 passed, 2 skipped / PYTEST_EXIT=0` |
| 6 | 真实 API E2E（当前部署版本） | PASS | `deploy-verification.json`：health / 首页 / CSS / options 全 200 |
| 7 | 真实浏览器 E2E + 截图 / snapshot 落盘 | PASS | `gray-style-e2e.json` 7 步 PASS + 4 项产物 |
| 8 | 部署可访问、live 版本正确 | PASS | 首页 `styles.css?v=76`、`app.js?v=77` |
| 9 | 状态台账、变更日志、复盘、引用路径齐全 | PASS | changelog、spec §13、`docs/sdd/retro/2026-11-12-*.md`，引用路径 0 断链 |
| 10 | 无 P0/P1、无关键产物缺失 | PASS | P0=0 / P1=0；P2 文案与既有基线项已如实登记 |

**十项 10/10 通过（≥9/10 门槛）**，无 P0/P1、无 API E2E 失败、无关键产物缺失。

## 三、已知非阻塞项（如实登记）

- V5/V7 沿用 `--muted` 在灰底对比度 3.0365:1（既有基线，改动前 3.1306:1），按 spec §13 R1 裁决不扩范围、不用 `opacity`/`filter` 补救。
- `test_research_detail_actions_placement_contract.py:223` / `test_memory_return_global_contract.py:210` 的 f-string 失败提示仍写「为 75」，frontend-reviewer 判 P2 非阻塞。
- `scripts/check_test_layout.py` EXIT=1 的 5 项为既有历史编号测试，非本任务引入。
- 浏览器控制台 4 个 404 来自其它视图历史会话资源；Langfuse `:3000` 未启动。
- 合并后 `research-tasks.js?v=25` 未随净增 223 行升版，属部署缓存层风险（合并 PR #4 已披露，另案处理）。
