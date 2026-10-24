# Task05 后端复用合同核对

> 核对时间：2026-10-20（只读）
> 范围：模型调用、会话、项目记忆、受限 RAG、KB 索引就绪门禁。
> 本文不是实现报告：本轮未调用模型/provider，未读取论文原文，未写数据库，未修改业务代码。

## 结论摘要

现有模型和会话链可以复用，但当前地图领域没有 `MapAnalysis` 持久化，也没有 map/node 到 conversation 的绑定。不能把 `MapPaper.provenance` 或 `document_id` 当作分析结果/会话绑定。

最小安全桥接必须由服务端依据冻结的 map、node、project 和 document 身份组装上下文：

1. 分析只由点击入口创建，写入独立的 `MapAnalysis` 结果引用；不在读节点时调用模型。
2. 全文级只在 canonical document、owner/project allowlist、索引代际和目标 chunker manifest 均可证明时使用；否则只能使用已有摘要，标题缺摘要不得生成论文内容。
3. RAG 必须把服务端已核验的单个 `document_id` 传给 `hybrid_search`，不能直接复用当前会话默认的“项目全部文档”范围。
4. 会话可复用 `MemoryRepository` 的原子写入和 `run_chat`，但需新增窄的 map/node 绑定接缝；现有 `Conversation` 没有 map/node 字段，现有公开 route 也没有节点文档过滤参数。

## 已核实的可复用接口

### 模型/消息装配

- `backend/app/chat/application/chat_runner.py`
  - `build_role_aware_messages(question, *, system_rule=None, advisory=None, history=None) -> list[dict[str, str]]`：统一加入平台 system、受控 advisory、历史 role 消息和当前问题。
  - `run_chat(question, model, *, route=None, prompt=None, think=True, reasoning_effort=None, messages=None, system_messages=None) -> ChatRun`：沿用既有 Ollama/LangChain/direct 路由，不新建 model client。返回的 `ChatRun.events` 在迭代中产出事件，结束后 `ChatRun.result` 为既有 `OllamaChatResult`（或相应 provider 结果）。
- `backend/app/chat/application/conversation_service.py`
  - `compose_chat_messages(question, history, memories, project_instructions=None, summaries=None, *, rag_hits=None, system_rule=None, segments=None, project_id=None, tool_outputs=None, recall_hits=None) -> list[dict[str, str]]`。
  - RAG 证据应通过 `rag_hits` 注入，不能自行拼第二份 chat prompt；该函数会将 RAG 作为“仅供参考”的 advisory。
- `backend/app/api/routes_conversations.py::_message_stream(...)`
  - 现有顺序是 owner-scoped memory/history → project instructions → project document RAG → `compose_chat_messages` → `run_chat` → SSE token/source/done。
  - 当前 `POST /api/conversations/messages` 和 `POST /api/conversations/{conversation_id}/messages` 返回 SSE，不是可直接当作地图分析 JSON job 的接口。生成过程中会持久化消息、processing steps 和安全事件；不得把 reasoning 内容写入地图分析结果。

### 会话和项目

- `backend/app/memory/repository.py::create_conversation(owner_id, project_id=None, title="", memory_history_policy="from_binding", reasoning_effort=None) -> Conversation`
  - 校验 project 属于 owner 且 active；`project_id=None` 表示未绑定项目。
- `create_conversation_messages(owner_id, content, project_id, model, mode, reasoning_effort=None, *, update_preference=False) -> tuple[Conversation, Message, Message]`
  - 新会话、首条 user message、assistant pending placeholder 一个事务完成。
- `create_message_pair(conversation_id, owner_id, content, *, model=None, mode=None, reasoning_effort=None, update_preference=False) -> tuple[Conversation, Message, Message]`
  - 复用现有会话时的原子 user/assistant 写入；owner 不匹配或会话已删会失败。
