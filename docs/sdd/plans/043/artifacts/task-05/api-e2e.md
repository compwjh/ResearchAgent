# Task05 真实 API E2E 验收记录

结论：**BLOCKED（全文证据门禁未满足）**

本记录是已部署候选的真实 HTTP 验证，不是 mock、内部函数调用或表单调用。摘要分析、幂等重放、摘要会话和 SSE 闭环真实通过；全文路径按接口门禁返回受控 409，未绕过门禁、未重建知识库、未从应用 API 直连 provider，也未修改生产数据。

## 运行元数据

- run_id：`20261021-002317-b94717c`
- 候选：`codex/spec043-literature-map`，commit `b94717c`
- 地址：`http://127.0.0.1:8000/`，端口 `8000`
- `/api/ready`：HTTP 200，`ready=true`；jieba、ollama_tags、embedding、qdrant 均 `ready`
- `/api/health`：HTTP 200，模型 `qwen3.8:27b`，状态 `ok`
- Langfuse：未启动/未观测；本报告不声称有 Langfuse 观测成功
- 所有请求/响应和脱敏运行摘要：[`api-e2e.json`](runs/20261021-002317-b94717c/api-e2e.json)
- 运行证据目录：[`runs/20261021-002317-b94717c`](runs/20261021-002317-b94717c)

首次沙箱请求的 HTTP 000 已保留为环境证据；随后在不改变请求、服务和数据的情况下使用授权网络重试获得上述 HTTP 结果，未将 HTTP 000 判定为服务故障。

## 候选实体核验

| 实体 | ID | 结果 |
|---|---|---|
| map | `0baabeae7268429c9f7e4de8098ae1d0` | GET 200；revision 9，status `partial`，`project_id=null` |
| node | `21041260a5394f42891b020128fa60fa` | GET 200；标题 `Graph Attention Networks` |
| document | `55afc3b8f01445429462fe78ed0d4c98` | node 的 `document_id` 精确匹配；下载状态 `indexed` |

分析前 GET 返回 `analyses=[]`，`source_status.abstract_available=true`、`fulltext_ready=false`、`available_evidence_levels=["abstract"]`；摘要来源版本为 `c518a10f28b2656ae30f53790a67ef835c8ebe219168460969b763f481d1e42c`，全文来源版本为 null。

## 摘要分析：PASS

请求 `POST /api/literature-maps/{map_id}/nodes/{node_id}/analyses`，请求体为 `evidence_level=abstract` 和固定幂等键 `spec043-task05-abstract-v1`，实际返回 HTTP 202。

- `analysis_id`：`7c63cba835c044859c571dbc87f6a48a`
- `job_id`：`95d900a561664e8b9db4300189abf336`
- 状态轨迹：`pending → running → completed`
- analysis/job 最终状态：`completed/completed`
- version：`1`
- model：`qwen3.8:27b`
- source_version：`c518a10f28b2656ae30f53790a67ef835c8ebe219168460969b763f481d1e42c`
- `result.summary`：非空（分析结果摘要 490 字符）
- `source_refs`：仅 `kind=abstract` 和该 node，无全文片段冒充

使用完全相同的幂等请求重放返回 HTTP 202，仍为同一 `analysis_id`、`job_id`、version 和 source_version，未增加分析版本或第二个 job。最终列表仍只有这一条完成的摘要分析。

## 全文分析：BLOCKED

当前真实 source gate 明确为 `fulltext_ready=false`，因此未启动全文模型。两次完全相同的全文提交（首次与幂等重放）均返回：

```text
HTTP 409
code: MAP_FULLTEXT_UNAVAILABLE
message: 当前依据不可用
retryable: false
```

没有创建全文 analysis/job，也没有把摘要结果降级冒充全文成功。证据见 `full-submit.json`、`full-replay.json`、`analyses-before.escalated.json`。

只读 API 核验到候选文档的状态如下：

