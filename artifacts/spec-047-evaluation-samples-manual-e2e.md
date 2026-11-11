# Spec047 追加范围三 人工验收详情：≥100 条真实样本 + 紧凑可展开指标卡

> 交付物目录契约见 [`artifacts/README.md`](./README.md)：文件名 `spec-047-*` 标明所属 spec，
> 过程日志在 `.codebuddy/agent-logs/`，E2E 证据在 `docs/sdd/plans/047/runs/task-16/`。
> 服务地址：**http://127.0.0.1:8000/#evaluation-view**（端口 `8000`，启动命令 `RERANKER_ENABLED=false ./deploy/start.sh -d`）。
> 本文件只描述可复现步骤与产物路径，不替代真实 API / 浏览器 E2E 证据。

## ① 入口与选择（自然语言主路径）

1. 浏览器打开 `http://127.0.0.1:8000/#evaluation-view`（左侧主导航第 9 项「▦ 评测」）。
2. 三个下拉依次选择：
   - **策略**：`基线（v1 / top_k=5 / reranker=off）`；
   - **模型**：**建议 `qwen3.5:9b`**（100 条实测 596.084s；`qwen3.8:27b-q4_K_M` 等大模型 × 100 条可能触发超时，见 ⑤）；
   - **评测集**：`RAG 检索召回（128 条样本）` / `意图识别分类（120 条样本）` / `回答质量（既有判官轨迹）（120 条样本）`。
3. **可核对**：选项区直接显示真实样本数，三份集均 ≥100；状态栏提示「选项已加载：请选择策略、模型与评测集后点击『开始评分』」。

## ② 点击后提示

点「开始评分」后按钮禁用，状态栏出现「评分中…」/「正在」以及
「100 条样本真实打分（批量生成 + 批量判官，可能耗时数分钟）」。
**不会出现「功能降级 / 关闭 / 不可用」隐藏态**；不可用维度照常显示卡片与原因。

## ③ 等待条件与提示

等待 `POST /api/evaluation/score` 返回 HTTP 200（本地 9b 模型实测约 **8–10 分钟**，
前端超时 `900000ms` 与服务端 `SCORE_TIMEOUT_SECONDS=900.0` 对齐）。
期间可点「刷新历史」回看已落盘 run，不影响本次请求。
成功后状态栏给出本次 `run_id`，「分维度分数」区渲染 5 个分组 + 22 张卡片。

## ④ 下一步（用户要看到的效果）

1. **看多维度分数**：5 个分组标题「检索质量 / 意图识别 / 回答质量 / 生成可用性 / 安全」，
   共 22 张**紧凑**卡片（实测 `padding:8px`、`gap:5px`、数值 `18px`、网格 `minmax(160px,1fr)`）。
   每张卡**始终可见**：`label`、`value`、`status`、样本数、`reason`；`null` 显示 `—` 而非 `0`。
2. **看样本数**：computed 维度显示「样本数：100」，与真实参与计算的条数一致。
3. **点开看详情**：点卡片下方「**参数与明细**」展开原生 `<details>`（默认收起），
   可见判官模型、被测模型、`answer_source`、`score_mapping`、`judge_mode`、逐类明细等 7+ 行参数；
   关键信息留在折叠区外，展开前后都可见。
4. **看策略效果提升**：换策略（如 `扩大召回（v1 / top_k=10 / reranker=off）`）再打一次分，
   在「两次对比」里选同评测集的两个 run → 按 **5 组**展示 22 项 `delta`（如 `回答切题度：delta +0.0000`）。
5. **切评测集**：`chat-quality` 看回答质量 / 生成 / 安全 11 项真实出分；`rag-retrieval` 看召回率、准确率、MRR 等；
   `intent-classification` 看意图识别准确率 / 宏平均 F1。所选评测集决定评分对象，跨集不出分。

## ⑤ 失败恢复（如实，不隐瞒）

