# 文献地图 v1 接口与持久化合同

日期：2026-10-19；架构师：自身。状态：合同冻结；编码仍以Task02最终Go为前提。仅冻结已确认Spec043，不表示地图接口已实现。

## 模块与组合根

- 领域：`backend/app/literature_maps/domain/`；应用：`application/`；SQLite：`infrastructure/`。
- 路由：`backend/app/api/routes_literature_maps.py`，通过既有`routes.py`组合。运行时依赖由地图runtime组合，复用provider/bootstrap思想，不把论文目录common变为地图仓储。
- 默认库：`BASE_DIR/data/literature_maps/literature_maps.sqlite3`；允许仅服务端环境变量`LITERATURE_MAP_DB_PATH`覆盖及测试注入。WAL/事务/增量schema版本，不建个人KB Collection，不迁移/删除旧库。
- HTTP owner来自现有`OWNER_ID`服务端边界，不接受客户端owner覆盖；service/store方法显式传owner，跨owner按404处理。项目绑定先以现有MemoryRepository验证owner及存在性。
- 前端独立`frontend/literature-maps.js`和`frontend/literature-maps.css`，现有主导航入口`data-view="literature-maps"`、视图`literature-maps-view`；资源版本首版`v=1`。`showView`接入独立组件生命周期，离开取消前端轮询但不取消作业。

## 公共对象

所有响应带`schema_version="literature-map-v1"`。ID为服务端UUID hex；node ID在同图不因布局/metadata刷新变化。时间为UTC ISO8601。

- Map：`map_id, name, topic, owner_id, project_id, filters, requested_count, revision, status, view_settings, created_at, updated_at`。filters包含`year_start/year_end/source_ids/conference_ids`；空表示不限。status为`generating/ready/partial/failed/stopped`。
- Node：`node_id, map_id, external_ids, title, authors, year, venue, abstract, keywords, citation_count, source_url, provenance, catalog_paper_id, document_id, download_status, position, group_id`。external_ids键`semantic_scholar/doi/arxiv`；缺失字段为null或空数组，`authors`为字符串数组。`position={x,y}`可空。catalog/document为可空关联，不把S2 ID当catalog ID。
- Edge：`edge_id,map_id,kind,source_id,target_id,provenance,score,basis,model_version,content_hash`；端点为node_id。kind为`citation/similarity`，引用方向citing→cited；similarity端点字典序归一。引用score/basis/model可空。禁止自环。
- Job：`job_id,map_id,operation,status,step,counts,failed_units,created_at,updated_at`；status为`queued/running/completed/partial/failed/stopped`。create作业step为`discover/metadata/references/similarity/finished`；counts含`provider_count/accepted_count/node_count/citation_edge_count/similarity_edge_count`。
- Layer：`citation/similarity`各有`status=waiting/running/completed/partial/unavailable`和固定错误码。真实无引用/无高相似对属于completed且0边，不是unavailable。malformed/429是partial失败单元，不伪装0边成功。
- Event：`event_seq,map_id,job_id,type,status,step,counts,error_code,created_at`；payload只用固定安全字段，不含动态异常文本、凭据、provider headers、模型全文。
- Preview：`preview_id,map_id,base_revision,operation,status,candidates,diff`；candidate保留外部identity及`existing`状态；确认只允许预览范围内ID，不能提交任意元数据。
- Error：HTTPException的`detail={code,message,retryable}`；输入400/422，资源不可见404，revision/幂等冲突409，预算/节点上限409，来源/存储不可用503。message为固定可行动文案。

## MVP HTTP

1. `POST /api/literature-maps`：`{topic,name?,project_id?,year_start?,year_end?,source_ids?:[],conference_ids?:[],limit?:30,idempotency_key}`。topic去空白1–500字符，limit仅20/30/50，years为合法且起止不倒置的年份；服务端不接受owner。202返回`{schema_version,map_id,job_id,status,map,job}`，提交后后台运行。
2. `GET /api/literature-maps`：返回`{schema_version,maps:[Map]}`，先按更新时间倒序；首版最多100项，通过可选cursor/limit分页扩展，不因列表调用联网。
3. `GET /api/literature-maps/{map_id}`：`{schema_version,map,latest_job}`。
4. `PATCH /api/literature-maps/{map_id}`：`{expected_revision,name?,project_id?}`，项目可显式null解绑；`{schema_version,map}`。DELETE返回204，撤销map作业写资格，不删任何KB/共享缓存。
5. `GET /api/literature-maps/{map_id}/graph`：`{schema_version,map,nodes,edges,layers,latest_job}`，读本地；网络获取只能通过command/job。前端用同一对象绘图和详情，不能自行推断边。
6. `GET /api/literature-maps/{map_id}/nodes/{node_id}`：`{schema_version,node}`，未归该图404。
7. `PATCH /api/literature-maps/{map_id}/view`：`{expected_revision,positions?:[{node_id,x,y}],viewport?:{x,y,scale},filters?:{year_start?,year_end?,download_status?},layers?:{citation:boolean,similarity:boolean}}`。仅已存在node、有限数值/正scale；原子应用并增revision，响应`{schema_version,map}`。
8. `GET /api/literature-maps/{map_id}/jobs/{job_id}`：`{schema_version,job}`。events端点`?after_seq=0`返回`{schema_version,events,next_cursor}`，单次最多200条，next_cursor是最后已返回序号；空页不回退游标。
9. `POST /api/literature-maps/{map_id}/nodes/{node_id}/imports`：用户显式动作才调用既有安全导入/恢复流程，返回既有句柄与map/node关联。Task03需用窄bridge实现，不另建下载/登录协议；无法安全关联时返回固定可行动错误，不硬塞S2 ID。链接只允许安全http/https。

