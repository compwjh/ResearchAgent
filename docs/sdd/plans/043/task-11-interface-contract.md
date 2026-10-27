# Task11 接口与持久化合同

状态：已确认（独立需求／技术GO，用户要求继续）；本合同不是实现或验收证据。
关联：[Task11](task-11-paper-expansion.md)；继承Spec043已确认的所有者、真实关系、50/500/20/200及后台摘要边界。

## 1. 版本和持久模型

- 地图SQLite从当前v7增量至v8：`literature_map_previews`增加`preview_revision INTEGER NOT NULL DEFAULT 1`和`pagination_json TEXT NULL`。不改稳定ID/旧preview候选与状态，不重建表。旧preview的pagination为null，继续原v1 apply；新分页命令只用于显式启用分页的references/citations。旧预览不支持续页时明确提示重新获取，由用户决定，不由GET自动抓取。
- graph/node及默认资源包仍为`literature-map-v1`，导出保持当前v2；preview增加可选字段，不给整张图换版本。
- `pagination_json`版本1：`page_size=50,max_candidates=500,next_cursor,loaded_count,total=null,has_more=null,limit_reached=false,state,failed_cursor,last_error,page_job_id,seed_identity_key`。state为idle/loading/ready/failed/exhausted/capped；has_more来源未知时为null而非false，total仅使用来源实际返回值。cursor只在服务端保存，API不接受客户端offset/URL。
- 每次preview持久状态改变都递增preview_revision，包括分页排队、成功追加或失败。写入候选快照与下一cursor必须同事务。候选ID沿现有稳定身份哈希；同身份重复不重复增加loaded_count，但来源游标仍按实际响应推进。
- 页作业复用`literature_map_jobs`，operation=`preview_page`；批次作业operation=`expand_batch`，均沿现有执行器、lease/worker_token和事件。它们不是新的执行框架；不覆盖地图主建图状态投影，地图有节点不因补摘要重新显示Queued/0%。
- expand_batch复用cursor_json版本1：`seed_node_id,preview_ids,new_node_ids,items`。items最多20，以node_id为键，记录metadata状态/尝试/来源缓存键/安全错误及analysis_id、source_version。counts持久记录各阶段数。批次与命令结果沿现有mutation idempotencies关联，不另建批次/缓存数据库。
- v8 DDL、默认值、版本marker在同一事务；失败整段回滚，重复启动幂等。旧preview/图/颜色/布局/知识库关联不变。删除地图沿现有清理顺序删除新增作业，不删共享缓存和PDF。

## 2. 公共接口

以下路径前缀均为`/api/literature-maps/{map_id}`，owner从服务端取得。JSON未知字段拒绝，revision为非bool整数，幂等键非空且有既有长度上限。

### 创建单方向分页预览

`POST /previews`请求示例：

```json
{"kind":"references","node_id":"seed-id","pagination":{"version":1,"page_size":50,"max_candidates":500},"idempotency_key":"create-ref-key"}
```

pagination三个值仅允许冻结值；不传时保留旧合同。统一入口为同seed分别建立references/citations两个预览。请求参数哈希含owner/map/seed/kind/pagination/query；同键同参数返回同preview/job，不重新联网，同键异参409。成功202返回既有preview/job包，并在preview中加入preview_revision和pagination；初始状态loading，候选为空不代表来源空结果。

### 续页与失败页重试

`POST /previews/{preview_id}/load-more`：

```json
{"expected_preview_revision":3,"retry_failed":false,"idempotency_key":"next-page-key"}
```

- retry_failed为严格bool。false只取已保存next_cursor；true只允许failed状态下重取failed_cursor。同一preview最多一个页作业在途，不同方向独立。
- 在单事务中先验owner/map/seed有效、分页版本、preview revision及非busy，再把cursor绑定到新preview_page作业、登记幂等结果并置loading。后台在事务外访问来源，返回202含preview_id/job_id/preview_revision；幂等重放优先于旧revision检查，回放原命令结果，不重复推进。
- 页成功：核对worker token及目标cursor，按身份去重追加，单事务保存候选/next_cursor/数量及ready或exhausted/capped，revision加1。空页但仍有next不冒充穷尽；游标不推进或循环为来源响应错误，不自动无穷取页。
- client耗尽已有有限退避后429或来源失败：同事务保存failed_cursor和安全错误、state=failed，保留此前候选及next_cursor。手动retry只补此页。500去重候选或无后续游标时，继续请求分别409 MAP_PREVIEW_LIMIT_REACHED/MAP_PREVIEW_EXHAUSTED，不创建网络任务。
- 两方向共用现有client每秒一次限流及最多一次、Retry-After/指数延迟30秒封顶重试；不增设外层无限重试。候选仅保存成功、可解析且身份可信的行；失败绝不变成“成功0篇”。