- map `project_id=null`，document `project_id=null`
- document status `indexed`；v1/v2 chunker 均 `indexed`，progress 均 100
- document `source_sha256=a7d811a44e1c65bf27da3a01859f23a8edbe33b8f96114b4b5066aedb078f284`
- `/api/kb/papers` 返回 `source_hash_state=legacy_unknown`、`indexed_source_sha256=null`
- `/api/kb/health` 返回 qdrant、embedding、generation ready，但不能替代该文档的 source manifest/项目门禁

为保持验收边界，未调用可能触发自动重索引的 inspection GET，未调用 reindex，也未改项目关联或删除数据。因此当前证据只能说明部署候选不满足全文门禁，不能把全文分支判为 PASS；若要修复，应由主 agent/后端开发处理 canonical project association、source manifest/hash 验证和生成状态后重新执行全文案例。

## 摘要会话和消息 SSE：PASS

摘要会话请求和幂等重放均为 HTTP 200：

- conversation_id：`5e530508d5b9433297bf1be0f27b2352`
- `created=true` 首次，重放 `created=false`
- project_id：null
- evidence_level：`abstract`
- source_version：与摘要分析一致
- context 含 map、node、标题、冻结摘要、外部身份和 document_id；本次会话没有全文证据可见

通过既有 `/api/conversations/{conversation_id}/messages` 发送摘要事实问题，HTTP 200、`Content-Type: text/event-stream`。真实 SSE 共 350 个事件，`event_seq` 严格为 1 到 350；终止 `done.status=completed`。随后 GET messages 显示 user/assistant 均 `completed`，assistant 非空回答 695 字符，未出现可见文档 ID或全文 citations。未执行全文会话，因为全文门禁已阻断。

## 图谱不变量

分析前后 GET graph 均为 revision 9、status `partial`、21 nodes、18 edges；布局和分组字段保持不变。分析完成后 latest job 指针按业务记录切换到 analysis job，但没有改变图谱 revision、节点、边或布局。这符合“分析不得把 partial 图谱写成 ready 或重建图谱”的验收条件。

## 证据文件

- 运行摘要：[`runs/20261021-002317-b94717c/api-e2e.json`](runs/20261021-002317-b94717c/api-e2e.json)
- ready/health/实体和图谱：`ready.escalated.json`、`health.escalated.json`、`map.escalated.json`、`node.escalated.json`、`graph-before.escalated.json`、`graph-after.json`
- 摘要分析：`abstract-submit.json`、`abstract-poll-01.json`、`abstract-poll-02.json`、`abstract-poll-03.json`、`abstract-replay.json`
- 全文门禁：`full-submit.json`、`full-replay.json`、`analyses-before.escalated.json`
- 摘要会话/SSE：`conversation-abstract-submit.json`、`conversation-abstract-replay.json`、`chat-abstract.sse`、`chat-abstract-messages.json`
- 来源门禁只读证据：`kb-documents-page2.json`、`kb-papers.json`、`kb-health.json`

## 脱敏复核

提交前已对两个 run 目录做静态脱敏复核，没有再次请求服务：

- 原始 KB 文档分页发现 50 条唯一非 GAT 记录：首 run 第一页出现 50 次，恢复 run 的 before/3 次 poll 各出现 50 次（跨快照共移除 250 条记录出现）；候选 GAT document 记录保留，响应原始 `total=51` 和分页语义保留，并在 JSON 的 `redaction` 字段标明 `omitted_record_count`。
- 原始 `/api/kb/papers` 与恢复后的 `kb-papers-after.json` 各发现 50 条唯一非目标论文记录（两个快照共移除 100 条记录出现）；GAT 的状态、source hash、chunker 状态、project_id 保留。
- map/graph 响应中的 owner、时间、过滤器、topic、view 设置和 20 个非目标节点/18 条边详情已移除；revision/status、21/18 聚合计数、GAT node 布局快照和 latest-job 状态保留，因此不改变图谱不变量结论。
- 摘要会话只发现本次 GAT conversation 的 2 条消息；未发现其他会话。移除了消息中的所有 `reasoning_*`/首 token/推理状态字段，保留最终 assistant 摘要、消息状态、实体 ID 和 event_seq。
- 原始 SSE 只包含本次摘要会话；已移除 token/content 及任何推理内容，改为保留 350 个事件的 type/seq 范围、终态和 duration。`chat-abstract.sse` 现为脱敏事件摘要，不再是可重放的原始文本流。
- headers 静态扫描未发现 Authorization、Cookie、Bearer、API key 或 token 字段；JSON/SSE 静态扫描未发现绝对内部路径。原始失败码、HTTP 状态、实体 ID、source version、摘要非空/长度和全文 BLOCKED 含义均未改写。

