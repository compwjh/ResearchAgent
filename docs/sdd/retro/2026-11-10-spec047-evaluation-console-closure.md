# 复盘：Spec047 追加范围「评测台与多维度打分」收口

日期：2026-11-10（Asia/Shanghai）｜分支：`feature/spec-047-evaluation-p2-and-observability-fixes`
结论：**已完成**（验收评审 §13 通过 17/17、准备度 9/10、P0=0 / P1=0，架构师已签字）

---

## 1. 用户需求与交付

用户要求：不新增 spec 号码、归为 047 追加功能、设计好就直接开发；人工验收时能看到
「选策略 + 模型 + 评测集 → 系统打分」，且打分多维度（RAG 召回率/准确率、意图识别准确率）；
功能不要降级/关闭态；并追问「之前 openeval 之类的指标打分为什么看不到」。

交付：主服务新增 `/api/evaluation/*` 五端点与第 9 个「评测」视图，界面三选一触发真实打分，
每个维度独立卡片显示数值 / 状态 / 样本数 / 明细，两次运行按维度给 delta。

## 2. 关键决策

| 决策 | 结论 |
|---|---|
| 归属 | 不新建编号；独立 `048-evaluation-effect-visualization.md` 已删除，设计定稿写入 047 追加章节（D7–D12） |
| 状态流转 | `已完成 → 实施中 → 已完成`，三次流转均在 `spec-status-changelog.md` 记录；原六块历史结论不翻案 |
| 旧边界推翻 | 042/045/047 的「不新增业务端点/前端页面」经用户 2026-11-10 明确授权推翻，ADR0002 追加「修订记录 2」登记 |
| 在线评测 | `EVAL_ONLINE_*` 默认仍关闭、决策 3 未改变；「不降级/关闭态」体现为评测台常驻可用、一键触发、结果立即可见 |
| 反伪造 | 内置标注集统一 `source: builtin-fixture` / `synthetic: true` / `label_source`，不冒充人工标注；不可用维度 `value=null` + `reason` |
| 复用 | 复用 `hybrid_search` / `detect_skill` / `eval_042` 判官与任务注册表，未建第二套框架 |

## 3. 「为什么之前看不到」的事实链

1. 「openeval」是 Spec042 的标题，不是引入的框架；全仓代码/依赖零命中。
   042 的 Q9=C（Langfuse 内置 evaluators）被 `042:95-99` F17 证伪（本机 Ollama `/v1` 不支持 `json_schema`），
   最终只落地自建 LLM-as-judge。
2. 既有实现只有 `chat_quality` / `memory_correctness` 两个单值判官 task；Langfuse 7 个 score 是性能延迟指标；
   「受控基准摘要」也是性能基准。RAG 召回率/准确率、意图识别准确率**从未作为产品能力实现**。
3. 042/045/047 明确不新增端点/页面，产物只写本地 `report.json`，前端只有一个纯文本性能卡片 —— 界面上无处可见。

## 4. 踩坑与修复

| 坑 | 处置 |
|---|---|
| 014 十题 RAG 标注绑定历史 Qdrant，当前 KB 只剩 1 个 `paper_id` 适用 | 从当前 KB（64 篇 / 19905 chunks）真实文档派生 8 条标注，`kb_alignment` 落盘说明「014 不适用」，`label_source=kb-derived:retrieval-rank` |
| **P1：所选模型只是元数据**（`answer_source=frozen_fixture_output`），换模型分数不变 | 改为所选模型实时生成回答 + 固定判官打分；两个模型真实得 0.5 / 1.0；生成失败如实 `degraded`，不回退冻结 output、不伪造 |
| **P1：运行历史显示 `[object Object]`**（`strategy` 是对象却直接 `String()`） | 新增 `formatEvaluationStrategy` helper，4 处调用点统一；浏览器复核 `includes('[object Object]') === false` |
| `compare` 成功体字段名 spec 未定稿 | 前端兼容多形态；主会话真实回查确认后端返回 `deltas[]`，契约一致 |
| `reranker available=false` / `chunker-v2` 无 v2 真值 / `memory_correctness` 无记忆真值 | 如实 `degraded` / `needs_ground_truth` + reason，不编造数值、不隐藏卡片 |
| 全仓 pytest 1 failed（手势性能阈值 1015–1030ms > 1000ms） | 负载敏感、与本次无关，验收 §13 如实记为已知非阻塞项；`test_spa_fallback.py` 因主服务占用 Qdrant 需 `--ignore` |
| 服务初始未启动 | 按 `deploy/README.md` 用 `./deploy/start.sh -d` 启动；Langfuse `:3000` 未启动按 spec 不判失败 |

