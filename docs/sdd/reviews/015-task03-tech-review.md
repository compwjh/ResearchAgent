# Spec 015 Task 03 会议配置与论文召回技术复核

- 评审者：当前协作 Agent
- 角色：独立开发主管（Tech Lead）
- 评审时间：2026-09-04 16:31 CST
- 评审范围：`docs/sdd/specs/015-security-paper-discovery.md`、`docs/sdd/plans/015/task-03-conference-registry-and-retrieval.md`、`docs/sdd/reviews/015-task02-baseline-review.md`、`docs/sdd/reviews/015-task02-tech-review.md`、`backend/app/domain/paper_discovery.py`、`backend/app/services/paper_discovery_store.py`、`backend/app/services/dblp_publication_source.py`、`backend/app/services/openalex_enricher.py`、`backend/app/services/paper_discovery_search.py`，以及四个对应测试文件
- 约束：只读复核；未修改业务代码、Spec014；未执行提交、推送、合并、reset、clean、stash

## 结论：打回

四组目标测试在补充项目根目录导入路径后为 `17 passed`，但测试未覆盖搜索会话之间的候选身份、用户查询透传、完整稳定排序和服务端会议配置边界。当前实现不能作为 Task03 的可复核完成态放行。

必须先修复两个 P0 问题：重复搜索同一论文会因全局 `candidate_id` 主键冲突而无法持久化；DBLP publication 请求完全没有透传用户查询，研究方向搜索实际退化为每个会议/年份的固定首屏召回。其余 P1 契约偏差也需在复审前收口，见下表。

## 逐项检查

### 1. 领域字段与 SQLite schema 映射

部分通过。`ConferenceSource` 的字段均能映射到 `conference_sources`，布尔值以 INTEGER 存储并在读取时转回 bool；`SearchSession` 的四字段均有列；`PaperCandidate` 的领域字段均有对应列，`normalized_title` 是存储派生列而非领域字段，authors 以 JSON 保存。这些映射与当前四组测试基本一致。

但有以下偏差：

- `paper_candidates.candidate_id` 是全局 `PRIMARY KEY`，而契约要求的是搜索会话范围内的 `(search_id,candidate_id)` 幂等约束。`PaperDiscoverySearchService` 又按 DOI/DBLP key/标题生成跨会话稳定 ID，因此第二次不同搜索保存同一 DOI 会失败。最小复现为首搜成功、二搜抛出 `sqlite3.IntegrityError: UNIQUE constraint failed: paper_candidates.candidate_id`。**P0，必须修复。**
- 存储 `normalized_title` 使用 `item.title.casefold().strip()`，与服务/DBLP 使用的去标点规范化不一致；`A-B` 与 `AB` 等等价标题不能依赖该索引正确去重。**P1。**
- DBLP 与搜索层的标题合并键只使用规范标题，未纳入 Task03 要求的年份和会议；同名论文跨年份会被错误合并，且当前 DBLP `deduplicate_publications` 也会跨年份折叠。**P1。**
- schema 只有候选到搜索会话的 FK，且过期清理直接删除 `search_sessions`，因 `ON DELETE CASCADE` 连带删除候选。Task03 当前没有导入表可以引用，但 Spec015 明确要求导入引用的候选快照不得随搜索 TTL 删除；进入 Task05 前必须改成保留导入快照/引用的 FK 图，不能让当前实现成为数据生命周期的默认语义。**P1（Task05 前置）。**

### 2. WAL、外键、事务与唯一约束

部分通过。每个连接设置 `journal_mode=WAL`、`foreign_keys=ON`、`busy_timeout=5000`；`save_conference`、`save_search`、`cleanup_expired_searches` 显式 `BEGIN`，上下文退出时提交，唯一约束和部分索引由 SQLite 执行，满足基础并发/事务意图。

仍需修复或补证：

- 初始化阶段在 `BEGIN` 后调用 `executescript`；Python sqlite3 的 `executescript` 会先提交待处理事务，使 DDL/版本初始化并非由该 `BEGIN` 覆盖的单一显式事务。应改为可验证的初始化/迁移事务，或明确 DDL 与 seed 的失败恢复策略。**P1。**
- `schema_meta` 没有单行约束/迁移流程；仅读取第一行版本，损坏或多版本行不会被稳定拒绝。**P1。**
- 唯一约束实现了 `(search_id,dblp_key)`、`(search_id,doi)` 非空索引和标题组合约束，但全局 candidate PK 与会话范围唯一约束冲突，实质上破坏了跨会话保存。**P0。**
- 当前测试只在单连接内验证 PRAGMA 和重复 DOI；没有两个连接/进程的同论文不同会话、写冲突回退、过期清理与 FK 保留行为测试。**P1。**

### 3. DBLP stream/year/venue/type 过滤与降级

