# 复盘：Spec047 追加范围二（交付物目录治理 + 评测指标体系细化）

> 日期：2026-11-10 ｜ 结论：**收口通过**（验收评审 §14「通过」、准备度 9/10、P0=0/P1=0、架构师签字 §14.9）
> 状态：`待确认 → 已确认 → 实施中 → 已完成` ｜ 未 push、未合 main，`origin/main` 仍 `1b26c76c`

## 1. 用户意图与决策链

| 环节 | 内容 |
|---|---|
| 触发 | 用户指出 `artifacts/task-06/` 裸目录「只看文件夹地址完全看不出来是哪个 spec」，要求目录自解释；并要求「充分想有哪些维度还能增加」「调研 openeval 有哪些指标，哪些可以加入就去实现」 |
| 设计 | 先落盘 `artifacts/README.md` 目录契约 + `docs/sdd/notes/047-openevals-metric-feasibility.md` 指标可行性矩阵 + spec 追加范围二，状态 `待确认`，按 SDD 停下 |
| 确认 | 用户「我确认 你开发吧」→ 台账 `待确认 → 已确认`；两份追加评审通过（P0=0/P1=0）→ `实施中` |
| 分派 | 前后端拆两次独立分派（task-11 `backend-dev` / task-12 `frontend-dev`），定向测试稳定后各集中评审一次，P1 批量修复后各集中复审一次 |
| 收口 | 跨端验收 `tester` §14「通过」+ `architect` 签字裁决 → 真实 API/浏览器 E2E → 全量回归 → 台账/复盘/本地 commit |

**关键决策**

1. **不新增 spec 编号**：用户此前明确「归为 047 追加功能」，本轮继续挂在 047 追加范围二，spec 主体 `已完成` 与 D7–D12 三份评审逐字不翻案。
2. **不接入 OpenEvals 框架**：全仓核实本项目从未引入该库（`openeval` 只是 spec-042 标题用词）。借鉴其指标分类法与 rubric 设计，**复用 `eval_042.judge_client.call_ollama` 作唯一传输层**，新增 `rubrics.py` 做「一次调用出 7 个 rubric 枚举标签」，不是第二套判官框架。
3. **反伪造优先于「看起来都有分」**：B/C/D 档指标（correctness with reference、trajectory、task_completion、多轮模拟、代码沙箱等）缺真值就不进注册表；跨 dataset 一律 `needs_ground_truth` + `reason`，`value=null`，绝不硬编码分数或显示假 0。
4. **目录治理只做最小迁移**：9 个裸目录 → `artifacts/spec-032/task-NN/`，保留其它 spec 的 `plans/NNN/artifacts/` 双落点，历史归档报告的旧写法由映射表解释，不批量改写历史。
5. **纯文档代行三处留痕**：`artifacts/README.md` 头部、调研底稿头部、spec 追加范围二 §3，另在状态台账记录；含 `.py/.js/.html` 的改动一律分派。

## 2. 事实链（真实值，非声称）

| 项 | 真实结果 |
|---|---|
| 目录迁移 | `git mv` 16 个 `R`，9 个裸目录清零；同步 Spec032/032.1 活跃引用 15 文件 22 处；修复 `plans/032.1/task-08` carryover 断链；`artifacts/README.md` 契约 + 旧→新映射表 |
| 指标规模 | `METRIC_KEYS` / `METRIC_LABELS` / `METRIC_GROUPS` 均 22；5 组：检索 6 / 意图 3 / 回答质量 9 / 生成 2 / 安全 2 |
| 判官 | 固定 `qwen3.5:9b`；一次 `call_ollama` 出 7 个 rubric；`chat_quality` 原 `judge_majority` + `enum_to_score` 路径逐字保留 |
| 定向验证 | 后端 `tests/evaluation` 290 passed（P1 修复后 293）、前端评测契约 39 passed、`tests/frontend` 499 passed（含 1 个既有 flaky）、`node --check` 0、`ruff` 0 |
| 真实 API E2E | 11 records = 9×200 / 1×409 / 1×404；4 次 `POST /api/evaluation/score` 全 200 且 `metrics=22`；`chat-quality` 127.023s 实时生成+判官；`compare` 6 项真实 delta（`recall@k +0.5`、`hit_rate@k +0.5`、`nDCG +0.1781`、`retrieval_relevance -0.5`） |
| 真实浏览器 E2E | Chromium 6 步：5 组标题 / 22 卡 / 意图组 computed / 回看 chat-quality 时回答质量 11 项真分可见 / 按组 delta；无 `[object Object]`、无 `innerHTML`、`null → —`、degraded 不隐藏 |
| 全量回归 | 首轮 `2 failed, 4305 passed`（1 个本次迁移断链已修）；最终候选 `1 failed, 4306 passed, 2 skipped, 67 subtests passed in 1249.93s` |
| 部署 | `RERANKER_ENABLED=false ./deploy/start.sh -d` 重启（PID 34342），`/api/health` 200，`app.js?v=75` / `styles.css?v=72` 生效 |

## 3. 踩坑与修复