- `get_conversation(conversation_id, owner_id) -> Conversation | None`、`get_project(project_id, owner_id) -> Project | None`、`list_context_messages(...) -> list[Message]` 是现有 owner 门禁和历史读取入口。
- `routes_conversations.py` 的 `GET /api/conversations/{id}` 投影为 `conversation_id/owner_id/project_id/title/status/...`；没有 map/node 投影。公开消息入口的模型校验和 reasoning capability 解析也应继续复用 `_validate_model` / `_resolve_request_effort`，不要在地图模块复制。

### RAG、文档 allowlist 与索引就绪

- `backend/app/knowledge_base/application.py::list_documents_for_project(project_id, *, owner_id=None) -> list[dict]`：只返回 `knowledge-document-v1` 且 association owner/project 匹配的 canonical records。`project_id=None` 是 unbound/shared pool，不能被误当任意项目文档。
- `backend/app/knowledge_base/infrastructure/retrieve.py::hybrid_search(question, *, top_k=None, candidate_pool=None, chunker=None, include_citations=None, paper_id=None, document_ids=None, client=None) -> list[Hit]`。
  - `Hit` 字段为 `paper_id/file_name/page/chunk_index/text/score/chunker/page_end/section/is_citation/start_line/end_line`。
  - 地图全文问答应使用 `document_ids=[已核验的 node.document_id]`，必要时明确 `chunker`；不能只传项目 ID 或用 S2/catalog ID 冒充 document ID。
- `backend/app/knowledge_base/infrastructure/prompts.py::citation_payloads(hits) -> list[dict]` 可复用既有 citation shape（`document_id`, `chunk_id`, 页码、score、source_url 等）。地图分析只保存受控 result/source ref，不应在本核对阶段读取或复制 `Hit.text`。
- `backend/app/api/routes_kb.py::_canonical_document(document_id)` 只证明 canonical record 存在；`_canonical_source_is_indexable(document_id)` 只证明存在 source hash，二者都不等于“全文索引可用”。
- `routes_kb.py::_require_generation(...)` 使用 `FinalizeBundleStore.require_generation()` 做全局代际门禁；`GET /api/kb/documents/{document_id}/inspection` 还会读取 `InspectionManifestStore`，且 manifest 缺失时可能排队 reindex。因此地图分析的只读 readiness 检查不能调用该 GET 作为探测，否则会在读操作中产生 reindex 副作用；应由后端窄适配器直接执行只读 generation + manifest 检查，并检查目标 document/chunker 的状态。
- `routes_kb.py::kb_ask` 的默认 RAG 范围是项目全部文档。它可作为事件/citation 形状参考，不能直接作为 map-node 问答入口。

### 组合根

- `backend/app/platform/bootstrap.py` 的 `register_provider/get_provider/override_provider` 是唯一通用 provider 注册/测试替换点。
- `backend/app/api/routes_conversations.py` 注册 `memory_repository`；`backend/app/api/common.py` 注册 `paper_import_port`、`paper_batch_service` 等业务 provider。Task05 不应新建 provider client；若需要 map 专用 bridge，应在应用组合根注册一个窄接口，测试用 `override_provider` 替换。

## GAT 现有文档的证据绑定

本次只使用既有验收材料提供的稳定 ID，没有读取论文原文或调用 KB/model：

```json
{
  "document_id": "55afc3b8f01445429462fe78ed0d4c98",
  "schema_version": "knowledge-document-v1",
  "evidence_level": "full"
}
```

上面的 `evidence_level=full` 只能在实现时重新通过 canonical record、owner/project association、索引 generation 和目标 manifest 后写入；它不是本轮重新探测的结论。当前代码没有既成的 `source_version` 字段或编码。主会话需冻结一个由 canonical document 身份、来源哈希和已提交 generation/manifest 版本组成的不可变值；不得仅用论文标题、S2 ID、catalog ID 或地图 `source_url` 生成它。若只存在节点摘要，结果应标为摘要级；标题且无摘要时返回可行动的证据不足状态，不调用模型生成总结。

## 必须由主会话冻结的地图窄合同

