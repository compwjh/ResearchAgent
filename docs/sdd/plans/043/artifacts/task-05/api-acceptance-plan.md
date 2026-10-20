# Task05 真实 API 验证执行单

状态：待执行；不是成功报告。2026-10-20 架构师纯文档准备，不代替独立测试。

## 前置门禁

- 前后端 P0/P1 修复并独立复审通过，冻结本地候选提交后才部署。
- 当前 8000 实例因前端开发暂停；先按 deploy/README.md 启动单实例，验证 `/api/ready` 200。不得并发打开同一知识库目录。
- 已有地图 `0baabeae7268429c9f7e4de8098ae1d0`，GAT 节点 `21041260a5394f42891b020128fa60fa`，文档 `55afc3b8f01445429462fe78ed0d4c98` 可作为候选；必须先由当前 API 读回验证，不能把历史索引成功当本轮就绪证据。

## 主路径

1. GET 地图/节点和 `/nodes/{node_id}/analyses`：记录地图 revision、图谱状态、摘要与全文可用性和来源版本；只读不得触发模型或重建索引。
2. 显式 POST 摘要分析，保存脱敏请求、HTTP 状态、analysis/job ID；每隔合理时间 GET 作业结果，记录真正终态和非空 summary。确认 evidence_level=abstract，来源版本一致，无全文引用冒充。
3. 显式 POST 全文分析：仅在当前 source_status.fulltext_ready=true 时运行；记录真实文档、模型、来源版本和片段引用，输出必须非空，明确依据为全文索引片段。不改真实门禁来让案例通过。
4. 重发同一幂等请求：同 analysis/job/version，不额外生成；重新 GET 历史确认摘要结果仍保留。
5. 摘要与全文分别创建既有会话，记录 conversation ID/project/evidence/source_version。通过既有消息 API 各问一个依赖论文事实的问题，确认真实回答及摘要/全文证据隔离；全文引用只来自该文档。
6. GET 地图：分析作业不能把原图谱 partial 状态改为 ready，也不能更改节点布局或分组。
7. 浏览器：显式点击分析按钮，验证等待、非空结果、旧版本查看和现有会话导航；打开详情本身不能 POST 分析。

## 边界与失败处置

- 项目继承、无项目不使用项目记忆、跨所有者拒绝、归档/删除旧会话不复用、地图删除保留快照、并发预留和来源变化主要在隔离测试中复核；生产示例不删除用户已有地图或项目来测试。
- 如果真实 provider/索引/模型失败，落盘真实错误、等待时长和恢复方式，保持 Task05 进行中；禁止用 mock 或内部函数结果冒充成功 API。
- 本轮只跑受影响领域；全量回归留 Task08。

## 必须交付的证据

- `api-e2e.md` 与脱敏 JSON：候选提交、端口、请求/响应、实体 ID、时间、最终状态、非空产物、幂等重放和限制。
- `browser-e2e.md`：点击路径、可见状态、浏览器或自动化方式、实际截图路径（有则记录，不伪造）。
- 阶段结论通过才更新任务状态；未运行的项目保留“待执行”。

## 部署后可直接执行的 HTTP 细节（本轮仅准备，不执行）

### 候选实体核验

以下命令中的实体 ID 是当前候选，不能跳过读回检查：

```bash
BASE=http://127.0.0.1:8000
MAP_ID=0baabeae7268429c9f7e4de8098ae1d0
NODE_ID=21041260a5394f42891b020128fa60fa
DOC_ID=55afc3b8f01445429462fe78ed0d4c98

curl -sS -D /tmp/spec043-ready.headers "$BASE/api/ready" \
  -o /tmp/spec043-ready.json
curl -sS -D /tmp/spec043-map.headers "$BASE/api/literature-maps/$MAP_ID" \
  -o /tmp/spec043-map.json
curl -sS -D /tmp/spec043-node.headers "$BASE/api/literature-maps/$MAP_ID/nodes/$NODE_ID" \
  -o /tmp/spec043-node.json
curl -sS -D /tmp/spec043-graph.headers "$BASE/api/literature-maps/$MAP_ID/graph" \
  -o /tmp/spec043-graph-before.json
curl -sS -D /tmp/spec043-health.headers "$BASE/api/health" \
  -o /tmp/spec043-health.json
```

