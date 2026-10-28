# Task11 浏览器扩展后的公开 API 只读核验（2026-10-28）

**结论：本次限定的 UI 扩展后 API 核验通过。** 仅验证主会话通过浏览器提交的两个 batch 与三篇新增论文；不替代 Task11 最终验收，也不计入前一份独立 API E2E 的三篇论文。

## 范围和方法

- 服务：`http://127.0.0.1:8000`；map：`0baabeae7268429c9f7e4de8098ae1d0`。
- 本轮仅执行 6 个公开 HTTP GET：两个 batch job、三个 analysis、当前 graph。未提交 POST、未启动分析、未变更服务或图数据。原始记录不包含请求头、Cookie、API key 或环境变量。
- 浏览器交互由主会话执行。本报告只读取公开 API，并引用主会话提供的 DOM 快照；不声称本 agent 操作浏览器。
- 原 API E2E 的三篇和 revision 191 快照 `038` 保持原报告不变。当前图 revision 195，作为本轮浏览器新增数据的只读观测。

## Batch 与 analysis 终态

| UI batch | node / 论文 | analysis_id | status | evidence | source_version | model | summary |
|---|---|---|---|---|---|---|---:|
| `db39f31b8a4545acadec45968ea773fb` | `33c9baddfd284c2ea8088f430ad63a95` · Inductive Representation Learning on Large Graphs | `e44bacad6cd04a449fee882f9a010e2e` | completed / job completed | abstract | `2b40cc974a82981265123d67017d360b6e7515fcfc3e41f7805b5aa66a159a53` | `qwen3.8:27b` | 487 chars |
| `db39f31b8a4545acadec45968ea773fb` | `558415d254e043f09d711b770aaf5076` · LLM-Enhanced MARL for Multi-Hop UAV Networking: An Edge-Cloud Protocol Aware Framework | `8826e71b23004b2f99367117f32b9908` | completed / job completed | abstract | `30b96447bde41972a6788883c760c9ea3e16996eb9c68b66f6f35421f99be120` | `qwen3.8:27b` | 420 chars |
| `5a9d46dc70304ff8ba55edf5261b1424` | `0997c1774f2348c1bc9c07e5c526ae3c` · Programmable Agents | `19269bc67d1249dba79b178a54a33955` | completed / job completed | abstract | `ef9f3f27ddea4d9d75a27a532e8d2269ace2a97ecb20c3659dbc6e7783384c94` | `qwen3.8:27b` | 408 chars |

两个 batch 的 GET 均为 HTTP 200、`completed`，`failed=0`，`metadata_status=complete`；第一批包含2项，第二批1项。三个独立 analysis GET 均为 HTTP 200，任务自身和 analysis 状态均为 `completed`，摘要均非空、证据等级为 `abstract`。每个 batch item 的 `source_version` 与对应 analysis 相同。模型均为 `qwen3.8:27b`。

API 原始证据：[`requests.jsonl`](task-11-runs/20261028-browser-api/requests.jsonl)、[`verification-summary.json`](task-11-runs/20261028-browser-api/verification-summary.json)，以及目录中 `01`–`06` 的逐请求 JSON。

## 图持久化与旧内容

- 当前 graph GET 为 HTTP 200，revision 195：27 nodes、24 edges。相对封存的 [`038-graph-after-browser-layout.json`](task-11-runs/20261028-real-api/038-graph-after-browser-layout.json)，新增 node ID 正好是上述三项；每篇均有非空摘要与非空 position。
- 三个新增节点的稳定身份和位置：
  - `33c9baddfd284c2ea8088f430ad63a95` — Inductive Representation Learning on Large Graphs；IDs `{"arxiv": "1706.02216", "semantic_scholar": "6b7d6e6416343b2a122f8416e69059ce919026ef"}`；position `{"x": -12.582947356279192, "y": -183.37897542222817}`。
  - `558415d254e043f09d711b770aaf5076` — LLM-Enhanced MARL for Multi-Hop UAV Networking: An Edge-Cloud Protocol Aware Framework；IDs `{"doi": "10.1109/tmc.2026.3713358", "semantic_scholar": "841483b3f6de18cc711d3f4187313f5673bfb401"}`；position `{"x": 159.4170526437208, "y": -183.37897542222817}`。
  - `0997c1774f2348c1bc9c07e5c526ae3c` — Programmable Agents；IDs `{"arxiv": "1706.06383", "semantic_scholar": "046c4ff0b08361b1ee84fecf1292d385d7bca277"}`；position `{"x": 331.4170526437208, "y": -183.37897542222817}`。
- 对比旧24个 node 的 `node_id`、`external_ids`、`position`、`group_id`、`color_override`：无差异；原21条 edge 均完整保留且 JSON 不变；另有3条新 edge。详情见 `verification-summary.json`。
- 主会话提供的 DOM 快照在两个 UI batch 写入后、点击“查看新增论文”导航前显示：旧24行的 DOM 坐标/半径逐字一致，viewport transform 一致；其间距计算报告三篇新节点的最小间距值分别为 24.1176、11.5632、77.6004。快照和间距计算的副本均存于本目录 `parent-provided-*`，来源与非本 agent 浏览器操作的说明见 summary。DOM快照未提供edge行（前后均0）；边保留结论来自公开 graph API 对比。

## 判定边界

- **本次只读 API 核验：PASS。** 两个 UI batch 和三篇 analysis 终态与 source/model/产物均可由 GET 复核；新节点 position 持久化，旧24节点字段与旧21条边保留。
- 主会话此前记录第二批遇 revision 变化后人工重核并再次确认成功、两条历史记录可恢复及切换旧批显示正确；这些属于主会话的 UI 观察，本 agent 未独立重放。
- **Task11 最终验收仍未评估。** 本报告不覆盖全量回归、人工验收 readiness 或项目收口签字。