脱敏计数和保留规则同步写入两个 run JSON 的 `redaction` 对象；未删除或改写生产数据。

## 人工验收准备度

本文件记录 backend/API 真实证据；浏览器点击路径由独立 `browser-e2e.md` 记录，未将其缺失的 UI 观察冒充 API 证据。可复现路径为：打开候选地图 → 选择已核验 GAT 节点 → 触发“基于摘要分析”并等待完成 → 打开既有会话提问 → 核对非空结果和会话历史；全文按钮必须在 `fulltext_ready=true` 且来源版本可核验后再执行，否则预期显示受控不可用提示，不应静默降级。

当前准备度不能达到交给用户人工验收的门槛：全文分析、全文会话及其全文引用缺失，且部署候选的来源门禁证据未满足。摘要闭环可作为已成功的局部证据保留，但不能覆盖全文阻塞。

## 最终裁决

**BLOCKED。** 摘要真实 API 主路径和幂等行为通过；全文分支因候选文档 `legacy_unknown`/`indexed_source_sha256=null` 且 map/document 无 project association，被 API 正确拒绝为 `MAP_FULLTEXT_UNAVAILABLE`。完成来源门禁修复或换用满足 canonical source 状态的候选后，应重新执行全文分析、全文幂等重放、全文会话和全文 SSE，并补齐可复核证据；在此之前不签署 Task05 总体通过。

## 有界 v1 恢复尝试（追加 run）

经授权，本节在不覆盖原始失败证据的前提下，对既有 GAT 文档执行了唯一一次有界恢复：

- recovery run：`20261021-003209-b94717c-v1-reindex`
- parent run：`20261021-002317-b94717c`
- 请求：`POST /api/kb/documents/55afc3b8f01445429462fe78ed0d4c98/reindex`，body `{"chunker":"v1"}`
- 返回：HTTP 202，task_id `b41b7c83c071448d8fc2630d4988b093`，queued，progress 0，Retry-After 2
- 轮询：三次只读 `/api/kb/documents?limit=100` 均 HTTP 200；文档和 v1 均显示 `indexed`、progress 100、error null
- 未调用 `GET /api/kb/documents/{id}/inspection`，避免其缺失 manifest 分支产生额外副作用；未全库重建、未删除 PDF/用户数据、未手改 manifest/DB/hash

恢复后的 map source-status 只读轮询（3 次 HTTP 200）仍为：`fulltext_ready=false`、`available_evidence_levels=["abstract"]`、full source version 为 null。`/api/kb/papers` 仍显示 `source_hash_state=legacy_unknown`、`indexed_source_sha256=null`，而 v1 状态仍仅为 indexed 100%，不能证明当前全文 evidence manifest 已 ready。因此本次没有重跑全文分析、全文幂等、全文会话或全文 QA，也没有追加第二次 reindex。

恢复证据和最终状态摘要：[`reindex-e2e.json`](runs/20261021-003209-b94717c-v1-reindex/reindex-e2e.json)。恢复后结论仍为 **BLOCKED**；原摘要成功和原全文 409 证据保持不变。

## 2026-10-21 修复候选 scoped v1 恢复（追加 run）