### MapAnalysis

当前 `backend/app/literature_maps/infrastructure/store.py` 只有 map/node/edge/job/preview 等表，`MapPaper` 只有 `document_id/download_status/provenance` 等字段，没有 analysis 表或 result ref。Task05 实现应新增独立 analysis 持久化（不覆盖 provenance），并明确：

- 主键及唯一性：`owner_id + map_id + node_id + source_version + evidence_level` 是否允许并存多个版本；旧摘要结果不能被全文结果静默覆盖。
- 状态和失败 shape：沿用现有 queued/running/completed/failed 语义还是新枚举；错误只能是稳定、可行动 code，不暴露 provider 异常、prompt、URL 或 key。
- `result_ref` 指向受控结果/来源投影，而不是把全文或 hidden reasoning 塞进节点 JSON。
- 分析任务应复用已有持久作业/恢复模式，但当前 map executor 没有已核实的 analysis operation；`MapJob.operation` 是文本列并不代表执行器已经支持分析。不能只新增一个字符串就宣称后台任务存在。

### Map/node conversation binding

现有 `Conversation` 只有 `project_id`，`literature_map_nodes` 没有 conversation 字段，且没有 map/node association 表。最小桥接应由服务端保存独立绑定（或等价窄 adapter），至少包含：`owner_id/map_id/node_id/conversation_id/project_id_at_bind`，并以 `(owner,map,node,project snapshot)` 做查找/幂等门禁。

- 创建前验证 map、node、owner 和当前 project；新会话使用 `create_conversation(owner_id, project_id=当前 map.project_id)`。
- 复用前用 `get_conversation(conversation_id, owner_id)` 再核对 project；跨 owner/project/node 不复用，已删除会话重新创建或返回固定冲突。
- 地图后来解绑不得修改旧会话的 `project_id_at_bind` 或历史结果。
- 现有 `POST /conversations/{id}/messages` 没有 node/document 参数，直接调用会把项目内全部文档纳入 RAG。需要一个服务端生成的 node-scoped retrieval context（或对 `_message_stream` 的内部参数化），客户端不能提交任意 `document_ids`。
- 两个现有 repository 各自事务，尚无“创建 conversation + 写 map binding”的跨库原子接口；实现前需冻结幂等/并发补偿策略，不能假设两步天然原子。

## 建议的最小调用顺序

1. API 解析 owner/map/node，读取冻结节点和项目快照；只接受服务端节点身份，不接受客户端 URL、document ID 或项目覆盖。
2. 分析入口创建独立 analysis/job 记录并立即返回句柄；没有全文时只生成/返回摘要级路径，不在详情读取时触发。
3. 全文路径只读校验 document allowlist、canonical record、索引 generation、目标 manifest；通过后调用 `hybrid_search(..., document_ids=[node.document_id])`。
4. 以 `compose_chat_messages(..., rag_hits=hits, project_id=bound_project_id)` 装配，再调用 `run_chat`；保留既有消息/事件持久化和安全 source projection，不复制聊天链路。
5. 结果写入独立 `MapAnalysis.result_ref`，带冻结的 `source_version/evidence_level`；状态更新和错误均走现有 owner/map/node 守卫。

## 当前明确缺口/阻塞

- 没有 `MapAnalysis` schema/store/service/route。
- 没有 map/node 到 conversation 的持久绑定；不能仅靠 conversation title 或消息内容查找。
- 现有会话 RAG 是项目全量文档范围，不能满足单节点证据隔离；需内部窄参数或独立 server-side context adapter。
- 没有已核实的 map analysis 异步 executor/恢复协议；现有 `MapJob` 不能仅凭 operation 字符串替代。
- `source_version`、`evidence_level` 枚举、analysis 错误码和 result ref schema 尚未在既有实现中冻结。

以上缺口需主会话先冻结公开/持久合同，再进入 backend-dev 实现；本轮不以调研文档代替代码、精准测试或真实 API 验收。