逐项记录 HTTP 状态、时间和 JSON；`/api/ready` 必须为 200（`ready` 可能因预热为 false，但不得把非 ready 当成功分析）。从 node 响应读回 `node.document_id`，只有它等于候选 `DOC_ID` 才继续全文案例；同时记录 map 的 `revision/status`、node 的 `title/abstract/document_id`。若地图、节点或文档不匹配，停止主路径并在 `api-e2e.md` 记录具体响应，不改写数据库或伪造 ID。

### 分析请求、轮询和幂等

先只读确认 source 状态，响应应为 `schema_version`、`analyses`、`source_status`，其中后者包含 `available_evidence_levels`、`source_versions.abstract/full`、`fulltext_ready`。保存 `/tmp/spec043-analyses-before.json`，不得因 GET 触发模型或索引。

摘要请求使用固定幂等键，省略 `model` 以沿用当前已配置模型（实际模型从 `/api/health.model` 记录）：

```bash
curl -sS -i -X POST "$BASE/api/literature-maps/$MAP_ID/nodes/$NODE_ID/analyses" \
  -H 'Content-Type: application/json' \
  --data '{"evidence_level":"abstract","idempotency_key":"spec043-task05-abstract-v1"}' \
  | tee /tmp/spec043-analysis-abstract-submit.txt
```

成功提交为 HTTP 202，响应为 `schema_version/map_id/node_id/analysis_id/job_id/status/analysis/job`；保存 `analysis_id`、`job_id`、初始 `version`、`source_version` 和 `evidence_level`。轮询：

```bash
curl -sS "$BASE/api/literature-maps/$MAP_ID/analyses/$ABSTRACT_ANALYSIS_ID" \
  | tee /tmp/spec043-analysis-abstract-final.json
```

`ABSTRACT_ANALYSIS_ID` 以实际提交响应为准。允许观察 `queued`/`running` 中间态，只有 GET 读到 `analysis.status=completed`、`job.status=completed`、非空 `analysis.result.summary` 才算成功；摘要结果的 `source_refs` 不得冒充全文片段。若为 `failed`，保存固定 `error.code/message/retryable`、轮询时间和恢复动作。

当 `source_status.fulltext_ready=true` 且 node 的 `document_id` 已核验为 `55afc3b8f01445429462fe78ed0d4c98` 时，再执行全文请求：

```bash
curl -sS -i -X POST "$BASE/api/literature-maps/$MAP_ID/nodes/$NODE_ID/analyses" \
  -H 'Content-Type: application/json' \
  --data '{"evidence_level":"full","idempotency_key":"spec043-task05-full-v1"}' \
  | tee /tmp/spec043-analysis-full-submit.txt
```

全文终态必须有非空 summary、`evidence_level=full`、提交时冻结的 `source_version`，以及只指向 `DOC_ID=55afc3b8f01445429462fe78ed0d4c98` 的受控 `source_refs/citations`；不得因全文不可用而静默降级摘要。`fulltext_ready=false` 时预期不提交模型，记录 409 `MAP_FULLTEXT_UNAVAILABLE`，不把它标为通过。

对摘要和全文分别原样重发同一 JSON（同一幂等键），并保存重放响应：应仍为 HTTP 202，且 `analysis_id/job_id/version/source_version` 与首次相同，不能增加新版本或第二个 job。可再 GET `/nodes/$NODE_ID/analyses`，确认历史结果仍保留。

### 会话桥接与既有消息 SSE

摘要会话：

