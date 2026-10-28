# Task11 真实 API E2E 验收记录（2026-10-28）

**范围结论：API E2E 在本次已授权范围内通过；Task11 最终验收未评估。** 本记录不代表 Task11 已完成，也不替代前端浏览器验收、全量回归或验收评审签字。

## 运行信息

- run_id：`20261028T134614Z`
- 时间：2026-10-28 13:46:14–14:00:19 UTC（21:46:14–22:00:19 Asia/Shanghai）
- 服务：`http://127.0.0.1:8000`，端口 8000
- 部署候选：`9721cbcb`；部署记录确认 map schema 8、memory schema 8
- Map：`0baabeae7268429c9f7e4de8098ae1d0`（`API E2E graph attention networks r2`）
- Seed：`21041260a5394f42891b020128fa60fa`（`Graph Attention Networks`）
- 起始图：revision 188、21 nodes、18 edges；最终 API 图：revision 190、24 nodes、21 edges
- 部署前后及备份摘要：[`before.json`](task-11-runs/20261028-deployment/before.json)、[`after.json`](task-11-runs/20261028-deployment/after.json)

本次只调用公开 HTTP API；未改产品源码、测试源码、部署、环境变量或模型配置，未运行 pytest/全量回归，也未执行浏览器操作。API 请求记录仅保存方法、路径、请求体、状态码和响应体，不记录请求头、Cookie、API key 或环境变量。

## 真实 API 证据

所有逐次请求与真实响应保存在 [`task-11-runs/20261028-real-api/`](task-11-runs/20261028-real-api/)；[`requests.jsonl`](task-11-runs/20261028-real-api/requests.jsonl) 汇总38次 HTTP 调用，每次也有独立 JSON 文件。图写入前快照为 [`002-graph-before.json`](task-11-runs/20261028-real-api/002-graph-before.json)，可比较旧节点的完整字段、边和 view settings。三篇候选摘要与最终节点的逐字比较在 [`abstract-preservation-comparison.json`](task-11-runs/20261028-real-api/abstract-preservation-comparison.json)；本轮计数及ID汇总在 [`run-summary.json`](task-11-runs/20261028-real-api/run-summary.json)。

### 服务和分页

- `GET /` 与起始 `GET /api/literature-maps/{map_id}/graph` 均为 HTTP 200。起始 map revision 为 188，seed 存在。
- References `POST /previews` 返回 HTTP 202（排队响应）；随后 GET 作业为 `completed`，真实来源返回 45 个候选，`loaded_count=45`、`has_more=false`、`state=exhausted`、`total=null`。来源实际耗尽，不伪造第 46–101 条。证据：[`003-create-references.json`](task-11-runs/20261028-real-api/003-create-references.json)、[`005-job-7fbb48c62a93431babdfce783d514475.json`](task-11-runs/20261028-real-api/005-job-7fbb48c62a93431babdfce783d514475.json)、[`006-preview-1d7e1756209b48cb802e96e782cd14e4.json`](task-11-runs/20261028-real-api/006-preview-1d7e1756209b48cb802e96e782cd14e4.json)。
- Citations 首页 `POST /previews` 返回 HTTP 202；作业终态为 `completed`，返回50条，`has_more=true`。随后两次显式 `load-more` 各返回202并在 GET 后完成；第3页后为150个候选、150个不同 `candidate_id`、150个不同 `identity_key`，`loaded_count=150`、`has_more=true`、`total=null`。这验证了第100条之后的真实候选；总量未知，因此没有声称穷尽来源。三页作业的 `provider_request_count` 均为1。证据：[`004-create-citations.json`](task-11-runs/20261028-real-api/004-create-citations.json)、[`007-job-962bb5b0fa174ac5802d6c5109f3bf40.json`](task-11-runs/20261028-real-api/007-job-962bb5b0fa174ac5802d6c5109f3bf40.json)、[`008-preview-541ca1cec64a4064aa7b272fe4f9e73d.json`](task-11-runs/20261028-real-api/008-preview-541ca1cec64a4064aa7b272fe4f9e73d.json)、[`012-more-541ca1cec64a4064aa7b272fe4f9e73d-task11-e2e-20261028-cite-page2-reread.json`](task-11-runs/20261028-real-api/012-more-541ca1cec64a4064aa7b272fe4f9e73d-task11-e2e-20261028-cite-page2-reread.json)、[`014-preview-541ca1cec64a4064aa7b272fe4f9e73d.json`](task-11-runs/20261028-real-api/014-preview-541ca1cec64a4064aa7b272fe4f9e73d.json)、[`015-more-541ca1cec64a4064aa7b272fe4f9e73d-task11-e2e-20261028-cite-page3.json`](task-11-runs/20261028-real-api/015-more-541ca1cec64a4064aa7b272fe4f9e73d-task11-e2e-20261028-cite-page3.json)、[`017-preview-541ca1cec64a4064aa7b272fe4f9e73d.json`](task-11-runs/20261028-real-api/017-preview-541ca1cec64a4064aa7b272fe4f9e73d.json)。
- Citations 第2页第一次请求因首批完成后 preview revision 已更新，使用 revision 1 得到 HTTP 409 `MAP_PREVIEW_VERSION_CONFLICT`；GET 确认 revision 2 后，使用新显式命令键再次请求成功。原始失败响应未被覆盖，见 [`009-more-...cite-page2.json`](task-11-runs/20261028-real-api/009-more-541ca1cec64a4064aa7b272fe4f9e73d-task11-e2e-20261028-cite-page2.json)；重读见 [`011-preview-...json`](task-11-runs/20261028-real-api/011-preview-541ca1cec64a4064aa7b272fe4f9e73d.json)。本次没有来源429或来源错误，也没有额外无限重试。

