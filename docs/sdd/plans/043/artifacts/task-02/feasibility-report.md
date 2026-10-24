# Spec043 Task02 可行性合并报告

## 最终裁决

**GO：Task02 核心可行性通过。**

该结论只表示“真实来源/身份/embedding 能力与隔离 SVG 交互样例足以进入 Task03”，不表示生产地图 MVP 已实现、生产 API 已成功、服务已部署或用户验收已完成。Task03 必须先冻结公开合同，再在实现中复用现有入口；下列窄接缝是已确认的实现约束，不新增一轮产品门禁。

## 证据边界

本次合并复核只读取既有落盘证据与测试，并重新执行本地精准测试；未发起新的外部请求、未修改业务代码、未启动服务、未部署。

| 证据 | 性质 | 结论 |
|---|---|---|
| [`api-evidence.json`](api-evidence.json) | 已授权的真实 S2 只读探针与真实 title+abstract embedding | 支持来源、关系方向、身份分离和 embedding 可用性；失败/限流状态均保留 |
| [`browser-evidence.json`](browser-evidence.json) | 真实 Chromium 加载 `file://` 合成 SVG fixture | 支持 200 节点交互与 34/620 关系压力样例；不代表生产前端或真实论文关系 |
| [`backend-feasibility-report.md`](backend-feasibility-report.md) | 后端证据摘要 | 核心 GO，Task03 需窄适配 |
| [`frontend-feasibility-report.md`](frontend-feasibility-report.md) | 前端隔离样例报告 | 仅前端 SVG 交互前提 GO |
| [`reuse-contract.md`](reuse-contract.md) | 复用入口和身份/状态约束 | 作为 Task03 合同冻结输入 |

### 真实 S2/API 事实

- 主题为 `fuzzing vulnerability discovery`。`search_bulk(limit=30)` 与 `search_bulk(limit=50)` 各解析 438 条；地图层必须分别接受 30/50 条，并记录 `provider_count=438` 与 `accepted_count=30/50`。这是 provider 返回超量后的本地截取适配，不是 API 不能取 30/50。
- 真实非空引用页来自 Sizzler：5 条 `citedPaper`，方向为 `source -> citedPaper`，`offset=0`、`next_offset=5`。不能把 citations 与 references 混向。
- 初始 references 页和 SLIME references 页为 malformed/invalid envelope（含 `data=null` 或缺分页字段）；必须标为 invalid/source failure，不能当作合法空关系。SLIME citations 与 references 重试出现 HTTP 429，必须保留 rate-limited 状态，不能写成空边。
- 真实身份包含 DOI `10.1145/3533767.3534385` 和 S2 `paper_id=0085d37afabc73c2ac03c32b68d311ef550b5987`；规范化 DOI 可匹配，但 batch 回查因 provider rate limit 未确认。`catalog_paper_id` 保持空并标记 `unverified_external_id`，不能标题近似合并或伪造目录关联。
- 复用现有 embedding 对 6 条真实 title+abstract 输入做 15 对比较，模型 `bge-m3`、1024 维、阈值 0.75，未发现 `>=0.75` pair。无相似边是该输入集的正常结果，不是 embedding 服务缺失，也不允许降低阈值造边。

### 前端合成压力事实

- fixture 通过 `file://` 直接加载，无生产前端、网络、外部脚本或业务 API。baseline 为 200 节点/34 边；`?profile=high` 为 200 节点/620 边（310 citation、310 similarity），两档均为 synthetic 数据。
- 真实 Chromium 交互均完成：缩放、平移、拖动节点、选择节点；两档布局均为 8 次 RAF，long task 为 0。high 档最终记录最大 handler 约 0.1ms、最大渲染 wall 约 15.2ms、最大 gesture wall 约 794ms；gesture wall 包含自动化输入序列，不能替代每帧指标。
- 因此该证据只支持 SVG 调度和交互边界可行，不支持生产地图性能、真实数据渲染、移动端验收或 API E2E。

## Task03 必须先冻结并复用的最小合同

1. 首批节点上限及 `20/30/50` accepted limit 固定；provider 返回量、accepted 量和截取策略分别可观察，不能把 438 条直接越过地图预算。
2. graph page 固定三类状态：合法空页、malformed/invalid、`429`/`source_failed`；invalid 或限流页不得写入空 `MapEdge`。
3. 引用方向固定为 `citingPaper -> source` 与 `source -> citedPaper`；S2 `paper_id` 与 `catalog_paper_id` 分离，只有确定 DOI/arXiv 才能建立目录关联。
4. 相似层记录批次 `model_version`、`basis=title_abstract`、内容摘要/hash、阈值和状态；无 `>=0.75` pair 时引用图与元数据仍可 partial，不降低阈值。
5. 复用 `SemanticScholarGraphClient.search_bulk/batch/graph_edges`、既有共享 1-RPS limiter、有限 retry 和 `embed_texts`；不新建第二套 provider/limiter，不创建个人 KB collection，不下载 HTML/PDF。
6. 生产前端应沿用已验证的节点/边类型与可观察状态，但必须在真实地图 API 接口上重新验证创建、读回、partial/error 和保存重开；隔离 fixture 不得作为生产成功证据。

上述条目是 Task03 的合同冻结与复用限制，属于既定 Task02→Task03 交接，不是因本次合并复核新增的 No-Go 门禁。偏好型建议（如布局算法、标签策略）不阻塞进入 Task03。

## 与已冻结 Task03 合同的交接核对

只读核对 [`interface-contract.md`](../task-03/interface-contract.md) 未发现范围扩大或两端需要猜测的冲突：

- `schema_version`、服务端稳定 ID、同图 200 节点上限、`provider_count/accepted_count`、S2/catalog identity 分离和引用方向均与本报告一致。
- 单个地图作业最多 60 次 S2 逻辑请求；选定节点的 references 每节点最多 100 条，分页截断必须保留 `partial`，不能把预算耗尽或分页不足伪装成 completed 空结果。
- SQLite 默认路径为 `data/literature_maps/literature_maps.sqlite3`，仅允许服务端 `LITERATURE_MAP_DB_PATH` 覆盖和测试注入；不迁移/删除旧库、不建个人 KB Collection。
- owner 由现有服务端 `OWNER_ID` 边界提供，客户端不能覆盖；service/store 显式传 owner，跨 owner 按 404 处理。项目绑定沿用现有 owner/existence 校验，项目删除只做 owner-scoped detach，失败保留项目。
- 公共 HTTP 入口、事件游标、固定错误码和 `generating/ready/partial/failed/stopped` 状态已在合同中冻结；本 Task02 不实现、不调用这些生产接口，也不把合同冻结当作接口已上线。

## 精准验证

- `.venv/bin/python -m pytest -q tests/literature_maps/test_map_feasibility.py tests/frontend/test_frontend_map_feasibility.py`：退出码 **0**，**8 passed**。后端测试离线重放脱敏证据；前端测试在合成 fixture 上运行 Chromium，不调用 S2/Ollama/数据库。
- `.venv/bin/python scripts/check_test_layout.py`：退出码 **0**，`test layout: ok`。
- 未运行全量回归；未进行真实生产 API E2E、部署或启动验证，因此不作相应成功声明。

## 尚未完成范围

生产地图 API、数据库 schema/迁移、地图 job/events、前端生产入口、保存重开、partial 恢复、手机适配、真实 API E2E 和部署均未实现，属于 Task03–08 范围；本报告不能替代后续验收报告。
