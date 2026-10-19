# Task05 增量合同：证据分析与论文会话

2026-10-20，架构师纯文档落盘，基于已确认Spec043/Task05及 `reuse-contract.md`。沿用 `literature-map-v1`、owner和现有job/events；前后端按此精确交接，不能各猜返回结构。

## 证据与结果

- `evidence_level` 固定 `abstract` 或 `full`，请求必须明确选择，不静默降级。摘要缺失且只有标题时不调用模型；全文需canonical document、owner/项目allowlist、真实source hash、已提交generation和目标chunker manifest均通过只读检查。
- 当前文档默认chunker沿用既有v1；可用性不得仅凭node.download_status判断。使用已有 `hybrid_search(document_ids=[已核验document_id], chunker=已核验版本)`；绝不检索整个项目再事后过滤。
- 全文级标为“全文索引片段依据”，列真实引用片段；不能宣称通读整个PDF。没召回到有效片段时明确证据不足，不以空上下文生成全文总结。摘要级明确标记只基于摘要。
- `source_version` 为稳定hash：摘要含冻结title/abstract/外部身份；全文含document_id、canonical source hash、chunker、generation/manifest版本。来源更新后旧结果保留；只提示可重新分析，点击才生成新版本。
- 新增独立 `MapAnalysis` 及结果持久化，不把正文/隐藏推理塞入MapPaper.provenance。字段：analysis_id/map_id/node_id/version/status/evidence_level/source_version/model_id/job_id/result/error/created_at。version按节点递增；同幂等key返回同版本，不同显式请求可新增版本。
- `result` 仅在completed时存在：`{summary: string, citations: array, source_refs: array}`。只保存最终文本和受控来源引用，不保存prompt、全文语料或reasoning；动态文本安全渲染。空模型输出是失败，不填通用问候。

## API（前缀 `/api/literature-maps/{map_id}`）

1. `GET /nodes/{node_id}/analyses` → `{analyses: [...], source_status: {abstract_available, fulltext_ready, available_evidence_levels: [], source_versions: {abstract?, full?}, unavailable_reason?}}`。只读，不联网、不生成、不排队reindex。
2. `POST /nodes/{node_id}/analyses`，body `{evidence_level: "abstract"|"full", model?: string, idempotency_key: string}` →202 `{map_id,node_id,analysis_id,job_id,status,analysis,job}`。model缺省使用现有配置的对话模型；校验与provider沿用既有能力，不新增client。公开请求不接受document_id、URL、项目覆盖或source_version伪造。
3. `GET /analyses/{analysis_id}` → `{analysis,job}`。analysis含上述字段；失败为 `{error:{code,message,retryable}}`。沿用既有job停止/可重试机制和游标事件；分析作业不能改变地图图谱的partial/ready状态。
4. `POST /nodes/{node_id}/conversation`，body `{evidence_level: "abstract"|"full", idempotency_key: string}` →200 `{conversation_id,created,project_id,evidence_level,source_version,context:{map_id,node_id,title,document_id?}}`。创建或复用既有Conversation，前端跳转现有对话页面，不另造聊天框。

所有响应沿用schema_version包和固定错误结构。缺摘要409 `MAP_ABSTRACT_UNAVAILABLE`、全文不可用409 `MAP_FULLTEXT_UNAVAILABLE`、无有效片段409 `MAP_EVIDENCE_UNAVAILABLE`、来源变化409 `MAP_ANALYSIS_SOURCE_CHANGED`、节点已移除409 `MAP_NODE_REMOVED`；owner/map/node/doc不匹配失败关闭。模型失败使用受控固定码，不回原异常或凭据。

## 作业与复用边界

- 复用现有executor、持久job/checkpoint/claim/CAS及重启恢复；不能只新增operation字符串而没有真实worker。读取列表/详情不触发模型。每次分析仅一次逻辑生成，有限provider重试，不无限重跑。stop/delete后的晚回调不能写入结果。
- 摘要/全文先冻结证据，再用既有 `compose_chat_messages` / `run_chat`；复用现有系统规则和项目指令装配，system顺序不回退。全文检索门禁不得调用有副作用的inspection GET。
- 来源在生成期间改变时重新校验版本：不能把新证据输出记成旧source_version。结果不可覆盖旧版本；模型不可用不影响地图浏览。

## 会话桥接及跨库幂等

- 绑定至少保存owner/map/node/conversation/project_snapshot/evidence_level/source_version和冻结paper context。复用前再核对Conversation仍active、owner/project及证据版本相同；被删、归档或手工移项目的会话不静默复活。新会话继承地图当前项目；未绑定时project_id=None，不使用项目记忆。
- 地图后来解绑不改旧会话。会话上下文属于会话的共享证据快照，不随地图删除/节点移除被静默抹掉；不能依靠已删除MapPaper临时读取来恢复旧问答。删除会话时清理其绑定上下文，KB文档不删。
- 跨地图库/记忆库不假装天然原子：先在地图库事务中预留binding及服务端生成conversation_id，再经现有MemoryRepository完成幂等创建，最后确认binding。允许对create_conversation增加内部可选预留ID参数，不对公开API暴露、不新增第二套Conversation表。已存在ID必须核对owner/project；并发同scope复用reservation，崩溃重试继续同ID，不重复创建会话。
- 项目/节点在绑定期间变化时固定409并保留可恢复reservation，不返回错误项目会话、不删除用户消息。旧失效绑定可留历史，新有效binding使用新预留ID。
- 普通会话消息入口不增加客户端document_ids。通过服务端可信binding窄适配器为既有 `_message_stream` 提供paper context/单document检索过滤；无绑定的普通会话行为不变。每次问答核验owner、项目和索引就绪，失败不能偷偷退回项目全库检索。

## 前端与验证

- 右侧详情加载只读source_status/历史版本，按钮“基于摘要分析”“基于全文分析”“关于本篇提问”；缺证据说明下一步获取摘要/主动入库，不能生成伪内容。
- 显示依据、版本、生成中/失败及可操作提示。全文就绪仅提示重新分析，不自动调用模型或替换旧摘要结果/会话。切图/切节点/关闭后的旧请求不回写当前面板。
- API响应样例字段必须与fixture一致；真实验收分别运行摘要级、全文级一次分析并问答桥接，记录真实model/job/analysis/conversation/document/source_version。不以mock当真实模型输出。
- 定向测试包括证据隔离、缺摘要、无索引/代际不一致、跨owner/project/doc、来源变化、版本不覆盖、并发绑定/崩溃重试、未绑定项目记忆、地图解绑不改旧会话，以及普通会话/RAG受影响回归。测试按能力命名；不运行Spec全量，最终全量仍仅Task08。
- 后端只改地图分析模块及明确的MemoryRepository/会话内部桥接；前端只改地图详情与复用现有导航所需小接缝。禁止新聊天框架、自动下载、KB重建、整图综述或恢复Spec032全部工作。