### 两方向原子加入和幂等

首批实际选择为两篇不同、当时未在图中且摘要非空的候选：

| 方向 | 论文与稳定身份 | candidate_id | 新 node_id |
|---|---|---|---|
| references | Attention is All you Need；`arxiv:1706.03762` | `candidate-a1a0262a54cd0bbc3e7baed2` | `1bdf6773eadc401cb106b2fcc9a4cbc1` |
| citations | Universal Graph Convolutional Network: Zero-Shot Transfer Across Power Grid Topology Reconfigurations；`doi:10.1109/tsg.2026.3693251` | `candidate-5c62d8572e14ebeb554ca2eb` | `3c18411a87c34a96a4f0cda1d023d2d2` |

同一次 `POST /previews/batch-apply` 返回 HTTP 202、`added_count=2`、`existing_count=0`，map revision 从188只升到189；产生 batch `b0878dbbac1e4becaa33af02d664367b` 和 queue `92f382a294da4beba25f16aaab7976ad`。随后以完全相同请求体和幂等键重放，仍返回同一 batch、queue、node IDs 与 revision189。重放后 GET graph 仍为23 nodes/20 edges，analysis queue total仍为23；没有重复节点、边或分析。证据：[`018-batch-apply.json`](task-11-runs/20261028-real-api/018-batch-apply.json)、[`020-job-b0878dbbac1e4becaa33af02d664367b.json`](task-11-runs/20261028-real-api/020-job-b0878dbbac1e4becaa33af02d664367b.json)、[`025-batch-apply.json`](task-11-runs/20261028-real-api/025-batch-apply.json)、[`026-graph-after-replay.json`](task-11-runs/20261028-real-api/026-graph-after-replay.json)、[`027-analysis-queue.json`](task-11-runs/20261028-real-api/027-analysis-queue.json)。

### Stale revision、显式 revalidate 和第三篇

第三篇 citations 候选为 `TACO-Graph: Automated Construction of Text-Atributed Graphs`（`arxiv:2610.36650`，candidate `candidate-39238cebf9b85ca3578221b4`）。使用已过期的 expected map revision 188 发起 batch-apply，服务返回 HTTP 409 `MAP_PREVIEW_VERSION_CONFLICT`，未产生写入。随后的 GET graph/preview 显示 map revision189、preview revision7/base revision189，候选仍有效且未加入。显式 revalidate 返回 HTTP 200：valid selection 包含该 candidate、invalid selections 为空，preview revision升至8。之后再次显式 batch-apply 返回 HTTP 202，revision从189升至190，新增1篇、已有0篇；新节点 `b261e3e50d16421a8d2d9eb18d1995af`，batch `79105650dd434cfaa30f24bae77c6833`。之后对第一批 batch 的 GET 仍返回 HTTP 200 且 completed。证据：[`028-batch-apply.json`](task-11-runs/20261028-real-api/028-batch-apply.json)、[`029-graph-after-first-stale-409.json`](task-11-runs/20261028-real-api/029-graph-after-first-stale-409.json)、[`030-preview-541ca1cec64a4064aa7b272fe4f9e73d.json`](task-11-runs/20261028-real-api/030-preview-541ca1cec64a4064aa7b272fe4f9e73d.json)、[`031-revalidate.json`](task-11-runs/20261028-real-api/031-revalidate.json)、[`032-batch-apply.json`](task-11-runs/20261028-real-api/032-batch-apply.json)、[`035-job-b0878dbbac1e4becaa33af02d664367b.json`](task-11-runs/20261028-real-api/035-job-b0878dbbac1e4becaa33af02d664367b.json)。

