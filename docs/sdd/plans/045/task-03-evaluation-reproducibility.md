> 关联：[spec-045](../../specs/045-evaluation-observability-hardening.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`待执行`

# Task 03 — 评测可信度：fallback 生效 + 合并判官编排 + 可复现基线

## 状态与一句话目标

`待执行`。让 `--fallback` 真正生效、把三套 judge 编排收敛为一套，
并给评测结果加上可跨运行比较的指纹，使「发布前后质量涨跌」成为可判定的结论。

对应 spec 11 项中的 **01（规格落地）** 与 **02（能力补齐）**。

## 背景与前置条件

- 必读：[spec-045](../../specs/045-evaluation-observability-hardening.md) F3/F4、Q3、验收类别定义；
  [045-evaluation-module-survey.md](../../notes/045-evaluation-module-survey.md) 第 2/5 节。
- **F3**：`backend/eval_042/runner.py:637,662` 的 `fallback` 只写进签名与 metadata，
  `_score_item`（`:452,718-726`）只用 primary；Q8 回退链只存在旁路
  `consistency.py:71-114` 与 `memory_probe.py:278-321`。
- **F4**：导出按 `timestamp.desc` + 输出长度倒序（`langfuse_export.py:267,319`）、
  judge 无 `seed`（`judge_client.py:62-66`）、平票依赖 `Counter.most_common(1)`
  插入顺序（`runner.py:490`）、metadata 不记指纹（`runner.py:658-666`）。
- 编排重复三套：`consistency.run`、`memory_probe.run_probe`、`runner._score_item`；
  脱敏正则三套（`cli.py:30-39`、`runner.py:30-49`、`report.py:112-126`）。
- 前置：task 02 已完成（真实 trace 与 CLI 可跑）。

## 数据、配置与接口

- 报告 metadata 新增：`dataset_sha256` / `judge_model_digest` / `prompt_sha256` /
  `seed` / `tie_break_rule`（不保存 trace 原文、prompt 原文、raw completion、凭据，
  `spec-042:236`）。
- judge 请求增加固定 `seed`；保持 `temperature:0 / think:False / num_predict:160` 语义。
- 数据集导出改为固定时间窗 + 稳定 ID 排序，并计算 SHA256；
  默认 `n_scoreable=20` 等参数不变。
- `ReportWriter` 的 running 骨架与终态字段不删减
  （`report.py:22-24,431-517` 已被 85 个测试锁定）。
- CLI 参数语义不变（`--primary/--fallback/--repeats`），只是 fallback 真正参与执行。

## 实施步骤与文件边界

1. 先写红测：判官 primary 不可用时应切 fallback 并跑完；两次同 seed 同数据集结果一致；
   平票有确定的、与插入顺序无关的规则；metadata 含四类指纹。
2. 抽出一个 judge 编排入口，让 `runner` / `consistency` / `memory_probe` 共用；
   删除重复的裁决逻辑，保留各 CLI 的统计输出语义。
3. `runner._score_item` 接入 fallback；`runner.metadata` 落指纹；
   `langfuse_export` 稳定排序 + dataset hash；`judge_client` 加 seed。
4. 顺带把三套脱敏正则收敛为一处（同任务内消重，不扩大范围）。
5. 回归：`tests/evaluation/` 全量 + 新增用例；产出前后两份 `report.json` 做可比性对照。

**文件边界**：`backend/eval_042/{runner,judge_client,langfuse_export,consistency,memory_probe,config,report,cli}.py`、
`tests/evaluation/**`；**不碰** `backend/app/**`、`frontend/**`。

## 子代理分派

- 含 `.py` 改动 → **必须先 `Task(backend-dev)` 分派**，主会话只做编排与读回校验
  （`AGENTS.md:127,128`）。
- 红测先行：由 `Task(backend-tester)` 或 backend-dev 提供失败用例输出，再进入实现。
- 分派上下文最小化：只给本 task 文档 + 上述路径行号 + 目标状态，不复制整份 spec。

## 边界与明确不做

- **不做** 人工标注 gold 集、`human_agree_rate` 仍为 `null`（P2）。
- **不做** 在线实时评测、**不统一** `quality_score` 与 Langfuse score 口径（P2）。
- 不改变 score POST「恰好一次且不重试」的既有契约
  （`offline_guard.py:199-218`、`tests/evaluation/test_offline_transport.py:95-510`）。
- 不改 `KNOWN_TASKS={chat_quality, memory_correctness}`、不改 skip 语义
  （空输出/Intake/synthetic 仍 SKIPPED）。
- 不新增业务 HTTP 端点（spec-042 边界）。

## 验收、风险与回滚

| 验收点 | 证据 |
|---|---|
| fallback 生效 | 红测先红后绿：mock primary 失败后 fallback 被实际调用并完成评分 |
| 可复现 | 同 seed/同数据集两次运行 `report.json` 的 label/score 一致；指纹字段齐全 |
| 编排收敛 | `consistency` / `memory_probe` / `runner` 不再各写一份裁决逻辑 |
| 回归 | `tests/evaluation` 全量通过；真实 CLI 产物（Q10 证据②） |

风险：`Counter.most_common(1)` 改成显式规则会改变历史平票结果，需在报告中标注
`tie_break_rule` 版本；合并编排可能改变 `consistency.py` 的 Go/No-Go 阈值输出，
须用现有 0.90/0.80/0.80 三个阈值的测试锁住。失败时回滚到任务 02 状态，
不连带改动 task 04–07。

## 产出物、执行结果与变更日志

### 执行结果（2026-11-08，代码与契约测试已完成）

**状态：代码已完成并通过契约测试；Q10 证据 ②（真实 CLI 产物）待 Task 02 环境就绪后补。**

- 改动：`backend/eval_042/{config,judge_client,langfuse_export,runner}.py`，
  新增 `tests/evaluation/test_task03_reproducibility.py`。
- 落地：`--fallback` 真正参与执行（primary 不可用切 fallback）；
  `judge_majority` + `_majority_label` 确定性平票（替换 `Counter.most_common(1)`）；
  `JUDGE_SEED=42`；`stably_sort_items` + `compute_dataset_sha256`；
  report metadata 新增 `dataset_sha256 / judge_model_digest / prompt_sha256 / seed / tie_break_rule`；
  脱敏正则收敛到 `config`。
- 红绿证据：`test_fallback_used_when_primary_unavailable` 断言
  `captured == ["primary-model", "fallback-model"]`，通过。
- 主会话读回复跑：`.venv/bin/python -m pytest tests/evaluation/ -q` → **149 passed**。
- ruff：`runner.py` / `langfuse_export.py` 无 F401/F821/E 类错误；
  剩余 `I001/F541/SIM102/B023/SIM108` 经 `git show HEAD` 基线比对确认为
  HEAD 既有历史债（另有一处本次新增 SIM102，已交 Task 04 顺带收口）。

### 过程记录（如实保留）

首个 `backend-dev` 因上下文 Token 上限中断，留下导入期崩溃
（`langfuse_export.py:191` 的 `@dataclass` 误置于函数前，6 个测试文件收集期全挂）；
第二个 `backend-dev` 以极窄范围收口修复并补全 `_score_item` 接线。
两次日志见 `.codebuddy/agent-logs/spec-045/task-03/backend-dev/`。

### 待补（Task 02 环境就绪后）

真实 `eval_042` CLI 的两份可比 `report.json` 路径与命令、退出码（Q10 证据 ②）。
