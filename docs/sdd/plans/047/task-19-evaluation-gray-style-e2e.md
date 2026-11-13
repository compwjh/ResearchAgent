# task-19 不相关指标灰色弱化：真实浏览器 E2E、部署验证与收口

> **产出性质**：纯文档任务书，由主会话代行创建（三处留痕：本头部 / spec 追加范围四 §13 / 状态台账 2026-11-12 条）。
> **状态**：`已完成`；依赖 task-17 → task-18（单向 17 → 18 → 19）。
> **分派**：`tester`（跨端验收总控）、`architect`（合并裁决签字）；真实浏览器 E2E 与部署由主会话执行。

## 一、真实浏览器 E2E（当前部署版本）

用 Playwright CLI / Chromium 打开评测视图（服务实际端口由部署验证确定）：

1. 选 `chat-quality` + `qwen3.5:9b` + `baseline` 点「开始评分」，或回看运行历史任一 `chat-quality` run（如 `eval-009223db…`）立即渲染。
2. 读 `getComputedStyle` 复核 `needs_ground_truth` 卡片：`borderLeftColor` 为 `#c9cbd3` 对应 rgb、`backgroundColor` 为 `#f6f6f8` 对应 rgb、徽章 `color` 为 `#5f626c` 对应 rgb、标题 / `<summary>` 为 `--muted-strong`。
3. 复核 `computed` 卡仍绿、`degraded` / `unavailable` 未被灰化；灰卡 `—` / `原因：…` / `样本数：0` 可见；点「参数与明细」可展开；不隐藏任何卡。
4. 切到 `rag-retrieval` 集后检索组恢复 computed 绿卡。
5. 落盘 `docs/sdd/plans/047/runs/task-19/gray-style-e2e.json`、snapshot、截图；按 WCAG 公式记录 V3 / V4 实测比值，并如实登记 R1（V5/V7 `--muted` 3.0365:1 既有基线退化，不用 `opacity` / `filter` 补救）。

## 二、部署验证

- Agent 实际启动或复用服务，`GET /api/health` 200、首页 200、`index.html` live `styles.css?v=76`；服务已在跑则硬刷新（静态文件磁盘读取、无需重启）。
- 端口被占用时选可用端口并直接启动；失败须写明具体阻塞原因与用户可执行命令，不得声称已部署。
- 最终回复必须给出可点击访问地址、实际端口与启动命令。

## 三、验收签字与收口

1. `tester` 出具 `docs/sdd/reviews/047-acceptance-review.md` §16（通过/不通过 + 签字），汇总单端回归与浏览器 E2E。
2. `architect` 合并裁决签字；十项人工验收准备度至少九项通过，无 P0/P1、无关键产物缺失。
3. Spec 收口：最终候选全量回归 `.venv/bin/python -m pytest -q`，记录命令 / 退出码 / 通过数 / 阻塞项（`AGENTS.md`：全量回归只在 Spec 收口阶段启动）。
4. 状态 `实施中 → 已完成`，台账追加；复盘落盘 `docs/sdd/retro/`；人工验收详情按 `artifacts/README.md` 契约命名 `artifacts/spec-047-*.md`（含逐步点击、提示、等待条件、失败恢复、产物路径）。
5. 闭环后本地 `git commit`（Conventional Commits + `Refs: spec-047`），**不 push、不合 main、不 force push**。
