# 追加范围三 Task16：真实 API / 浏览器 E2E、验收签字与收口

> 状态：**已完成**（API E2E PASS 18/18、浏览器 E2E PASS、全量回归 `4379 passed / PYTEST_EXIT=0`、验收 §15 与合并裁决签字生效、部署验证 200） ｜ 关联 [spec-047 追加范围三](../../specs/047-evaluation-p2-and-observability-fixes.md)（§8/§9/**§13**） ｜ 索引 [README](./README.md)
> 分派：`tester`（跨端验收总控）+ 主会话（部署验证、状态台账、复盘、本地 commit）
> 依赖：14 → 15 → 16；需求评审 §15 与技术评审「追加范围三」已「通过」，4 项 P1 裁决见 spec §13.1。

## 1. 一句话目标

用**当前部署版本**跑通 ≥100 条样本的真实 API 与浏览器主路径，落盘可复核证据，
完成三道门禁收尾（验收评审 §15 签字、状态台账、复盘、本地 commit），并给用户可点击的访问地址。

## 2. 文件边界

**只允许写**：`docs/sdd/plans/047/runs/task-16/`（证据）、`docs/sdd/reviews/047-acceptance-review.md`（§15 追加）、
`docs/sdd/retro/`（复盘）、`artifacts/spec-047-*.md`（人工验收详情，按 `artifacts/README.md` 契约命名）、
`docs/sdd/spec-status-changelog.md` / spec 状态段（主会话）。

**禁止**：`tester` 改业务代码。发现缺陷 → 回传具体 `文件:行号` + 复现命令，由主会话分派
`backend-dev` / `frontend-dev` 定向修复并复审，**不自行补位写代码**。

## 3. 前置门禁

- task-14 Go/No-Go 基准：**通过**（总耗时 ≤900s、22 项 `computed` 维度 `sample_count ≥ 100` 且 `value` 非 `null`）。
  未通过则**停止收口**，按 spec §13.1 P1-1 回 spec 修订并再次请求用户确认，不得靠 `degraded` 收场。
- task-15 三项自查与定向静态契约测试通过；前后端代码评审与单端回归已完成（task-14/15 之后）。

## 4. 真实 API E2E（不可由 mock / 内部函数 / 仅表单调用替代）

1. 重启服务：`RERANKER_ENABLED=false ./deploy/stop.sh` → 同步 `deploy/run.pid` → `./deploy/start.sh -d`；
   `GET /api/health` 200 才继续（Qdrant 本地文件模式必须单进程，禁止裸 `kill`）。
2. `GET /api/evaluation/options` 200，三份 `datasets[].item_count` 均 **≥100**。
3. **≥3 次**真实 `POST /api/evaluation/score` 200（`max_items=100`，覆盖 `rag-retrieval` / `intent-classification` /
   `chat-quality`，其中至少两次不同策略以支持 delta）；每次记录：请求体、响应体、HTTP 码、`run_id`、
   总耗时、22 项 `status` / `value` / `sample_count` / `detail.reason`、`metrics.length===22`、5 个 `group` 齐全。
4. `GET /api/evaluation/runs` / `runs/{run_id}` 200；`POST /api/evaluation/compare` 200 且 `deltas[]` 带 `group`。
5. 稳定错误码回归：非法选项 404 `EVAL_OPTION_NOT_FOUND`、跨 dataset compare 409 `EVAL_NOT_COMPARABLE`、
   非法 `max_items`（0 / -1 / true / 字符串 / 99999）按 `_clamp_max_items` 收敛且不报错。
6. 落盘 `docs/sdd/plans/047/runs/task-16/evaluation-samples-api-e2e.json`（≥N records，逐字保留请求/响应）、
   `api-e2e.log`、`run-api-e2e.py`；run 产物在 `docs/sdd/plans/047/runs/evaluation/`。

## 5. 真实浏览器 E2E（Playwright CLI / Chromium）

- 打开 `http://127.0.0.1:8000/#evaluation-view`（zsh 中 URL 必须加引号，避免 `#` 被解析）。
- 逐步取证并落盘 `browser-e2e.json` + 每步 `.yaml` snapshot + `.png` 截图：
  ① 选项区显示各评测集真实样本数 ≥100；② 点「开始评分」后按钮禁用且出现「正在 / 评分中…」与「100 条样本」文案；
  ③ 等待 200 后看到 5 个分组标题 + 22 张**紧凑**卡片，样本数显示 100（或如实显示实际条数）；
  ④ `detail` 默认收起、点「参数与明细」展开可见判官模型 / 被测模型 / 映射等参数，关键信息（`value` / `status` /
  `sample_count` / `reason`）**折叠前后都可见**；⑤ 切 `chat-quality` 看回答质量组真实出分；
  ⑥ 「两次对比」看按组 delta。
- 断言：无 `[object Object]`、无 `innerHTML` 注入、`null → —`、degraded 卡片不隐藏、无横向溢出。
- 已知非阻塞项如实记录（不要虚报全绿）：其它视图 404、Langfuse `:3000` 未启动、历史 wall-clock flaky、
  `check_test_layout.py` 的 4 个历史编号测试。

## 6. 全量回归与收口

- Spec 收口阶段跑一次全量回归，记录命令 / 退出码 / 通过数 / 阻塞项；失败先定向修复再重跑，
  **不放宽阈值、不改无关代码、不虚报全绿**；独立复跑确认 flaky 与本次改动无关后可记为已知非阻塞。
- 引用路径存在性检查、真冲突标记扫描（`grep -rn "^<<<<<<<\|^>>>>>>>\|^=======" . | grep -v "/.venv/" | grep -v "/.git/"`，
  `====` 命中须逐条甄别为日志/表格分隔线）、`git diff --check`。
- 验收评审 `047-acceptance-review.md` §15：`tester` 出结论（准备度 ≥9/10、P0=0/P1=0、API E2E 成功、
  关键产物齐全）+ `architect` 签字与合并裁决；未签字不得转 `已完成`。
- 主会话：spec 顶部与追加范围三章节头部状态回 `已完成`、`plans/047/README.md` 与 task-14/15/16 状态回填、
  状态台账追加、复盘 `docs/sdd/retro/2026-11-11-spec047-evaluation-samples-closure.md`、
  人工验收详情 `artifacts/spec-047-evaluation-samples-manual-e2e.md`、本地 commit（不 push、不合 main）。
- 最终回复给出可点击地址 `http://127.0.0.1:8000/#evaluation-view`、实际端口 `8000` 与启动命令
  `RERANKER_ENABLED=false ./deploy/start.sh -d`；若默认端口被占用则选可用端口并明确告知。

## 7. 人工验收可复现步骤（交付前必须 ≥9/10）

逐步点击 → 点击后提示 → 等待条件与提示 → 下一步 → 失败恢复 → 产物查看路径，六要素齐全；
自然语言入口属于产品主路径时优先验证。交给用户前不得有 P0/P1、API E2E 失败或关键产物缺失。

## 8. 明确不做

- 不用 mock / 内部函数 / 仅表单调用冒充真实 E2E；不伪造分数、不隐藏 `degraded`、不把 `null` 说成 0。
- 不因赶进度跳过 Go/No-Go、验收签字、全量回归或部署验证；不扩大已确认范围。
- 不 push、不合 main、不 force push，`origin/main` 仍 `1b26c76c`。