## 摘要分析终态

`202` 只视为“命令已受理”；以下均在后续 GET 中确认分析 job 和 analysis 状态为 `completed`。三篇 metadata 均为 `complete`，三个 `summary` 均非空；证据等级都是 `abstract`，没有下载PDF或使用全文。当前部署实际返回的模型 ID 是 `qwen3.8:27b`。

| 论文 | analysis_id | source_version | 状态 / evidence | summary字符数 |
|---|---|---|---|---:|
| Attention is All you Need | `3f6137cf451a463bb4e015cb17109c66` | `386f492df3b979e6d10ae147c638bd7f959e4724079b1079b946386d3d8f0b72` | completed / abstract | 205 |
| Universal Graph Convolutional Network… | `2232374411774c868701debd6a797192` | `87a701133fa5c5591b90dee728901efcc90753876387fe63a5915effe036d5a3` | completed / abstract | 401 |
| TACO-Graph… | `9c0108dafbe7446d9d8a536008de27a3` | `21542e2328b77f17016b583cd0afb6aeb0da83dc24ac6087453bdf3d6e787ba1` | completed / abstract | 358 |

第一、二篇实际 analysis 响应：[`023-analysis-ref.json`](task-11-runs/20261028-real-api/023-analysis-ref.json)、[`024-analysis-citation.json`](task-11-runs/20261028-real-api/024-analysis-citation.json)；第三篇批次及分析：[`033-job-79105650dd434cfaa30f24bae77c6833.json`](task-11-runs/20261028-real-api/033-job-79105650dd434cfaa30f24bae77c6833.json)、[`034-analysis-third.json`](task-11-runs/20261028-real-api/034-analysis-third.json)。最终 analysis queue GET 为 `state=completed`，24 total、22 completed、0 queued、0 running、0 failed、2 skipped，`failed_items=[]`，见 [`037-analysis-queue.json`](task-11-runs/20261028-real-api/037-analysis-queue.json)。

## 图一致性与范围限制

batch 写入后 graph GET 为 HTTP 200，revision190、24 nodes/21 edges。对照起始 graph：旧21个 node 的完整JSON完全一致；旧18条 edge 的完整JSON完全一致；map `view_settings` 完全一致。新增三条边方向为：seed→references 候选；两篇 citations 候选→seed。新身份均不同，first batch `existing_count=0`，第三批 `existing_count=0`。batch 写入后的 graph 响应见 [`036-graph-final-api.json`](task-11-runs/20261028-real-api/036-graph-final-api.json)。

`036` 快照中新增节点 `position` 为 `null`。主会话随后打开当前图并由既有前端完成布点；本子任务再 GET graph，HTTP 200、revision191，响应中的三个新增 node `position` 均非空：`1bdf6773eadc401cb106b2fcc9a4cbc1` → `(161.3843, -23.8279)`；`3c18411a87c34a96a4f0cda1d023d2d2` → `(376.3843, -3.1879)`；`b261e3e50d16421a8d2d9eb18d1995af` → `(505.3843, -3.1879)`。该后续快照仍显示旧21个节点和旧18条边完整JSON未变，view settings 未变，见 [`038-graph-after-browser-layout.json`](task-11-runs/20261028-real-api/038-graph-after-browser-layout.json)；三篇摘要与graph node值逐字一致，见摘要比较 artifact。这验证了前端布局和摘要已通过公开API持久化。本轮快照在主会话后续独立的两篇UI扩展操作之前封存，不将这些后续数据计入本run。手机交互、人工验收步骤及十项 readiness matrix 仍未在本次API限定范围内执行。

## 判定

- **专项 API E2E：PASS（限本次授权路径）**。来源分页成功（references按真实来源耗尽，citations已超过100条）；首批跨方向加入原子成功；真实方向边、去重、revision、旧图保持、幂等重放、409→GET→revalidate→确认以及三篇摘要分析完成均有公开API证据。
- **Task11最终验收：未评估**。还需整合前端浏览器布局保存/提示验证、人工验收步骤与项目规定的其他Task收口门禁；不得据本报告标记Task11已完成。
- API调用观察到2个HTTP409，均保留了原始响应并按显式GET/重核流程恢复；没有来源429、5xx、后台分析失败或失败单元。

验收进展日志：`.codebuddy/agent-logs/spec-043/task-11/tester/20261028-1345.md`。