1. **跨 dataset 口径偏离（P1）**：`_answer_quality_metrics` 初版无条件加载 042 chat 轨迹，导致选 `rag-retrieval` 时回答质量 11 项拿另一个集出分，违反任务卡 §5 与用户「选了评测集就对此打分」。修复：加 `dataset_id` 早退分支，11 项 `needs_ground_truth` + reason 且零外部调用；`chat-quality` 行为不变。
2. **兼容 marker 污染静态契约（P1）**：`index.html` 新增 marker 含完整 `<script ...v=74>` 字面串，使 `_live_versions` 返回 `['75','74']`。修复：按评审建议演进过时断言（而不是堆叠 marker），marker 降为纯属性片段，live 标签恰好 1 个且为 `v=75`；XSS 面归零。
3. **目录迁移断链（全量回归发现）**：`tests/paper_discovery/test_ccs_catalog_coverage.py:17` 硬编码 `artifacts/task-07/ccs-coverage.md`。首轮回归抓到后由 `backend-dev` 定向 RED→GREEN 修一行，最终复跑消除。教训：**文档引用同步不等于代码引用同步**，迁移后必须全仓扫 `.py/.js/.json` 路径常量，不能只扫 `.md`。
4. **服务重启审批阻塞**：裸 `kill` 命令被审批拦截，改用项目标准 `deploy/stop.sh` + `deploy/start.sh -d`（先同步 `deploy/run.pid`）完成；同时确认 Qdrant 本地文件模式必须单进程，不能并存两实例。
5. **前端 120s / 后端 300s 超时不一致**：技术评审 R1(b) 指出后统一为 300000ms，避免「前端报失败但 `save_run` 已落盘」。
6. **既有 wall-clock flaky**：`test_frontend_map_feasibility.py` 的 `maxGestureWallMs < 1000` 实测约 1010–1178ms，5 次独立复跑 `4 passed / 1 failed`；模块只引用 `docs/sdd/plans/043/artifacts/task-02`，与本次无关。**未放宽阈值、未改无关代码、未虚报全绿**，按追加范围一 §13 先例如实记为已知非阻塞项。
7. **Langfuse `:3000` 未启动**：全量回归尾部出现 OTLP 导出 transient error，按 spec 不判失败。
8. **`check_test_layout.py` 退出码 1**：报 4 个含交付编号的历史测试文件（`test_task03_reproducibility.py` / `test_task04_idempotency.py` / `test_task05_decoupling.py` / `test_task06_identity_redaction.py`）。核实均由 `1b26c76c`（spec-045，2026-11-08）引入、本次 `git status` 为空（tracked 且未改动），属既有历史遗留、按项目「历史归档不随改名重写」约定不在本范围；本轮新增 6 个测试全部按能力命名。如实记录，未擅自改名或扩大范围。
9. **`git diff --cached --check` 行尾空白告警**：全部来自 `runs/task-13/full-regression*.txt` 两份 pytest **原始输出**（空行与分隔线），不是代码缺陷。为保证回归证据逐字可复核，未做格式化改写；代码文件 `git diff --check` 退出码 0。

## 4. 分工与边界

| 角色 | 产出 |
|---|---|
| 主会话 | 编排、目录治理（纯文档代行）、spec 追加范围二、状态台账、任务卡、人工验收详情、真实 API/浏览器 E2E、重启部署、复盘、commit |
| `architect` | 需求评审 §14、技术评审「追加范围二」、验收签字 §14.9 合并裁决 |
| `backend-dev` | 22 指标注册表 / `rubrics.py` / 规则类指标 / `service` 编排 / 5 个测试文件 / 两处 P1 与断链修复 |
| `frontend-dev` | 按 `group` 分组渲染、对比按组、超时对齐、`?v=75`/`?v=72`、静态契约 / marker P1 修复 |
| `backend-reviewer` / `frontend-reviewer` | 各一份初评 + 一份 P1 集中复审，均「通过」 |
| `tester` | 跨端验收评审 §14（10/10、准备度 9/10、P0=0/P1=0） |

边界：不新增端点 / DB 表 / 迁移 / SSE 事件；不改 `backend/eval_042/**` 与既有 6 个 key 语义；不改业务对话链路；不引入 `openevals` 依赖；不 push、不合 main、不 force push。

## 5. 交付物速查

| 类别 | 路径 |
|---|---|
| 目录契约 | `artifacts/README.md` |
| 指标调研矩阵 | `docs/sdd/notes/047-openevals-metric-feasibility.md` |
| 设计与状态 | `docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md` 末尾追加范围二 |
| 任务卡 | `docs/sdd/plans/047/task-{11,12,13}-*.md`、`README.md` |
| 三道门禁 | `docs/sdd/reviews/047-{requirement,tech,acceptance}-review.md` §14 |
| 代码评审 | `docs/sdd/reviews/047-{backend,frontend}-metrics-review.md` |
| 真实 API E2E | `docs/sdd/plans/047/runs/task-13/evaluation-metrics-api-e2e.json` + `run-api-e2e.py` |
| 浏览器 E2E | `docs/sdd/plans/047/runs/task-13/browser-e2e.json` + `eval-*.yaml` + `eval-scored.png` |
| 回归 | `docs/sdd/plans/047/runs/task-13/full-regression{,-first-run}.txt` |
| 人工验收 | `artifacts/spec-047-evaluation-metrics-manual-e2e.md` |
| 状态台账 | `docs/sdd/spec-status-changelog.md` |
| 实现交接 | `docs/sdd/plans/047/runs/task-{11,12}/implementation.md` |

## 6. 后续可选（本次明确不做）

- B/C/D 档指标若要纳入，需先补：人工标准答案 / reference、工具调用轨迹、多轮会话与任务完成真值、人类偏好标签；届时新建独立 spec，不回头改 047 结论。
- `langfuse-waterfall.html` / `observability-samples.json` / 未跟踪的 `jd-agent-infra-capability-map.md` 命名不合规，已在 `artifacts/README.md` §3.3 登记，重命名需单独变更。
- 手势性能 flaky 阈值可单独评估（是否改为相对阈值 / 加大采样），属独立技术债，不在本范围。