### 跨预览重核（409恢复）

`POST /previews/revalidate`：

```json
{"expected_revision":42,"idempotency_key":"revalidate-key","selections":[{"preview_id":"ref-preview","expected_preview_revision":4,"selected_candidate_ids":["a"]},{"preview_id":"cite-preview","expected_preview_revision":6,"selected_candidate_ids":["b"]}]}
```

只读来源快照、不联网；这是一条更新预览基准的显式命令，不写地图节点/边。单事务核对当前map revision、两preview版本/owner/map/seed/kind及候选归属、身份、删除状态和容量；重新标记候选的已有/移除状态，更新所涉preview的base_revision与preview_revision，并返回当前revision、两preview新版本、有效/无效选项与变化摘要。失效选项不能静默丢掉并提交；用户需处理后再次明确确认。重核沿既有mutation idempotencies保存结果：同键同参数优先重放，异参409；输入版本过期409并给出可读最新版本，不自动循环。

### 跨方向一次原子确认

`POST /previews/batch-apply`：

```json
{"expected_revision":42,"idempotency_key":"apply-batch-key","selections":[{"preview_id":"ref-preview","expected_preview_revision":5,"selected_candidate_ids":["a"]},{"preview_id":"cite-preview","expected_preview_revision":7,"selected_candidate_ids":["b"]}]}
```

- selections长度1或2，方向不能重复，必须同owner/map/活动seed；每组最多20个唯一candidate ID，跨方向按既有确定身份计算最多20新增/整图200。已有项不可冒充新增，墓碑不自动恢复，自环拒绝；缺失/外preview/身份不确定的选择拒绝，不能仅根据标题合并。
- 非busy分页快照才能确认；两个preview的base_revision必须等于expected_revision，preview revision须逐一匹配。冲突返回409，客户端保留选择，先GET当前图/preview，再显式revalidate，展示变化后由用户重新确认，禁止仅换expected_revision绕过检查。
- 单SQLite事务依序：校验map owner→查询幂等结果→检查请求参数哈希、版本、种子与全部选择→算去重及容量→插入节点/真实边→map revision一次递增→创建expand_batch持久outbox与新节点步骤→为已有摘要的新节点原子注册既有摘要队列项→更新preview中已加入标记及基准/版本→保存固定命令结果和事件。任何一步失败全部回滚。
- 没有新增的合法幂等重放不重复边/作业/分析；新键但全部已存在返回added_count=0及已有数，不制造新分析或布局变动。所选新论文若两侧都有则一个节点、按两侧来源证据保留两种真实方向。
- 不把任意一条公开apply嵌入另一条公开apply；提取共享的事务级校验/写入helper，由一次连接/事务负责。网络、embedding和模型调用全部在提交后。
- 成功202：`schema_version,map_id,revision,added_count,existing_count,node_ids,batch_job_id,queue_job_id,previews[{preview_id,preview_revision,base_revision}]`。重放返回同命令结果，另以GET读最新进度。同键异参409，不因重试时map已升revision而丢失已提交结果。
- 成功后preview仍可继续选其他未加入候选；所涉preview已加入标记和版本更新，用户下次确认仍遵循当前revision，不要求重新抓取来源。

### 批次状态与修复

GET现有`/jobs/{batch_job_id}`扩展投影为批次node IDs、分阶段counts和安全failed_units；仍纯读。复用既有`/jobs/{job_id}/retry`用于expand_batch，新增严格可选`node_ids`、`steps=["metadata"]`及幂等键以限定本批失败/无摘要节点的手动元数据重试；旧空请求语义保持。模型失败继续复用analysis-queue按analysis_ids重试。暂停/继续仍为地图级，暂停后不调度本批后续元数据/模型步骤，在途单次请求可结束，不能声称已中断模型。

缺摘要的稍后重查只允许用户显式对skipped_no_abstract节点发起一轮有界请求，并绕过该节点已知无摘要缓存；不定时轮询、不自动清掉失败证据。明确非可重试状态给原因，不无条件新建批次。

