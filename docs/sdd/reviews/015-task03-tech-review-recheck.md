# Spec015 Task03 P0/P1 修复复审

- 评审者：当前协作 Agent
- 角色：独立开发主管（Tech Lead）
- 评审时间：2026-09-04 CST
- 评审范围：`docs/sdd/reviews/015-task03-tech-review.md` P0/P1 清单；`backend/app/domain/paper_discovery.py`、`backend/app/services/paper_discovery_normalization.py`、`paper_discovery_store.py`、`dblp_publication_source.py`、`openalex_enricher.py`、`paper_discovery_search.py`；对应四个测试文件
- 约束：只读复核；未修改业务代码、Spec015 或测试；未执行 Git 操作

## 结论：P0 已通过，P1 未全部收口，暂不放行

上一轮两个 P0 已实质修复并有回归测试：候选主键已改为 search session 范围，DBLP 请求已透传查询词并保留服务端 stream/year 约束。目标测试使用根目录导入路径运行结果为 `30 passed`。

但仍存在会影响安全边界、结果确定性和后续导入生命周期的 P1 缺口，因此本轮不能签署 Task03 完成。OpenAlex malformed/degraded 协议和 `schema_meta` 单例校验本轮通过；DBLP Venue Search/自定义 Venue Search 仍未实现，且搜索/会议配置 HTTP 路由当前未接入。

## P0 复核

### P0-1：跨 search session 的候选主键 — 通过

`paper_candidates` 当前为 `PRIMARY KEY(search_id, candidate_id)`，并保留 `(search_id, normalized_title, year, conference_id)`、按 search_id 的 DOI/DBLP key 唯一约束。`PaperDiscoverySearchService` 仍为同一论文生成稳定 domain `candidate_id`，但不同 session 可以保存相同值。

回归测试：

- `tests/test_paper_discovery_store.py::test_store_allows_stable_candidate_id_across_search_sessions`
- `tests/test_paper_discovery_search.py::test_same_stable_candidate_id_is_saved_for_distinct_search_sessions`

### P0-2：DBLP query 透传 — 通过

`DBLPPublicationSource.search(source, query, years, limit)` 将原始已校验 query 传入 `_request`；请求参数 `q` 为 `"{query} stream:{stream} year:{year}"`，stream/year 仍由服务端 source 和年份参数决定。响应记录再次执行 stream、年份、conference type、venue alias 过滤，query 中注入其他 stream 不能绕过过滤。

回归测试：

- `tests/test_dblp_publication_source.py::test_search_encodes_query_while_retaining_server_controlled_filters`
- `tests/test_dblp_publication_source.py::test_query_cannot_bypass_stream_filter`

## P1 逐项复核

### 已通过

1. **统一规范化与基础去重：基本通过。** `normalize_doi` 已覆盖 HTTP/HTTPS DOI URL、`doi:` 前缀和末尾句点；`normalize_title` 在 DBLP、搜索和 SQLite 派生字段中复用。DBLP key/title 组合键包含年份与会议，搜索层同样按 DOI 或 key/title+year+conference 合并。已有跨年、跨会议和 DOI 变体测试。
2. **OpenAlex malformed/degraded 协议：通过。** `locations` 非 list 时不再迭代崩溃，而是产生 `OPENALEX_INVALID_LOCATIONS`；helper 保留 `warnings` 与 `error_code`；搜索编排可传播结构化 warning/error；`pdf_access` 在 enricher 与搜索合并边界限制为 `unknown/public/login_required/unavailable`。对应 malformed locations、超时、429、5xx、非法 JSON 与 helper 传播测试通过。
3. **schema_meta：通过本轮范围。** 初始化使用显式事务执行 DDL/seed；启动时拒绝多行、非 integer 或非当前版本，且创建 `schema_meta_singleton` 唯一表达式索引。重复 metadata 行测试通过。
4. **跨 session、候选快照基础存储：通过。** 30 条定向测试全部通过，候选 session 外键、WAL、`foreign_keys=ON`、`busy_timeout=5000` 均保持。

### 仍需修复的 P1

#### P1-1：受控会议 source 校验仍可被伪造

`paper_discovery_search.py:118-130` 只检查输入对象的 enabled、conference_id、stream 和 aliases 非空，并仅比较输入 stream 与存储 stream；没有比较或直接使用存储的 `name`、`short_name`、`venue_aliases`、`built_in`。因此同一 `conference_id`/`dblp_stream` 但替换名称和 venue alias 的对象仍会被接受，并发送给 DBLP。

最小复现结果：

```text
输入 ConferenceSource("ccs", "EVIL", "CCS", "conf/ccs", ["EVIL VENUE"])
结果：DBLP called with forged source；未抛出 CONFERENCE_INVALID
```

最小修复：按 `conference_id` 从 store 解析唯一的 enabled 配置，并将该存储对象传给 DBLP、候选映射和过滤；若保留对象参数，则至少拒绝所有身份/别名字段与存储值不一致的输入。补充“同 stream 伪造 aliases/name/built_in 均拒绝”回归测试。

#### P1-2：初排编号仍依赖年份输入和上游返回顺序

