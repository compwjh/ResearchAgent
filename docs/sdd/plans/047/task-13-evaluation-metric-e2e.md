# 追加范围二 Task13：真实 E2E / 部署验证 / 收口

> 状态：**已完成** ｜ 关联 [spec-047 追加范围二](../../specs/047-evaluation-p2-and-observability-fixes.md) ｜ 索引 [README](./README.md)
> 分派：`tester` + 主会话 ｜ 依赖：Task11（后端 22 指标）+ Task12（前端分组视图）均完成

## 1. 一句话目标

用**当前部署版本**跑通真实 API 与真实浏览器 E2E，看到 5 组 22 个维度分数与按组 delta，
落盘可复核证据，交 `tester` 出验收评审、`architect` 签字，再收口。

## 2. 前置

- 主服务 `http://127.0.0.1:8000/api/health` 返回 200；若未启动按 `deploy/README.md` 用
  `./deploy/start.sh -d` 起服务，端口占用则选可用端口并明确告知用户。
- Langfuse `:3000` 未启动**不据此判失败**（沿用追加范围一验收口径）。
- 前端 `app.js?v=75` 已生效（硬刷新后确认）。

## 3. 真实 API E2E（禁止 mock / 内部函数 / 仅表单调用）

至少 4 次 `POST /api/evaluation/score`（真实 HTTP，记录请求体、响应体、HTTP 码）：

| # | strategy_id | model | dataset_id | 目的 |
|---|---|---|---|---|
| 1 | `baseline` | 任一可用本地模型 | `rag-retrieval` | 检索组 6 项真实出分 |
| 2 | `topk-10` | 同上 | `rag-retrieval` | 策略切换产生按维度 delta |
| 3 | `baseline` | 同上 | `intent-classification` | 意图组 3 项真实出分 |
| 4 | `baseline` | 同上 | `chat-quality` | 回答质量 / 生成 / 安全组真实出分（实时生成 + 联合判官） |

再加 `GET /api/evaluation/options`、`GET /api/evaluation/runs`、`GET /api/evaluation/runs/{run_id}`、
`GET /api/evaluation/compare?a=&b=`（同 dataset 两次 run）与一次跨 dataset 的 `EVAL_NOT_COMPARABLE`。

**每次必须落盘**：真实请求体、响应体（含 22 个 key / `group` / `value` / `status` / `sample_count` /
`detail.reason`）、HTTP 状态码、`run_id`、最终状态、产物路径。
索引写 `docs/sdd/plans/047/runs/task-13/evaluation-metrics-api-e2e.json`。

## 4. 真实浏览器 E2E

用 Playwright CLI 打开 `http://127.0.0.1:8000/#evaluation-view`：

- 三个下拉可见且能选；点「开始评分」后看到「评分中…」禁用态，完成后看到分组标题与指标卡。
- **必须验证 5 个组标题中至少出现 3 个**（不同 dataset 激活不同组），且每个非 computed 卡片显示
  `status` + `reason`，**没有一张把 `null` 显示成 `0`**、全页 `document.body.innerText` 不含 `[object Object]`。
- 切策略再打分一次，用「两次对比」看到按组 delta。
- 落盘 snapshot yaml + 截图 png + `browser-e2e.json`（含控制台异常、失败恢复、真实文本断言）到
  `docs/sdd/plans/047/runs/task-13/`，**不留在仓库根目录**（见 `artifacts/README.md` 目录契约）。

## 5. 收口清单（逐条可勾）

- [ ] 后端定向 pytest + 前端静态契约 + `node --check` + `ruff check backend/app/evaluation` 全绿，记录命令 / 退出码 / passed 数。
- [ ] Spec 收口前**全量回归** `cd backend && ../.venv/bin/python -m pytest -q`（已知与本次无关的手势性能阈值失败如实记录，不隐瞒、不改无关代码）。
- [ ] 三份评审：`047-requirement-review.md` §14、`047-tech-review.md`「追加范围二」已通过；
      `047-acceptance-review.md` §14 由 `tester` 出「通过/不通过」结论（含 17+ 项逐条、准备度 ≥9/10、P0=0/P1=0），`architect` 填签字栏。
- [ ] 状态台账追加 `实施中 → 已完成`；spec 顶部与追加范围二章节头部状态回 `已完成`。
- [ ] 复盘 `docs/sdd/retro/2026-11-10-spec047-evaluation-metrics-expansion-closure.md`。
- [ ] 引用路径检查（所有新增链接存在）、冲突标记扫描（覆盖所有文件含 `.gitignore`）。
- [ ] 人工验收详情 `artifacts/spec-047-evaluation-metrics-manual-e2e.md`：逐步点击、点击后提示、等待条件与提示、下一步、失败恢复、产物查看路径、签字栏。
- [ ] 本地 `git commit`（Conventional Commits，`Refs: spec-047`）；**不 push、不合 main**，`origin/main` 仍 `1b26c76c`。
- [ ] 最终回复给出可点击访问地址、实际端口、启动命令。

## 6. 明确不做

- 不用 mock / 内部函数 / 仅表单调用冒充真实 E2E；不伪造分数、不把 `degraded` 藏起来。
- 不因 Langfuse 未启动判失败；不改无关失败用例来「刷绿」全量回归。
- 不 push、不合 main、不 force push；不写用户级配置。

## 7. 产出物

`docs/sdd/plans/047/runs/task-13/`（API E2E JSON、browser E2E JSON、snapshot、截图、回归输出）、
`docs/sdd/reviews/047-acceptance-review.md` §14、复盘、人工验收详情、本地 commit。
进展日志：`.codebuddy/agent-logs/spec-047/task-13/tester/<YYYYmmdd-HHMMSS>.md`。
