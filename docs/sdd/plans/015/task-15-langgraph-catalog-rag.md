# 任务 15 — 实现 LangGraph、目录 RAG 与冻结结果

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)
> 依赖：任务 14；被依赖：任务 16、17；当前状态：`待执行`
> 主 Skill：`.agents/skills/usenix-paper-catalog-search/SKILL.md`（本任务只做目录、工作流和RAG）

## 一句话目标

用固定 LangGraph 工作流异步编排 USENIX/DBLP 增量同步、权威合并、独立目录向量化、研究方向召回和稳定结果冻结，并提供可轮询 API。

## 当前证据

- 项目依赖已包含 `langgraph`，现有 `backend/app/graphs/chat.py` 和 `backend/app/agents/article_agent.py` 可作为项目内用法参考，但不得复制无关聊天状态。
- 知识库已有 BGE-M3 dense+sparse、Qdrant collection 初始化、RRF 和可选 reranker；本任务只参数化复用。
- Task13 提供搜索任务/进度/事件/结果仓储，Task14 提供两个来源同步用例。
- 当前 `/api/papers/search` 是同步调用并返回会话候选；本任务建立新异步接口，旧接口在 Task16 前端切换后删除。

## 前置门禁

1. Task14 的四个固定样本、增量缓存、DBLP辅助和零PDF请求测试通过。
2. Qdrant discovery collection 名固定为 `paper-discovery-catalog`，与个人PDF collection不同。
3. Graph节点、状态和错误规则以Spec为准；运行时LLM不得动态生成工作流。
4. 网络、embedding、Qdrant、rerank不得在SQLite事务或全局锁内执行。

## 数据、配置与接口增量

- Graph输入：`search_id`；其余查询、会议和年份从持久化 `SearchJob` 读取，禁止信任后台线程传入的客户端URL。
- Graph状态只保存ID、节点状态、来源计数和受控错误；大量论文正文不在checkpoint中重复保存。
- 新建 `POST /api/papers/searches`、`GET /api/papers/searches/{id}`、`GET /api/papers/searches/{id}/results?page=N`。
- 创建接口返回HTTP 202；进度接口支持事件游标；结果页固定10条。
- 后台执行采用应用生命周期内受控执行器。进程重启时将 `running` 且无活跃执行的任务恢复为 `queued`，重新进入图；节点必须依靠SQLite幂等。

## 固定图与状态转换

```text
queued
  → validate_request
  → plan_fetch_units
  → [sync_usenix || sync_dblp]
  → merge_catalog_metadata
  → index_changed_catalog_papers
  → retrieve_and_rerank
  → freeze_search_results
  → completed | partial | failed
```

- 两个来源节点并行，但共享同一来源节流器与fetch-unit租约，不能通过图并行重复抓取。
- 任一节点重试时先检查已持久化结果；已完成副作用不得重复。
- `freeze_search_results` 在单一SQLite事务中写完整结果、总数和完成状态；写入前删除该任务尚未冻结的临时结果，冻结后拒绝更新。
- 有目录可见结果但任一来源失败或reranker降级为 `partial/degraded`；无可见结果且两个来源均失败才 `failed`。

## RAG 契约

- 复用既有 BGE-M3 实例与批处理，输入为规范化的 `title\nabstract\nkeywords`，单字段仍沿用既有文本上限。
- discovery collection 使用与现有实现兼容的 dense+sparse 向量配置，但独立 collection/payload；索引主键为稳定 `catalog_paper_id`。
- 只索引 `index_status=pending` 或 `metadata_hash` 与payload不一致的论文；成功条件更新为indexed，失败写事件并逐项隔离。
- Qdrant召回必须带会议和年份过滤；dense/sparse各取候选池后用既有RRF融合。
- reranker只对融合候选池运行；异常、非有限分数或不可用时保留RRF顺序并标记降级。
- 稳定排序固定为 `final_score desc, retrieval_score desc, year desc, normalized_title asc, catalog_paper_id asc`。

## 子任务拆分与子 Agent 分派

### A：参数化目录向量索引与召回

```text
你是 junior-dev，使用 qwen3.8:27b-mlx。实现Spec015 Task15的独立目录collection参数化切片。
只读取：已确认Spec015复用/RAG章节、Task15、Task13/14产物、backend/app/services/kb/embed.py、index.py、retrieve.py、store.py及对应KB测试。
允许修改：使用本地Ollama时最多2个代码文件、约150行，优先在既有KB基础设施中增加collection/payload/filter参数和对应测试；线上模型不受文件数上限。若需新建薄catalog adapter，必须调用现有embed/index/retrieve，不得复制算法。
禁止：修改个人KB默认行为；新建embedding客户端/RRF/reranker；混用collection；网络抓取；git add/commit/reset/stash/clean。
完成状态：同一BGE-M3基础设施可面向个人PDF与paper-discovery-catalog；目录payload支持会议/年份过滤；旧KB接口和测试不变。
必须验证：.venv/bin/python -m pytest -q tests/test_kb_services.py tests/test_kb_routes.py <新增目录RAG测试>；py_compile修改文件；git diff --check。
结果文档：docs/sdd/reviews/015-task15-catalog-rag.md；日志：.codebuddy/agent-logs/junior-dev-spec015-task15-rag-<timestamp>.md。
固定返回字段：状态/摘要、改动文件、测试命令/退出码/计数、产物、复用符号、决策、风险阻塞、主Agent动作、起止/耗时、可用时模型token工具统计。
```