部分通过。`filter_main_conference_records` 同时检查年份、stream key 前缀、`type` 含 conference、venue alias 严格相等，并拒绝包含 Workshop/Poster/Doctoral/SOUPS/Demo/Tutorial/CCSW/SPW 的记录；`DBLPPublicationSource` 对每个年份请求，支持显式 User-Agent、429/5xx 重试、指数退避、超时/网络/JSON 错误码，并在所有年份失败时给 `DBLP_UNAVAILABLE`。这符合 Task02 放行的“内置会议 + 主会白名单 + 降级”方向。

必须修复：

- `_request` 的 `q` 只有 `stream:{stream} year:{year}`，没有用户查询；`DBLPPublicationSource.search` 也没有 query 参数。最小复现 URL 为 `...?q=stream%3Aconf%2Fc+year%3A2024...`。因此同一会议/年份的研究方向查询不会改变 DBLP 召回结果，直接违反 Task03/Spec015 的方向检索目标。**P0，必须修复。**
- `_EXCLUDED` 将任意标题/venue/key/DOI 中的 `short` 作为排除词；合法主会论文如标题含 “Short ...” 会被误删。排除应绑定已验证的出版物类型、venue 别名或具体 workshop 标识，而不是全文关键词的宽匹配。**P1。**
- key 前缀和 venue/type 比对只在部分字段上做规范化；未知/异常 payload 形状被静默当作空结果，未产生可诊断 warning。**P1。**
- 年份请求按输入顺序执行，记录“first stable”依赖外部返回顺序；应在合并/排序前固定初排索引，确保相同候选集对年份顺序和重试顺序有稳定结果。**P1。**

### 4. OpenAlex DOI 优先和标题年份约束

条件通过。`OpenAlexEnricher` 对 DOI 先走 `filter=doi:`，命中时精确比较 normalized DOI；DOI miss 才走标题搜索，并在候选年份已知时要求 `publication_year` 相等，再按标题相似度和 OpenAlex ID 稳定选择。补全只写摘要/OA/PDF 等元数据，不造 rerank 分数；超时、429、5xx、非法 JSON 以结构化 warning 返回，并保留 DBLP 候选。对应测试覆盖 DOI 优先、标题年份不匹配、超时、限流/服务器错误/非法 payload，主路径成立。

需要修复：

- `locations` 从外部 JSON 取出后未验证为 list；若返回 dict/string，`row.get` 会抛异常，破坏“单源失败保留 DBLP 结果”的降级边界。**P1。**
- `enrich_by_doi`/`enrich_by_title` 只返回 metadata 或 None，丢弃 `OpenAlexWarning` 与 `error_code`；搜索服务使用 helper 时会把超时/限流/非法响应折叠成通用 `OPENALEX_NO_MATCH`，不符合稳定 warning 语义和可诊断性。**P1。**
- `pdf_access` 直接接受 `OpenAlexEnricher` 以外适配器的任意字符串（测试适配器写入 `open`），没有约束到 Spec015 的 `public/login_required/unavailable/unknown` 枚举。**P1。**

### 5. 搜索服务的 limit、输入验证、警告语义、网络调用与事务边界

部分通过。查询 trim 后校验 1–500 字符；年份非空、整数、最多 `max_years` 且不含当前未完成年份；limit 校验 1–100；外部 DBLP/OpenAlex 调用在 `save_search` 之前完成，网络调用不在存储事务内；DBLP 失败会保存空搜索会话，OpenAlex 异常保留 DBLP 候选并添加 warning。这些路径有四组测试覆盖。

必须修复：

- 服务只检查传入的 `ConferenceSource` 是 enabled 且字段非空，不从 `PaperDiscoveryStore` 解析已保存配置，也没有检查 source 是否为服务端配置对象。调用方可构造任意 enabled stream/alias，绕过“只使用受控会议配置”的边界。**P1。**
- 当前 Task03 只落地 domain/store/source/enricher/search，没有 `/api/papers/conferences` CRUD、Venue Search 路由或 `/api/papers/search` 路由；这至少意味着 Task03 文档中声明的接口尚未实现。Venue Search 仍按 Task02 blocked，不应宣称自定义会议已完成，但内置会议列表/停用与搜索入口仍需后续路由任务或明确移出本 Task 验收。**P1（范围/交付缺口）。**
- `max_years`、`max_limit` 为构造参数，未接入 Spec015 配置项；默认年份固定为 `current_year-5..current_year-1` 尚可，但 `PAPER_DISCOVERY_SEARCH_LIMIT`、`PAPER_DISCOVERY_MAX_SEARCH_LIMIT` 和候选池未由配置驱动。**P1。**
- `_enrich` 对真实 `OpenAlexEnricher` 主要依赖 helper；对返回 `OpenAlexEnrichmentResult` 的适配器会用 `vars()` 当 metadata，无法合并候选字段，且不会正确传播其 warnings/error_code。适配协议应固定为一种结果类型。**P1。**
- 结果排序是 `(-final_score, year is None, -year, candidate_id)`，未使用 Spec015 要求的 `(initial_rank asc, year desc, normalized_title asc, candidate_id asc)` 完整 tie-break；服务也没有保存 initial rank。**P1。**
- 全部召回失败目前返回“保存的空 session”与 error_code，而不是由上层稳定映射到“整体失败”的 HTTP/错误体；由于本轮没有路由，尚未能证明 Spec015 的状态码和错误体契约。**P1。**