| 现象 | 原因 | 恢复动作 |
|---|---|---|
| HTTP 504 `EVAL_SCORE_TIMEOUT` | 大模型（如 `qwen3.8:27b-q4_K_M`）× 100 条超出 900s 预算 | 换 `qwen3.5:9b` 重试；或减小 `max_items` 后重试。错误体 `retryable:true`，不残留半成品 run |
| 某些维度 `degraded` / `needs_ground_truth` | 判官批次解析失败，或该评测集不含对应真值 | 卡片照常显示 `status` + `reason`，**不隐藏、不显示假 0**；其余批次与维度真实出分；可重试 |
| 检索 / 意图 10 项在 `chat-quality` 集为 `needs_ground_truth` | 跨 dataset 早退：该集没有 `relevant_doc_ids` / `expected_intent` 标注 | 切到 `rag-retrieval` / `intent-classification` 集查看这些维度 |
| 浏览器其它视图 404 | 历史会话资源不存在（已知非阻塞） | 不影响评测视图；刷新即可 |

## ⑥ 产物查看路径

| 产物 | 路径 |
|---|---|
| 最终部署版本 Go/No-Go（GO / 596.084s） | `docs/sdd/plans/047/runs/task-16/go-no-go-final.json` |
| 真实 API E2E（请求 / 响应 / HTTP 码 / run_id / 22 维 / 耗时） | `docs/sdd/plans/047/runs/task-16/evaluation-samples-api-e2e.json`、`api-e2e.log` |
| 首轮 NO_GO 与配置级重试原证 | `docs/sdd/plans/047/runs/task-14/go-no-go.json`、`go-no-go-retry-9b.json` |
| 浏览器快照 / 截图 | `docs/sdd/plans/047/runs/task-16/eval-initial.yaml`、`eval-compact.yaml` / `.png`、`eval-compare.yaml` / `.png` |
| 三份内置集（128 / 120 / 120 条） | `docs/sdd/plans/047/gold/builtin-*.json` |
| 生成脚本（只读 KB、幂等） | `scripts/generate_evaluation_samples.py` |
| 后端 / 前端交接与回归 | `docs/sdd/plans/047/runs/task-14/implementation.md`、`backend-regression.md`；`runs/task-15/implementation.md`、`frontend-regression.md` |
| 评审报告与签字 | `docs/sdd/reviews/047-requirement-review.md` §15、`047-tech-review.md`「追加范围三」、`047-backend-samples-review.md`、`047-frontend-compact-cards-review.md`、`047-acceptance-review.md` §15 |
| spec / 状态台账 / 复盘 | `docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md` §13、`docs/sdd/spec-status-changelog.md`、`docs/sdd/retro/2026-11-11-spec047-evaluation-samples-closure.md` |

## 已知非阻塞项

- 修复后未单独复测 27B × 100 条（见 ⑤）；选该模型可能超时，按失败恢复处理。
- 其它视图 4 个会话接口 404、Langfuse `:3000` 未启动、历史 wall-clock flaky 测试、
  `check_test_layout.py` 的 4 个 spec-045 历史编号测试 —— 均与本次改动无关，如实登记、未虚报全绿。

## 签字栏

| 角色 | 结论 | 日期 |
|---|---|---|
| 实现（`backend-dev` / `frontend-dev`） | 已完成 | 2026-11-11 |
| 评审（`backend-reviewer` / `frontend-reviewer` / `backend-tester` / `frontend-tester`） | 通过（P0=0 / P1=0） | 2026-11-11 |
| 跨端验收（`tester`） | **通过**（准备度 9/10、P0=0/P1=0），`reviews/047-acceptance-review.md` §15 已签字 | 2026-11-11 |
| 架构师合并裁决（`architect`） | **通过 · 同意收口**，`reviews/047-acceptance-review.md` §15.6 / §15.8 已签字（全量回归补记后生效） | 2026-11-11 |
| 用户人工验收 | ____________ | ____________ |