## 3. 后台补摘要与分析合同

- 新增节点已有非空摘要：事务中只把这些新增node candidates传给既有store队列事务helper；不得调用遍历全图的service.ensure_analysis_queue补入旧节点。复用当前分析模型和source_version算法，不改历史分析键。
- 无摘要：批次items先持久metadata_pending，后台使用现有SemanticScholarGraphClient.batch及其固定字段/既有确定身份匹配规则，最多20个新增节点一轮。使用client.batch及现有元数据解析/确定身份匹配；不把S2 ID伪造为catalog ID，也不另建来源客户端。复用地图store的request_cache_key/get_request_cache/put_request_cache持久缓存，operation为metadata，key含规范化外部ID、字段集及缓存版本，TTL沿现有REQUEST_CACHE_TTL_SECONDS；不宣称client的内存_batch_cache可跨重启。
- 从已知S2/DOI/arXiv确定身份查找；只有确定匹配才合并。**写入白名单仅为缺失abstract与其来源证明**，不改title/external_ids/既有摘要/人工内容、布局、颜色、group、document ID或下载状态。引用数等字段不顺手更新。
- 元数据成功且有摘要：在同一写事务CAS确认该节点仍活动且abstract仍缺失→填abstract和来源→用既有_hash_source计算source_version→注册该节点现有摘要队列/分析ID→更新batch item为analysis_queued。已有其他合法写入则采用其当前摘要，不覆盖，不制造第二次分析。
- 来源成功但无摘要为skipped_no_abstract；请求429/错误为metadata_failed并保存retryable错误，身份无法确定为identity_unresolved，不用标题分析。两者不能混记。
- 本链仅在摘要从缺失到有效时请求分析；同内容/同模型已有completed版本直接关联，不再调用模型。缓存命中与重复确认/重开/重启不重复分析。只补其它非摘要元数据不能触发分析，亦不得变更旧source hash公式。
- extend现有队列事务helper接当前DB连接，避免嵌套事务。已存在全图旧工作可继续，但Task11不重新ensure旧节点；地图级暂停标记原样保留。
- outbox使用现有worker lease/CAS，启动恢复queued及过期running步骤，不清空成功步骤；模型仍交既有MapAnalysis worker。分析完成/失败的同一事务更新关联batch的item/count/status；恢复校正关联状态，不令batch长期Queued/0%。移除节点则安全跳过，不复活。

## 4. 错误与验收冻结点

统一沿现有`{"detail":{"code":"...","message":"中文可行动提示"}}`模式；404不泄露owner，非法JSON为422，非法选择/容量为结构化400。409码冻结为MAP_CONFLICT、MAP_PREVIEW_VERSION_CONFLICT、MAP_PREVIEW_BUSY、MAP_PREVIEW_REVALIDATION_REQUIRED、MAP_SEED_UNAVAILABLE、MAP_IDEMPOTENCY_CONFLICT、MAP_PREVIEW_LIMIT_REACHED、MAP_PREVIEW_EXHAUSTED。来源429表现为页/元数据持久失败及原provider安全码，不把create/load-more的202当来源已成功。

覆盖：旧v7迁移及回滚/幂等；同键同参/异参；两个方向并发分页、游标循环与重复页、500上限；首次/续页429保成功页，GET不联网；双方向原子回滚及40 raw IDs/20 unique身份；冲突GET→revalidate→用户确认；跨owner/map/seed与墓碑；提交后崩溃/迟到worker；旧队列不被全图ensure；补摘要白名单、确定身份、显式无摘要重查、同摘要不重跑；暂停/恢复及批次终态一致。此处没有运行任何测试或来源请求。

补充幂等命名：公开命令键保存在既有mutation表，内部MapJob键使用带operation/preview或batch身份的命名空间与尝试代数，不能把用户原键与保留的analysis_queue键混用。页重试新代数仍受同preview单在途约束，旧成功页不重复取。空选择、重复方向/候选、越界数量分别沿INVALID_PREVIEW_CANDIDATE、PREVIEW_BATCH_LIMIT、MAP_NODE_LIMIT等既有结构化400，不把无效输入当空成功。

## 5. 新操作的worker生命周期（技术复审补充）

**现状与实现增量分开**：普通`store.claim_job`并没有analysis专用的token/lease语义，不能直接用于新操作。Task11须增加事务级`claim_auxiliary_job`和token约束的finish/失败提交helper，复用现有jobs表字段、事务及lease维护机制的模式；不是声称现有通用claim已经安全。