本节是修复候选 `dd616d5` 上的独立真实 HTTP 运行；保留前两轮失败证据，不覆盖原 run，也没有再次调用 provider、inspection GET 或其他 reindex。

- run：`20261021-015442-dd616d5-v1-reindex`
- 地址：`http://127.0.0.1:8000/`，`/api/ready` HTTP 200，`ready=true`
- 目标：map `0baabeae7268429c9f7e4de8098ae1d0`、node `21041260a5394f42891b020128fa60fa`、document `55afc3b8f01445429462fe78ed0d4c98`
- 证据摘要：[`runs/20261021-015442-dd616d5-v1-reindex/api-e2e.json`](runs/20261021-015442-dd616d5-v1-reindex/api-e2e.json)

### 唯一一次 v1 reindex：HTTP PASS，但全文门禁仍 BLOCKED

按授权请求 `POST /api/kb/documents/{document_id}/reindex`，body `{"chunker":"v1"}`，返回 HTTP 202，task `46266f04e0e445b6ab0dfbb2998f842b`，状态 `queued`。一次只读轮询 HTTP 200 后，目标文档与 v1 均为 `indexed`、progress `100`、error null。没有第二次重试。

修复后的只读 canonical 证据为：目标 `source_hash_state=verified`，`source_sha256` 与 `indexed_source_sha256` 相等；v1 manifest 为 `status=ready`、progress `100`、verified、mapped `57`、unmapped `0`、index fingerprint 存在；generation requirement 通过。node 的 `document_id` 与目标文档精确匹配，map/document `project_id` 均为 null。

随后 GET `/api/literature-maps/{map_id}/nodes/{node_id}/analyses` 返回 HTTP 200，但仍为 `fulltext_ready=false`、`available_evidence_levels=["abstract"]`、`source_versions.full=null`。该未绑定地图的 owner-scoped association 集合没有目标文档条目，服务无法计算全文 `source_version`，因此返回全文不可用门禁。

### 全文分析与会话：未提交，保留真实阻塞

因 source gate 仍未满足，本轮没有提交全文分析、幂等回放、全文会话、消息或 SSE；不存在可声称的全文 analysis/job/conversation ID，也没有把摘要结果冒充全文结果。既有摘要真实成功记录仍引用首轮 run `20261021-002317-b94717c`，未重跑或覆盖。

### 图谱不变量：PASS

scoped reindex 前后只读 graph 均为 revision `17`、status `partial`、`21` nodes、`18` edges；GAT 节点位置保持 `(120.0, 80.0)`，目标 group ID 保持 `8c8f20f7a4c04e0e92f9cdd78fc01ce7`，groups GET 为 HTTP 200 且保留 `1` 个组。脱敏后的布局/分组哈希前后均为 `e88b7d51b1753bb9114c2b90f927fd140d66d726499fe32408119610d58bb3e1`。

### 本轮裁决

**BLOCKED。** 唯一一次 v1 reindex 真实返回并完成，canonical hash 与 manifest 门禁已达到 verified/ready；但当前 unbound map 没有 owner-scoped document association，部署候选仍无法产生全文 source version，故没有绕过门禁发起全文模型或会话。原始全文失败、摘要成功和此前恢复 run 均保留；下一步需由后端处理合法的 shared-pool association/来源解析后，再在新候选上重新执行全文验收。

## 继续验收：服务不可达（追加 run）

继续指令到达后，未重复此前已提交的 v1 reindex。对同一候选 `dd616d5` 只做两项只读核验：GET `/api/kb/documents?limit=100` 与 GET `/api/literature-maps/{map_id}/nodes/{node_id}/analyses` 均在 TCP 层 connection refused，未取得 HTTP 响应（无状态码）。本次不将无状态连接失败解释为业务失败，也没有重启服务。