```bash
curl -sS -i -X POST "$BASE/api/literature-maps/$MAP_ID/nodes/$NODE_ID/conversation" \
  -H 'Content-Type: application/json' \
  --data '{"evidence_level":"abstract","idempotency_key":"spec043-task05-conversation-abstract-v1"}' \
  | tee /tmp/spec043-conversation-abstract-submit.txt
```

响应为 `schema_version/conversation_id/created/project_id/evidence_level/source_version/context`；记录 `conversation_id`，并确认 context 含地图、节点、标题、冻结摘要和外部身份。原样重发后应为 HTTP 200、同一 `conversation_id/source_version`、`created=false`。全文会话只在全文就绪且文档 ID 已核验后，用不同幂等键执行同样步骤；全文会话的 `context.document_id` 必须为候选 `DOC_ID`。

通过既有消息接口发送问题（不要新造聊天接口）。模型值从 `/api/health.model` 复制，若本轮模型不可用，保留真实 SSE 失败证据：

```bash
curl --no-buffer -sS -N -X POST "$BASE/api/conversations/$ABSTRACT_CONVERSATION_ID/messages" \
  -H 'Content-Type: application/json' \
  --data '{"content":"请只依据这篇论文的摘要，说明研究问题、方法和主要结论。","model":"MODEL_FROM_HEALTH","mode":"normal","reasoning_effort":"off"}' \
  | tee /tmp/spec043-chat-abstract.sse

curl -sS "$BASE/api/conversations/$ABSTRACT_CONVERSATION_ID/messages" \
  | tee /tmp/spec043-chat-abstract-messages.json
```

实际执行时替换 `ABSTRACT_CONVERSATION_ID` 和 `MODEL_FROM_HEALTH`，不要把占位文本当作请求值。SSE 每个事件是 `data: {JSON}\n\n`：`meta` 应含 `message_id/event_seq/conversation_id/user_message_id/assistant_message_id/model/mode`，中间可有 `progress`、`reasoning_*`、`token`，全文有效召回后可有 `sources`（含 `sources/citations`），最后必须有 `done.status`。逐帧记录 `event_seq` 严格递增、最后 done 状态和非空 assistant 内容；同时 GET messages 记录 user/assistant 的最终 status/content/message_id。摘要会话应 `visible_document_ids=[]`，不得出现全文文档引用。

全文会话发送单独的事实问题，使用不同输出文件：

```bash
curl --no-buffer -sS -N -X POST "$BASE/api/conversations/$FULL_CONVERSATION_ID/messages" \
  -H 'Content-Type: application/json' \
  --data '{"content":"请根据该论文的全文索引片段概括研究方法，并明确引用依据。","model":"MODEL_FROM_HEALTH","mode":"normal","reasoning_effort":"off"}' \
  | tee /tmp/spec043-chat-full.sse

curl -sS "$BASE/api/conversations/$FULL_CONVERSATION_ID/messages" \
  | tee /tmp/spec043-chat-full-messages.json
```

全文 SSE 的 `sources/citations` 只能出现已核验 `DOC_ID`，并标明全文索引片段依据；没有有效召回时应记录 `MAP_EVIDENCE_UNAVAILABLE`/受控失败，不得退回项目全库检索。若重发同一会话创建请求，仍必须复用 conversation ID；消息问题本身不重复发送，除非验收需要单独记录第二轮。

### 收口记录格式

把上述脱敏 headers/body/响应、SSE 原文、事件序列、请求开始/结束时间、实际端口、候选提交/分支和最终实体状态汇总到 `docs/sdd/plans/043/artifacts/task-05/api-e2e.md`；`MODEL_FROM_HEALTH`、凭据、prompt 全文和内部 reasoning 不写入报告。`browser-e2e.md` 另记点击“基于摘要分析/基于全文分析/关于本篇提问”后的可见状态；HTTP 未执行或任一真实 provider/索引失败时，计划仍保持“待执行/进行中”，不得提前标记通过。