### Claim与写入资格

- 新helper只允许`preview_page`/`expand_batch`，先校验map owner及操作类型，再在一事务内仅对queued状态生成不可预测worker_token、UTC lease_expires_at=now+300秒、attempts+1，CAS切到running。有效running不能被第二worker认领，过期running须先走reaper回收，不能无条件覆盖token。
- batch只认领仍有metadata_pending/可补步骤的工作；已有摘要的分析注册在确认事务完成，分析请求继续由现有`claim_analysis_job(operation=analysis)`负责，不能让auxiliary handler执行模型。
- page成功/失败、候选追加/cursor推进、metadata写入/队列注册及batch步骤推进的**同一数据库事务**必须检查job_id/map/owner/operation、running、当前worker_token及未过期lease。任一条件失败则丢弃该worker的领域提交，整段rollback，不能先写preview或paper再检查token。
- token不会进入公共JSON或浏览器草稿。失效worker不得改变map/preview/paper/queue/batch状态，也不得注册新分析；真实公开来源响应可以沿已有校验进入共享缓存，但缓存不代表领域步骤已提交。

### 回收、路由和重启

- 使用现有维护循环增加两新operation的lease扫描；不要依赖当前普通recover后统一调用run_job的分派。显式路由：preview_page→run_preview_page，expand_batch中metadata待执行→run_expansion_batch；既有操作保留原handler，未知operation明确失败，禁止落入通用建图run_job。
- queued作业按类型重新提交。running且lease有效不双重启动；lease过期时事务撤销旧token，保留成功步骤、cursor及outbox，设置queued（地图分析暂停时batch设置paused待恢复）。每一自动接管代数重新claim发新token，旧worker迟到结果因token/CAS失败不能提交。
- 自动lease接管最多3次（本次命令代数），超过置可行动失败MAP_JOB_LEASE_EXHAUSTED，用户显式重试才能启用新代数。provider429/明确来源失败在client有限重试后直接终结该页为failed，reaper不能把它当lease中断再次自动联网。
- 页HTTP与元数据batch调用只在事务外，调用前后检查资格；不持SQLite事务等待网络。未知在途请求在崩溃后可能重取，不能承诺外部HTTP严格exactly-once；用来源缓存和最终领域CAS保证成功页不重复追加、cursor不双跳、分析登记不重复。
- 元数据准备结束后batch释放worker lease，状态进入active/analysis_wait（或paused），只通过已登记analysis_id观察现有分析worker；该状态不交给通用run_job，也不重做metadata。分析finish事务更新关联batch的item/count和终态；启动恢复对这些等待批次做只读已有分析状态后的事务性对齐，不重新请求模型。

### 暂停、恢复和终态

- preview_page与候选加载不受地图“暂停分析”影响；expand_batch在claim及每个后续metadata/分析调度边界读取现有地图分析暂停标记。暂停时不启动下一步骤，队列的暂停状态不能被ensure重置。
- 已在途单次请求允许结束：若token/lease仍有效，可保存元数据及待执行队列项，但不调度模型，batch最终进入paused并释放lease；若其lease已经失效，仅保留可验证公共缓存，不能写领域状态。暂停期间过期作业回收为paused，不自动认领。
- resume沿现有队列恢复入口恢复这些paused batch的未完成步骤；同一有效在途claim未结束时不能另认领。只恢复待补步骤，不重复完成/缺摘要终态；缺摘要重查仍须明确选择metadata重试，不由resume自动触发。
- analysis_wait不需要持有长lease；完成/失败均更新同一batch持久投影。map/node已删除或节点被移出时相应步骤终止或skipped_removed，不复活；旧worker提交必须再校验这些条件。
- 手动metadata重试在一事务验证node_ids属于本batch且确为metadata_failed/skipped_no_abstract、命令幂等，递增该命令代数、清除旧token并只重置所选步骤；已完成分析不重置。重复相同重试键不再重置attempt或再次联网。

验收须新增：双worker同时claim只成功一个；lease过期后旧token finish全回滚；page/metadata handler按operation恢复、不落入run_job；暂停前/中/后不重复调度；429失败不被reaper无限重放；批次analysis_wait恢复只对齐记录；提交后崩溃通过outbox继续、成功步骤不重做。以上属于本修订必须实现的增量，当前没有代码/测试成功声明。