- continuation run：`20261021-171101-dd616d5-continued`
- 脱敏摘要：[`runs/20261021-171101-dd616d5-continued/api-e2e.json`](runs/20261021-171101-dd616d5-continued/api-e2e.json)
- 由于服务不可达，不能重新确认 reindex 终态或 source gate，也未提交全文分析/幂等、全文会话、QA 或 SSE；此前 `20261021-015442-dd616d5-v1-reindex` 的 verified/ready 与 `MAP_FULLTEXT_UNAVAILABLE` 证据保持不变。

本轮裁决：**BLOCKED（服务不可达，等待已部署候选恢复后再继续只读核验）**。

## 2026-10-21 候选 `82c816f` 全文真实验收（追加 run）

本轮在新的已部署候选上继续验收；不重复已完成的 v1 reindex，不修改图谱、分组或 viewport，不调用 inspection API。运行摘要：[`runs/20261021-172344-82c816f-full/api-e2e.json`](runs/20261021-172344-82c816f-full/api-e2e.json)。

### 来源门禁与实体核验：PASS

- `/api/ready`：HTTP 200，`ready=true`；`/api/health`：HTTP 200，模型为 `qwen3.8:27b`。
- map `0baabeae7268429c9f7e4de8098ae1d0`、node `21041260a5394f42891b020128fa60fa`、document `55afc3b8f01445429462fe78ed0d4c98` 保持既有目标关系。
- `/api/kb/papers`：HTTP 200；目标 source/index hash 相等，`source_hash_state=verified`，v1 `indexed`、progress `100`、error null。
- analyses GET：HTTP 200；`fulltext_ready=true`、`available_evidence_levels=["abstract","full"]`；full source version 为 `a253fa60f4d0444592fd52f89e23016e8d437f01335f300b176d610eeefa644c`。既有摘要 version 1 保留。

### 全文分析与幂等：PASS

全文分析 POST HTTP 202，得到 analysis `3bb20a9a794d4104b13fc1fe5f581c66`、job `1655a96b6f054c66931260204caaefa4`、version `2`；终态为 `completed`，模型 `qwen3.8:27b`，summary 非空（627 字符），source version 与门禁一致。`source_refs` 仅包含目标 document、chunker `v1`；5 个 citations 的 document ID 也全部为目标 document。

同一 JSON 同 key 重放 HTTP 202，复用同一 analysis/job/version/source_version，未创建第二个分析版本。

### 全文会话与 QA/SSE：PASS

全文 conversation POST HTTP 200，conversation `cc9f02f3d8184943bee35b4a23aa9481`，`created=true`、`evidence_level=full`、source version 与全文分析一致，context 的 document ID 精确为目标文档。相同 key 重放 HTTP 200、`created=false`、conversation ID/source version 不变。

通过既有 `/api/conversations/{conversation_id}/messages` 发送一次全文事实问题，HTTP 200、`text/event-stream`。脱敏事件统计为 718 个事件，seq 严格 `1..718`：meta 1、progress 7、token 708、sources 1、done 1；done seq 718、status `completed`。sources seq 717 含 5 个来源，document ID 全部为目标 document。随后 GET messages HTTP 200，user/assistant 均 `completed`，assistant 非空（1473 字符）。报告不保存 prompt 全文、token、回答正文或 hidden reasoning。

### 图谱不变量：PASS

全文分析和会话前后只读 graph 均为 revision `17`、status `partial`、21 nodes、18 edges；GAT 节点位置 `(120.0, 80.0)`、目标 group ID `8c8f20f7a4c04e0e92f9cdd78fc01ce7` 保持不变。groups GET HTTP 200，仍为 1 个组；布局/分组哈希前后均为 `e88b7d51b1753bb9114c2b90f927fd140d66d726499fe32408119610d58bb3e1`。

### 本轮裁决

**PASS（Task05 backend API 全文链路）。** 新候选真实通过全文来源门禁、全文分析、分析幂等、全文会话幂等、单文档引用和全文 QA/SSE；既有摘要 version 1 保留，图谱结构/布局/分组未被分析链路改写。此前失败 run 未删除或覆盖。