## Task04–07 扩展合同

- previews：POST `/{map_id}/previews`输入`operation=topic/references/citations/refresh,node_id?,idempotency_key`，返回202 preview/job。预览不加节点；GET `/{map_id}/previews/{preview_id}`读状态/候选。POST该preview的`/apply`输入`selected_ids,expected_revision,idempotency_key`，事务内重检20/200和墓碑；响应map/job/counts。
- jobs的`/stop`、`/retry`命令返回job；retry只重排失败/缺失单元；remove node与显式preview加回区分，移除后旧回调不复活。
- groups CRUD均带expected_revision；node.group_id只能引用同图group，删组解绑成员不删节点。
- analyses：POST node `/analyses`带`evidence_level=abstract/fulltext,idempotency_key`，返回analysis_id/job；GET analyses读真实结果/状态。自动分析不在MVP，禁止打开详情即调用模型。
- conversations：POST node `/conversations`返回既有conversation_id，服务端记录map/node/evidence上下文，继承当时project。打开既有会话必须核对其project，不能偷改旧会话。
- JSON export GET `/{map_id}/export?format=json`含稳定schema及公开安全字段；PNG在前端用当前SVG快照。JSON导入不实现。

## 作业、缓存、预算与排名

- 开发可注入client/store/embedder/executor，生产只用现有S2 client和全局1RPS。使用共享执行器资源或同生命周期的受限地图队列；不在请求线程完成网络采集。
- 每个图同时只有一个改变节点/边的活动作业；布局/筛选改动不被job覆盖。运行前/每单元写前校验map仍存在及job未停止。
- 首批S2可能返回438条而忽略limit。保留provider_count，候选按范围、确定identity去重和相关性选取，显式截到requested_count；绝不将整页直接入图。用现有dense/lexical边界做相关性排名，向量不可用时明确lexical降级。排序同分按稳定provider ID，首批不足为partial。
- 筛选列表内部按OR，source_ids与conference_ids同时存在按兼容交集；所有合法选项必须参与，不能只处理第一项。未知/不支持组合在创建前返回400固定INVALID_MAP_SCOPE，不得伪装存储故障。来源证明取实际目录记录/冻结身份，不用请求值自证。
- 引用采集只在已选节点集合内建立边，不为引用邻居自动建节点。MVP每节点最多获取100条references（分页明确截断为partial）；单作业最多60次S2逻辑请求，达到预算保留成果并标记待补缺。现有有限retry内部每次attempt仍经1RPS。
- 同一job的60次逻辑请求计数持久化且跨retry/restart累计；成功缓存命中不计外呼。达到预算返回partial/固定预算耗尽码，不能用反复retry重置预算。后续显式新作业使用自己的预算。
- 缓存key含provider/operation/identifier或query/filters/page/fields版本，元数据与引用成功缓存TTL24h；失败不缓存为成功空页，429不跨过既有退避。只有明确refresh/retry才对过期/失败单元请求，普通打开不联网。
- 向量通过既有embed_texts；缓存key=model_version+basis+内容sha256。200节点内余弦阈值0.75、每节点top3、无向去重；无匹配允许0边。多余候选不自动下载或写KB。
- 重启将未完成map作业重新入队，按持久成功单元/缓存断点补齐；幂等key与参数hash持久绑定，同key不同参数409。
- project删除调用owner-scoped detach，失败返回503并保留project。Map删除只清理地图专属表，在途结果不写回已删除map。

## 兼容与验收

新增接口不修改现有papers/research/chat公开合同；仅项目删除增加必要解绑门禁。每次公开字段/语义修订先记录本合同版本，再同步两端测试。
真实引用样本与合成200节点图分开；Task03须HTTP真实创建→job→graph→view重开成功，Task04起使用相同稳定ID/版本，不另造状态模型。
