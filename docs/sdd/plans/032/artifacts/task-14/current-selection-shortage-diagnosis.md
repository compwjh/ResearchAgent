# Spec032 Task14 selection shortage diagnosis

## 结论

本报告针对真实运行 `spec032-task14-evaluator-fixed-20261011T033306Z`（任务
`1b0419675f49575db562c2d4ed7a2f7f`）复核候选池、evaluator、critic、floor/cap、
synthesis 冻结集合和持久化选择。

结论是：本轮没有发现 backend 的 selection 数量契约失效，也没有发现 server 把
候选 ID、allowlist 或 source snapshot 弄错。失败是可解释的候选不足：Search Worker
从工具返回的目录事实中交接了 4 个有效 recall ID，evaluator 在有实质摘要证据的
候选中保留 2 个；剩余 recall 池不足批准最低 5 篇，系统正确返回
`partial / EVIDENCE_INSUFFICIENT`。本轮不应强行凑入无关论文、放宽 allowlist 或
调整阈值。

## 运行范围与只读证据

- 分支：`codex/spec032-final-acceptance`
- 部署提交：`e83fdd6f8a43484f42e06d69a0d57f29f408bf51`
- 批准约束：`min=max=target=budget=5`，source=`usenix`，年份 `2024`
- s1 search：`168f85b8f4384fa989df4e373fef50b8`
- s2 search：`34374b8413ed49bf96249fb18c5ab8d1`
- 数据库和目录状态均以 SQLite `mode=ro` 读取；没有写入生产数据、环境变量或
  密钥，也没有重试旧 task、启动第二部署或运行全量回归。

## 候选池边界

### 原始工具结果与 Search Worker 交接

只读 `AgentRun` envelope 的 `tool_results` 显示：

- s1 的 `search_paper_catalog` 工具摘要有 8 个目录 ID；s2 有 5 个目录 ID，原始
  工具结果的 union 为 8 个 ID。
- 但是 Search Worker 的合法输出 `candidates` 分别只有 3 个：
  - s1：`ef9e0846844e5b02834163586ea6ddc9`、
    `9793a4a35caad52ee99f926ae7c90810`、
    `bb826cac3486a295d93eb9b6cea0a6f8`
  - s2：`ef9e0846844e5b02834163586ea6ddc9`、
    `9793a4a35caad52ee99f926ae7c90810`、
    `57e0402f82fe2ce354bea423b201fde3`
- 因而编排器的有效 Search Worker recall allowlist 是 4 个 ID：
  `ef9e0846844e5b02834163586ea6ddc9`、
  `9793a4a35caad52ee99f926ae7c90810`、
  `bb826cac3486a295d93eb9b6cea0a6f8`、
  `57e0402f82fe2ce354bea423b201fde3`。

这不是 server 把工具候选错误地当成最终选择：runtime 的边界是允许 Search Worker
只从工具事实中返回一个合法子集，后续 evaluator/synthesis 只能在 Search Worker
实际交接的 recall 集合内工作。把 raw tool result 中未被 Search Worker 交接的 4
个 ID 直接塞进后续选择，会越过既有 allowlist 和证据来源契约。

### evaluator 保留与淘汰

e1 的输入 `catalog_paper_ids` 正是上述 4 个 recall ID；`catalog_evidence` 中两
个有摘要的候选是：

- `ef9e0846844e5b02834163586ea6ddc9`，Stop, Don't Click Here Anymore…，模型安全
  摘要评分约 `0.92`；
- `9793a4a35caad52ee99f926ae7c90810`，Cascade: CPU Fuzzing…，模型安全摘要评分
  约 `0.88`。

e1 输出是合法 aggregate：`candidate_id=null`、`keep=true`，
`evidence_refs` 只引用上述两个 `catalog:<id>`。它的 reason 说明这两个候选有
实质技术证据，而 `bb826cac3486a295d93eb9b6cea0a6f8`（DARKFLEECE）和
`57e0402f82fe2ce354bea423b201fde3`（DNN-GP）在本次 evaluator handoff 中只有
标题元数据，作为 metadata-only placeholders 排除具体论文分析。该决策没有引用
未提供的摘要或全文事实，也没有出现新的 out-of-scope ID。

本地 paper-search 目录只读核对显示上述两个 metadata-only ID 在目录中确实有摘要；
这只能作为同一 recall ID 的安全 backfill，不能把 raw tool union 中未交接的 ID
变成候选。由于有效 recall 池总数仍只有 4，backfill 也无法满足最低 5 篇。

## floor、cap、critic 与冻结集合

