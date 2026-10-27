# Spec 043 当前运行限流阻塞诊断

日期：2026-10-27  
范围：只读核对 task-10 两次新建地图运行记录、运行目录中对应服务日志的安全摘要，以及 Semantic Scholar 请求、限流、缓存和官方目录适配器代码。未发起外部请求，未读取 `.env` 内容或凭据，未运行测试，未修改业务代码或测试。

## 结论

- **本地限流器不是 `SEMANTIC_SCHOLAR_RATE_LIMITED` 的产生者。** 当前请求客户端只在收到 HTTP 响应且 `status_code == 429` 时生成该错误码；本地 limiter 只用锁保证进程内请求至少间隔一秒，不生成冷却错误（`backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py:267-291`；`backend/app/paper_discovery/infrastructure/semantic_scholar_adapter.py:33-72`）。运行时通过默认组合创建 `LiteratureMapService`，其默认 client 是 `SemanticScholarGraphClient`（`backend/app/literature_maps/application/runtime.py:204-209`；`backend/app/literature_maps/application/service.py:63-71`）。因此，**代码路径强烈表明这些错误对应一次真实 HTTP 429 响应**；但运行日志没有记录该响应的原始状态码，不能把日志本身当作独立确认。
- **是否加载了 `SEMANTIC_SCHOLAR_API_KEY` 无法从现有运行记录判断。** 代码会在配置模块导入时调用 `load_dotenv()`，client 再从环境变量读取该项；有值才发送请求头，没有值仍会发请求（`backend/app/platform/config.py:6-8`；`backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py:230-253`）。运行记录和对应日志均没有安全的“凭据是否存在”布尔信号。未加载密钥不能单独解释为本地生成的错误码，也不能由 429 反推出密钥已加载。
- **官方目录是否为空、不可用或没有可验证条目无法从这次结果区分。** 官方目录查询先运行；若没有官方行，地图服务会再发一条 Semantic Scholar 补缺查询。补缺请求返回错误时，官方行为空的分支直接返回补缺错误码，可能遮住先前的目录错误（`backend/app/literature_maps/application/service.py:948-1009`）。适配器在没有可验证论文时会设置 `CATALOG_SCOPE_UNVERIFIED`，但该状态没有保存在本次运行证据中（`backend/app/literature_maps/application/catalog_adapter.py:218-247`）。所以 `nodes: 0` 不能证明官方目录返回空结果。

## 运行证据

- `task10-smoke-20261027-125456`：创建返回 202；首次图读取为 `partial`、`nodes: []`，记录 `provider_request_count: 1` 和 `SEMANTIC_SCHOLAR_RATE_LIMITED`；一次重试后仍为 `partial`、0 nodes，累计 `provider_request_count: 2`，失败单元各记录同一错误。详见 `docs/sdd/plans/043/task-10-runs/task10-smoke-20261027-125456/{create.json,graph-first.json,retry-once.json,graph-after-retry.json,result.json}`。
- `task10-official-20261027-130257`：USENIX Security 2024 范围创建返回 202；图读取为 `partial`、0 nodes，记录 `provider_request_count: 1` 和 `SEMANTIC_SCHOLAR_RATE_LIMITED`。详见 `docs/sdd/plans/043/task-10-runs/task10-official-20261027-130257/{create.json,graph-first.json,result.json}`。
- 两个运行的非零 provider 请求计数与应用代码一致：未命中成功请求缓存时才调用 client 并计数；仅成功载荷会写入该缓存（`backend/app/literature_maps/application/service.py:972-1009,1047-1085,1111-1118`）。这排除了“仅由缓存空结果造成此错误”的解释。
- 对运行目录 `/Users/wjh/ResearchAgent/deploy/run.log` 做了一次仅输出行号、级别和匹配标记的定向检查：目标地图 ID 命中的是 INFO 行（smoke：75788、76064、76349；official：77308）；没有找到 `SEMANTIC_SCHOLAR_RATE_LIMITED` 字符串或 official job ID 的日志行，匹配行也没有可提取的时间戳/HTTP 状态码。日志没有提供 429 的独立原始响应证据。

## 最小后续验证

1. 若只需确认配置状态，由运行环境负责人只提供进程启动时 `SEMANTIC_SCHOLAR_API_KEY` **是否存在**（是/否），不要提供变量值。
2. 若需确认官方目录结果，在同一查询与过滤条件下补充一条脱敏诊断摘要：`CatalogSearchAdapter` 的 `error_code`、候选 ID 数量、目录实体读取数量、S2 enrichment 后数量。需要记录在 S2 补缺查询之前，才能判断“目录无命中”还是“目录/关联环节不可用”。
3. 若需日志级别的独立 429 证据，只记录对应 API 请求的 HTTP 状态码、尝试序号和是否存在 `Retry-After`；不要记录请求头、密钥、cookie 或响应正文。当前阻塞下不应靠无限重试或伪造节点来验证。

需要用户/运行环境负责人帮助的只有前两项中的所需状态证据；无需提供任何凭据内容。当前结论足以排除“本地冷却器自行返回该错误”，但官方目录结果和密钥加载状态仍未证实。