## 5. 真实结果

- `GET /api/evaluation/options`：4 策略 / 12 模型 / 3 评测集（复用 `/api/models` 数据源）。
- RAG baseline：`recall@k=0.3333`、`precision@k=0.0667`、`mrr@k=0.3333`；
  `topk-10`：`recall@k=1.0`、`precision@k≈0.1`、`mrr@k≈0.4306`；compare delta `recall@k +0.6667`。
- 意图：`intent_accuracy=1.0000`（真实 `detect_skill`，样本数 3）。
- `chat_quality`：`qwen3.5:9b` → 0.5、`qwen3.8:27b-q4` → 1.0（`answer_source=live_generation`）。
- 真实浏览器：`#evaluation-view` 三选一 → 打分 → 分维度卡片全部渲染；`app.js?v=74` / `styles.css?v=71` 200。
- 回归：后端 33 passed、前端 24 passed + 326 passed 静态回归、`node --check` 0、ruff 新增文件 All checks passed；
  全仓 `4224 passed, 2 skipped, 67 subtests`（1 个无关性能阈值失败如实记录）。

## 6. 分工（真实发生）

| 角色 | 产出 |
|---|---|
| `architect` | 追加范围设计定稿（D7–D12）、需求/技术追加评审、验收签字与合并裁决 |
| `backend-dev` | 五端点、指标注册表、三份标注集、契约测试、模型假开关 P1 修复 |
| `frontend-dev` | 第 9 视图、`?v=N`/XSS 静态契约、`[object Object]` P1 修复 |
| `tester` | 跨端验收评审 §13（17/17、9/10、通过） |
| 主会话 | 编排、真实 API + 浏览器 E2E、状态台账、ADR 修订、复盘、部署验证、本地 commit |

## 7. 边界

- 内置标注集是合成/派生的，不是真人标注；`human_agree_rate` 仍需 ≥20 条人工标注。
- RAG / 意图维度不使用所选被测模型（固定 embedding / 模块固定识别链路），明细里标 `model_participates=false`。
- 在线旁路仍默认关闭；本次未改 `EVAL_ONLINE_*`、`spec-042` 正文保持原状。
- 不迁历史 trace / score，不改业务对话链路与 SSE 帧；不 push、不合 main，`origin/main` 仍 `1b26c76c`。

## 8. 交付物速查

| 用途 | 路径 |
|---|---|
| 设计定稿 | `docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md:342-520` |
| 三份追加任务 | `docs/sdd/plans/047/task-08..10-*.md`（均 `已完成`） |
| 真实 API E2E | `docs/sdd/plans/047/runs/task-10/evaluation-api-e2e.json` |
| 真实浏览器 E2E | `docs/sdd/plans/047/runs/task-10/browser-e2e.json` |
| 实现交接 | `docs/sdd/plans/047/runs/task-08/implementation.md`、`task-09/implementation.md` |
| 内置标注集 | `docs/sdd/plans/047/gold/builtin-*.json` |
| run 产物 | `docs/sdd/plans/047/runs/evaluation/` |
| 人工验收详情 | `artifacts/spec-047-evaluation-console-manual-e2e.md` |
| 验收评审与签字 | `docs/sdd/reviews/047-acceptance-review.md` §13.7 / §13.9 |
| ADR 修订 | `docs/adr/0002-...md`「修订记录 2」 |
| 状态台账 | `docs/sdd/spec-status-changelog.md` 末两条 |