- `validated` ID 数量为 2。
- `_promote_catalog_floor` 的 existing 为 2，recall 中尚未选的 ID 为 2，完整
  recall pool 为 4；`4 < _MIN_REPORT_CANDIDATES(5)`，因此按契约原样返回 2，
  不调用 floor 伪造第五篇。
- `_agent_selection_limit(5)` 为 5；`_bound_agent_selection` 没有截断，结果仍
  是相同的 2 个 ID。cap 不是短缺原因。
- c1 输出 `coverage=0.0`、缺口为“未检索到任何相关论文”和“缺乏对 5 篇目标论文
  的识别与内容获取”，并建议 bounded replan；但 c1 输入只有 `goal` 和
  `gap_threshold`，没有候选列表，且它没有缩减 e1 的选择集合。它解释了覆盖不足，
  不是候选被 server 丢失的根因。
- syn input 的 `validated_candidates`、`citation_allowlist` 和 `matrix_context`
  均冻结为同一 2 个 ID；syn `source_refs` 与之相同。
- durable `research_paper_selections` 也正是同一 2 个 ID，selection version 为
  3。两篇 acquisition 均完成；终端因 `selected 2 of 5` 返回
  `EVIDENCE_INSUFFICIENT`。因此 persistence、synthesis、matrix 入口和 terminal
  accounting 没有分叉。

由此，matrix `409 MATRIX_NOT_READY` 与 canonical report `404 REPORT_NOT_READY`
是最低数量门禁的预期后果，不是 matrix 或报告生成器绕过/改写候选集合的证据。

## 根因判定

本轮根因分类为“有效 recall 池不足 + evaluator 对证据充分性的合理淘汰”，不是
“existing 已验证数量契约失效”：

1. Search Worker 真实交接 4 个合法 ID，少于批准最低 5；runtime 正确使用交接
   `candidates`，没有把未经交接的工具 ID偷偷扩进 allowlist。
2. evaluator 只将两个有摘要的候选冻结为 validated 集合；其余两个在本次有界
   handoff 中仅有标题，未被凭空补写证据。
3. floor/cap/持久化/终端数量均保持同一结果，且既有 selection-budget、catalog
   floor、validated evaluator、matrix bridge 和 persistence 测试全部通过。

没有业务代码或测试代码改动；没有可由同范围最小 backend patch 修复的红灯。强行
把 8 个 raw tool ID 全部纳入会扩大来源范围并破坏 recall allowlist，改变阈值会
掩盖而非修复真实证据不足。

## 同范围可复现主题建议

未执行新的 E2E，仅基于同一 source/year 的本地目录快照给出下一轮可复现主题建议：

> 请比较 USENIX Security 2024 中模糊测试与漏洞发现的方法及局限，至少选择 5 篇、
> 最多选择 5 篇、目标 5 篇；只使用 USENIX Security 2024 官方目录。

只读目录统计显示 `usenix-security/2024` 中标题或摘要含 fuzz 的条目有 19 篇，
19 篇均有非空摘要；其中包括 Cascade、Atropos、EL3XIR、Fuzzing BusyBox、
HYPERPILL、MultiFuzz、ResolverFuzz 等。这个统计是主题选择依据，不是对新 E2E
成功的声称；新 run 仍须由 Search Worker 交接至少 5 个真实、同源、同年 ID 后才
能验证最低数量。

## 定向验证

- 只读语义探针：exit `0`。输出确认 raw tool counts `[8, 5]`、handoff counts
  `[3, 3]`、effective recall `4`、validated/floor/bounded/syn/durable 均为同一
  2 个 ID，selection limit 为 `5`。
- 精准后端测试（项目真实 `.venv`）：exit `0`，`18 passed in 1.57s`：
  `tests/research/test_selection_budget_convergence.py`、catalog floor 的三项
  short-pool/existing-pool 测试、`test_validated_evaluator_candidates.py`、
  matrix bridge 的冻结与 shortfall 测试，以及 persistence cap/shared-budget
  测试。
- 静态检查：项目真实 `.venv` 的 `ruff check`（orchestrator/runtime）和
  `python -m py_compile`（orchestrator/runtime）均 exit `0`；ruff 输出
  `All checks passed!`。
- 只读目录主题统计：exit `0`，`fuzz_count=19`、`nonempty_abstract=19`。

## 未验证项

未执行建议主题的新自然语言 E2E、未改代码、未部署、未运行全量回归，也未验证该
主题最终能否由模型在一次 run 中交接 5 个候选。后续应以全新 conversation/session/
task 验证，不重试本 task，不从 raw tool union 伪造第五篇。