### 6. candidate_id、去重与排名稳定性

不通过。候选 ID 的 hash 生成本身可复现，优先 DOI、其次 DBLP key、最后标题/年份/会议，且单次内重复记录会被合并；但全局主键冲突使跨搜索复用失败，属于核心持久化缺陷。另有：

- `_merge_candidate` 的 title key 没有 year/conference，造成跨年份同名论文误合并；DBLP dedup 同样只按 title。**P1。**
- DOI 规范化只移除 `https://doi.org/`，不处理 `http://doi.org/`、`doi:` 前缀和末尾句点；DBLP/OpenAlex 使用了不同规范化实现，容易漏去重。**P1。**
- 稳定排序没有 normalized title、初排序号；同分候选的结果依赖 candidate ID/hash 或年份，而非契约顺序。**P1。**
- `rank` 在替换更丰富候选时只保留旧 rank，但排序后又重新编号；该行为虽未立即错误，却没有测试元数据合并后的 tie-break/排名稳定性。**P1（测试补强）。**

### 7. 测试覆盖与 Spec015 契约偏差

当前四组测试共 17 条，覆盖了基础 schema PRAGMA/重复 DOI、DBLP 基本过滤与一次重试、OpenAlex DOI/title/year/error、搜索输入拒绝和基本降级；作为单元测试起点合格，但不足以证明 Task03 完成：

- 缺少同 DOI/DBLP key 在两个 search session 的保存与重搜测试（会复现 P0）。
- 缺少验证 query 进入 DBLP `q` 参数、不同 query 得到不同召回的测试（会复现 P0）。
- 缺少按规范标题+年份+会议去重、DOI 多种前缀、未知年份标题、跨年同名测试。
- 缺少完整 tie-break、输入年份重排后的稳定性、limit/candidate pool 上限和重复 warning 语义测试。
- 缺少 malformed `locations`、helper warning/error 传播和 `pdf_access` 枚举测试。
- 缺少服务端会议配置拒绝伪造 source、内置会议不可删除/只能停用、事务失败回滚及多连接并发测试。
- Task02 已明确 Venue Search/custom conference blocked；本评审不要求其在本轮实现或重新验证，亦不因用户跳过 Spec013/014 与 reranker 判断而追加前置条件。

## 必须修复项

### P0（复审前必须完成）

1. 将候选身份改为会话范围唯一（例如候选主键采用 `(search_id,candidate_id)`，或为持久层生成全局唯一存储键，同时保留契约要求的 `(search_id,candidate_id)` 唯一约束），并新增跨搜索重复论文保存测试。
2. 将用户 query 纳入 DBLP publication search 的服务端请求契约和参数编码；保留 stream/year/venue/type 过滤，新增测试确认 query 透传且不允许绕过配置注入任意 stream/URL。

### P1（复审前必须完成）

1. 统一 DOI/title 规范化；按“DOI、DBLP key、规范标题+年份+会议”实施去重，并让 SQLite 派生 normalized_title 与代码一致。
2. 固定并实现 Spec015 的稳定排序键，保存 initial rank/normalized title，保证年份输入顺序、重复请求和 metadata enrich 不改变同分结果。
3. 让搜索服务只接受 store 中已配置且 enabled 的会议；补齐本轮承诺的内置会议配置读/停用语义和 API 路由，或在 Task03 文档中明确把路由移到后续任务并降低当前验收范围。Venue Search/custom conference 保持 blocked。
4. 固定 OpenAlex 适配结果协议，防御 malformed `locations`，传播 warning/error_code，并将 `pdf_access` 限制为 Spec015 枚举。
5. 修复 schema 初始化/版本迁移与 TTL 生命周期：初始化事务可验证，schema_meta 损坏稳定失败；为后续导入候选快照保留策略建好 FK/删除规则，避免 TTL CASCADE 删除被导入引用的候选历史。
6. 将 Spec 配置项接入 search/store 的 limit、候选池和 TTL，而非仅使用构造器常量。
7. 补齐上述缺口测试，至少覆盖 P0 复现、并发/回滚、未知类型/误排除、跨年同名、排序稳定和 OpenAlex malformed/degraded paths。

## 放行条件

完成全部 P0/P1 修复，四组目标测试及新增回归通过；并由下一次 Tech Lead 复核确认：

- 不同搜索会话可安全保存相同论文而不发生主键冲突；
- DBLP 请求确实包含原始服务端校验后的 query，且外部失败按单源 warning/全部失败稳定映射；
- 过滤、去重、OpenAlex 补全与排序均符合 Task03/Spec015；
- TTL、schema/事务和服务端会议配置边界没有破坏后续导入任务。
