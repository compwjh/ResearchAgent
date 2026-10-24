# Task02 后端可行性报告

## 结论

**GO（核心可行性通过，带 Task03 窄适配条件）**。真实 S2 与既有 embedding 客户端均可达；已取得非空真实引用页，证明“自动发现 + 引用分层”的核心来源能力成立。`search_bulk` 对 30/50 返回 438 条属于 provider_count 与地图 accepted_count 的适配，不是 API 无能力；embedding 六条真实 title+abstract 两两比较未发现 `>=0.75` pair，但模型可用且不得为阈值造边。`SLIME` 的 invalid envelope、429 限流和未确认 batch 关联需按 partial/source_failed/unverified 状态处理，不阻塞核心可行性。

## 真实证据摘要

- 主题：`fuzzing vulnerability discovery`。
- `search_bulk(limit=30)`：HTTP 成功，解析 438 条，地图 accepted_count 应为 30；`search_bulk(limit=50)` 同样解析 438 条，accepted_count 应为 50。请求参数可达，地图层必须记录 provider_count 并截断。
- `Sizzler` 的 `references`：真实有效页解析 5 条，方向为 `source -> citedPaper`，安全 envelope 含 `data[]/citedPaper/next/offset`，证明非空引用链路可用。
- `SLIME` 的 `references`：HTTP 成功但 envelope 仅含 `citingPaperInfo/data=null`，缺少 `total/next/offset`，客户端返回 invalid；不能当作“无引用”。其 `citations` 429 也必须单独标记来源限流。
- 身份：真实搜索元数据含 DOI `10.1145/3533767.3534385` 与 S2 paper ID `0085d37afabc73c2ac03c32b68d311ef550b5987`；normalized external ID 匹配规则可验证。批量回查因 provider rate limit 未确认，故标记 `unverified_external_id`，未冒充 catalog 关联。
- embedding：复用 `embed_texts`，对仓库已固定的 6 条真实安全论文元数据 title+abstract 小批使用 `bge-m3`、1024 维，比较 15 对，未发现 `>=0.75` pair；cosine `0.523817341567123` 作为补充样本记录，不把无边误判为 embedding 故障。

完整脱敏记录：[api-evidence.json](api-evidence.json)。复用与接口缺口：[reuse-contract.md](reuse-contract.md)。

## Task03 必须冻结的最小适配

1. 在地图采集层强制执行 accepted limit（20/30/50），同时保存 provider_count 与 accepted_count，防止 438 条越过地图预算。
2. 固定 graph page envelope 的 valid-empty、invalid-shape、429/source_failed 分层；invalid response 不得写入空 MapEdge。
3. 为 DOI/arXiv 关联保留 `unverified_external_id` 状态；仅 deterministic external ID 才能关联 `catalog_paper_id`，S2 ID 始终独立保存。
4. 为 embedding 记录批次级 model/basis/content hash；相似边只接受真实 cosine `>=0.75`，无满足 pair 时保持引用图可用、相似层 partial。
5. Task03 合同需冻结 S2 与 catalog identity 分离、引用方向、provider_count/accepted_count、source_failed、rate_limited 与 partial 错误码。

## 安全与范围

- API key 只由已有配置在内存加载；证据只记录 `key_configured=true`，不记录密钥或请求头。
- 未抓取 HTML/PDF，未启动额外 service，未写业务数据库、KB Collection 或旧研究任务。
- 证据请求使用既有 1 秒共享 limiter 与有限 retry；累计 10 个逻辑请求、观察到 11 次 provider attempt，未超出 12 次预算。

## 验证

- 受控真实探针：授权后退出码 0；S2 search/graph/identity 摘要和 embedding 结果见 `api-evidence.json`；核心可行性结论 GO，Task03 仅需按上方窄适配落合同。
- 离线能力测试：`.venv/bin/python -m pytest -q tests/literature_maps/test_map_feasibility.py`。
- 测试布局：`.venv/bin/python scripts/check_test_layout.py`。
- 生产地图 API、业务数据库和前端未实现，未宣称部署或 API E2E 完成。