`paper_discovery_search.py:97-105` 直接用 DBLP records 的迭代顺序赋值 `initial_rank`；`DBLPPublicationSource.search` 又按 `years` 输入顺序逐年追加结果。因此相同候选集合只交换年份输入顺序就会改变 `initial_rank` 和同分结果。

最小复现结果：相同两篇候选分别以 `[2023, 2024]` 与 `[2024, 2023]` 搜索时，初排分别为 `(2023, 0),(2024, 1)` 与 `(2024, 0),(2023, 1)`。当前 `_sort_key` 的 tie-break 字段本身包含 initial_rank/year/title/id，但 initial_rank 的来源还不稳定。

最小修复：在合并/编号前定义不依赖年份请求顺序和重试返回顺序的确定性记录序（并明确 API 分页/召回序与 `initial_rank` 的关系），然后按该序一次性赋值；补充年份重排、重复请求及 enrichment 后排序不变测试。

#### P1-3：DBLP malformed payload 仍静默变成空结果

`dblp_publication_source.py:89-90` 对非 list 的 `hit` 包装成单元素后交给过滤器；`result/hits/hit` 缺失或形状错误会被当作零命中，没有 `DBLP_INVALID_RESPONSE` 或可诊断 warning。Task03 计划要求未知/异常 payload 不放行并记录可诊断原因。

最小修复：区分“合法空 hits”与 schema 形状错误；对 malformed `result/hits/hit` 返回稳定协议错误/warning，保留部分年份成功结果的单源降级语义，并补充对应测试。

#### P1-4：`save_conference` 未显式开启事务

`paper_discovery_store.py:166-180` 通过连接上下文的隐式事务提交会议写入，没有像初始化、`save_search`、`cleanup_expired_searches` 那样显式 `BEGIN`。这与 Spec015“所有写入使用显式事务”不一致，且没有回滚测试。

最小修复：在会议写入中显式 `BEGIN`，补充约束失败/异常后的回滚测试。

#### P1-5：TTL 仍会级联删除候选，未满足导入历史保留语义

当前数据库只有 `conference_sources`、`search_sessions`、`paper_candidates`、`schema_meta` 四张表，没有 `paper_import_batches/items` 或候选快照引用关系；`paper_candidates.search_id` 为 `ON DELETE CASCADE`。实测过期清理后候选从 1 条变为 0 条。

这在 Task03 尚未实现导入表的切片中可作为后续任务前置，但不能宣称已满足 Spec015 的完整 TTL 契约：导入引用的候选必须保留，TTL 只能删除未被引用的候选/会话。

最小修复：在导入任务接入前确定并实现保留快照或 `RESTRICT`/条件清理的 FK 图；补充“已导入引用的过期搜索不可删除、未引用候选可清理”的测试。

#### P1-6：Spec 配置项尚未接入

搜索服务固定 `expires_at = now + 24h`，`max_limit/max_years` 仅来自构造器默认值，代码库没有 `PAPER_DISCOVERY_SEARCH_TTL_SECONDS`、`PAPER_DISCOVERY_SEARCH_LIMIT`、`PAPER_DISCOVERY_MAX_SEARCH_LIMIT` 等配置接入。与 Spec015 配置表和上一轮 P1 清单不符。

最小修复：从项目配置读取 TTL、服务端 limit 与候选池上限，构造器参数仅作为显式测试覆盖；补充配置边界测试。

#### P1-7：Task03 计划声明的 API 路由尚未接入

当前 `backend/app/api/routes.py` 没有 `/api/papers/conferences`、`/api/papers/conferences/search`、`/api/papers/search` 路由，因此无法验收错误体/状态码、会议列表/停用/删除语义和功能开关零外部请求。应由后续路由切片补齐，或修订 Task03 验收范围后再放行核心服务。

自定义 Venue Search/用户会议新增按 Task02 结论继续保持 blocked；本轮不将其误报为已实现。

## 验证命令与结果

首次直接运行因测试导入路径未包含项目根目录而收集失败（`ModuleNotFoundError: No module named 'backend'`）。使用项目约定的根目录导入路径重跑：

```bash
PYTHONPATH=. pytest -q \
  tests/test_paper_discovery_store.py \
  tests/test_dblp_publication_source.py \
  tests/test_openalex_enricher.py \
  tests/test_paper_discovery_search.py
```

结果：`30 passed in 0.09s`。

额外只读复现：

- forged source 同 stream 但伪造 aliases/name：被接受并调用 DBLP（P1-1）。
- 相同候选以不同年份输入顺序：`initial_rank` 顺序改变（P1-2）。
- 过期 session 清理：`cleanup_expired_searches` 级联删除候选（P1-5）。
- SQLite 表清单仅含四张基础表，未含 import batches/items（P1-5）；代码搜索未发现三组 Task03 API 路由（P1-7）。

## 放行意见

- P0：通过。
- P1：未通过；至少 P1-1、P1-2、P1-3、P1-4、P1-5、P1-6 仍需收口；P1-7 需明确路由交付边界。
- 复审结论：打回实现，修复后重新进行 Tech Lead 复审。自定义 Venue Search 不属于本轮放行条件，继续保持 blocked。