### B：LangGraph工作流与恢复

```text
你是 junior-dev，使用 qwen3.8:27b-mlx。实现Spec015 Task15的固定LangGraph工作流切片。
只读取：已确认Spec015的图/schema/失败规则、Task15、Task13仓储、Task14同步用例、A后的目录RAG接口、现有graphs/chat.py和article_agent.py仅作风格参考。
允许修改：使用本地Ollama时最多2个代码文件、约150行，创建或修改paper discovery搜索应用/graph及对应测试；线上模型可按任务范围扩展。不得修改前端。
禁止：让LLM设计节点；在graph state存大段论文；事务内网络/embedding；直接写SQLite绕过store；新建来源缓存；git reset/stash/clean。
完成状态：固定节点/并行来源/事件/partial与failed/幂等重试/重启恢复均可用；每节点可注入fake以做确定性测试。
必须验证：.venv/bin/python -m pytest -q <graph测试> tests/test_paper_discovery_store.py tests/test_usenix_publication_source.py tests/test_dblp_publication_source.py；py_compile；git diff --check。
结果文档：docs/sdd/reviews/015-task15-langgraph.md；日志：.codebuddy/agent-logs/junior-dev-spec015-task15-graph-<timestamp>.md。
固定返回字段同Task要求；必须列出节点、状态写入点、幂等依据和失败矩阵。
```

### C：异步搜索API与冻结分页

```text
你是 junior-dev，使用 qwen3.8:27b-mlx。实现Spec015 Task15的异步搜索API切片。
只读取：已确认Spec015端点契约、Task15、B后的graph/application、backend/app/api/routes.py、schemas.py、tests/test_paper_discovery_api.py。
允许修改：使用本地Ollama时最多2个代码文件、约150行；若routes+schemas已占满，测试另行分派，禁止不写测试就宣称完成。线上模型可同时改对应测试。
禁止：删除旧接口（留到Task16前端切换后）；在请求中同步等待图完成；接受客户端URL/page_size；返回隐藏异常/凭证；git reset/stash/clean。
完成状态：POST返回202；GET状态返回两来源进度与事件游标；GET结果固定10条、任务未就绪/过期状态码正确；后台异常持久化为稳定错误。
必须验证：.venv/bin/python -m pytest -q tests/test_paper_discovery_api.py <新增graph/API测试>；py_compile routes/schemas；git diff --check。
结果文档：docs/sdd/reviews/015-task15-search-api.md；日志：.codebuddy/agent-logs/junior-dev-spec015-task15-api-<timestamp>.md。
固定返回字段同Task要求；信息不足必须阻塞。
```

## 子 Agent 必须返回的字段

结果状态和摘要、改动文件、测试命令/退出码/计数、报告和日志、实际复用符号、图节点与持久化点、错误/降级矩阵、风险阻塞、主Agent后续动作、起止时间/总耗时；可用时模型/token/工具统计。

## 主 Agent 回填校验

1. 读回Qdrant初始化与payload，证明个人KB和目录collection名称、数据形态完全隔离。
2. 注入fake source和fake Qdrant，断言两个来源并行开始、合并后才索引/召回、冻结后才完成。
3. 在每个节点后模拟中断并恢复，确认已完成fetch/index不重复副作用。
4. 构造USENIX失败+DBLP成功、DBLP失败+USENIX成功、两者失败+有缓存、两者失败+无缓存四类状态。
5. 冻结21条并重复分页，确认10/10/1、无重复、无跳项、排序不变。
6. 运行旧KB、下载、导入和批任务回归；扫描graph调用图确认无新基础设施。

## 实时监控命令

```bash
tail -f .codebuddy/agent-logs/junior-dev-spec015-task15-*.md
.venv/bin/python -m pytest -q tests/test_paper_discovery_api.py tests/test_kb_services.py
```

## 测试与验收标准

- POST不阻塞外部抓取，返回202和两条初始来源进度。
- 来源节点实际并行，SQLite租约仍保证同一unit只抓一次。
- 独立collection、metadata_hash增量索引、会议/年份过滤和RRF复用通过。
- reranker失败有degraded标志，排序稳定且不伪造分数。
- 任务重启恢复、节点幂等、事件游标和冻结分页通过。
- 旧个人KB行为、collection和测试零回归。

## 风险、停止条件与回滚

- 现有KB函数无法参数化且需要改变默认语义：停止并回到Spec评审，不复制实现。
- LangGraph版本API与锁文件不一致：记录实际版本与最小复现，停止猜测式实现。
- 后台执行器无法可靠恢复：任务保持queued并阻塞，不用内存状态伪装持久化。
- 回滚关闭新异步路由和graph入口，保留Task13/14目录数据；不得删除个人KB。

## 产出物

- 参数化的目录向量索引/召回适配。
- 固定LangGraph工作流、持久事件与恢复测试。
- 三个异步搜索接口及契约测试。
- 三份实现报告和日志。

## 执行结果

待执行后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-05 | 架构师（自身） | 创建Task15，固定图节点、状态、独立目录RAG、API与恢复契约；未执行代码 |
