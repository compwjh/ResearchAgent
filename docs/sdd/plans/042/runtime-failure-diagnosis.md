# Spec-042 Task 04 真实运行失败诊断

> 诊断角色：backend-reviewer（只读）
> 日期：2026-10-23（Asia/Shanghai）
> 分支：`codex/spec042-offline-evaluation`
> 范围：只核对 `langfuse_export.list_scores/find_score_by_id`、`runner` 验证接缝与本地 vendor Langfuse public API；未改生产代码/测试，未读取 `.env`，未发起真实 HTTP、POST 或删除请求。

## 结论

真实 API E2E 仍为 **NO-GO / BLOCKED（P1）**，但证据不支持“score 未写入”。`report.json` 已记录一次 POST 返回非空 `score_id=ba272a71-74bf-4ce6-8e74-181d649521c4`、`post_status=written`；随后 canonical verifier 在约 `0.05 + 0.10` 秒的 runner 等待窗口内得到 `not_found`。同一运行的只读后续核对又对 `/api/public/scores/{score_id}`、`/api/public/scores?traceId=...` 和 trace GET 均得到 HTTP 200，并确认 `id/name/traceId/value` 四字段匹配（`runs/20261023-0431-real-e2e/api-e2e.md:40-45`）。

因此当前最有证据的根因是：Langfuse score 写入经过异步 ingestion，canonical verification 的可见性等待窗口过短；另有一个独立的查询契约缺陷——当前代码把 v1 `/api/public/scores` 当成支持 `traceId` 过滤的列表接口使用，vendor v4.27.0 的 v1 schema/handler 实际不传递该过滤项。后者会使列表回查语义不可靠，但本次“稍后 exact GET 已可见”不能被改写成“查询 API 一定返回了错误结果”。

本结论只影响真实运行门禁；本地 runner/report 代码门禁仍以既有定向测试的 GO 为准，不能据此把 Spec-042 标记为完成。

## 运行证据

- `docs/sdd/plans/042/runs/20261023-0431-real-e2e/report.json:6-47`：一条真实 trace；`post_status=written`、`written=true`、score 为 `1.0`，但 `verification_status=not_found`、`verified=false`，最终 `status=failed`。
- `docs/sdd/plans/042/runs/20261023-0431-real-e2e/api-e2e.md:38-45`：同一 `score_id` 的只读 exact GET、列表 GET、trace GET 后续均成功；没有第二次 POST。
- `backend/eval_042/runner.py:26-27,344-404`：`_VERIFY_ATTEMPTS=3`，仅在两次间 sleep `0.05`、`0.10` 秒；每次调用 `find_score_by_id`，三次均未找到才生成 `score id not found on trace`。
- `backend/eval_042/langfuse_export.py:64-77`：POST 到 `/api/public/scores`，只要响应有非空字符串 id 即认为写回已被服务接受；这证明有 write response，不证明 ClickHouse read side 已立即可见。

## Vendor API 与当前调用的对照

### 1. 写入是异步可见，而非同步读后写

- `vendor/langfuse/web/src/features/public-api/server/scores-api-service.ts:223-280`：`createScore` 构造 `SCORE_CREATE` 事件，经 `processEventBatch` 后返回 `{ id: scoreId, result }`。
- `vendor/langfuse/packages/shared/src/server/ingestion/processEventBatch.ts:275-325,327-417`：事件先上传 blob，再以 `queue.add(..., { delay: ... })` 入 ingestion queue，函数随后返回 batch result。
- `vendor/langfuse/packages/shared/src/server/repositories/scores-utils.ts:29-55`：按 id 的读取直接查询 ClickHouse `scores` 表；因此 POST 返回和 read-side 可见之间存在真实异步边界。

这与 E2E 的“canonical 立即回查失败、稍后独立 exact GET 成功”一致。不能把总 CLI 运行时间（约 18 秒，其中含 3 次本地 judge）当成 score 已被等待 18 秒；score 写完后的 runner verification 仍只有上述约 0.15 秒 sleep。

### 2. 当前 list URL 存在 v1 trace 过滤契约错配

- 当前 `backend/eval_042/langfuse_export.py:80-109` 固定请求 `GET /api/public/scores?traceId=<trace>&limit=<n>&page=<p>`，再按 `meta.totalPages` 走 page-based 分页。
- vendor 的 v1 route `vendor/langfuse/web/src/pages/api/public/scores/index.ts:64-135` 确实提供 `GET /api/public/scores`，但其 `scoreParams`（`98-115`）没有 `traceId`；共享 v1 `GetScoresQuery`（`vendor/langfuse/packages/shared/src/features/scores/interfaces/api/shared.ts:35-73`）也没有 `traceId`。v1 支持的是 `scoreIds`（同文件 `49-55`）。未知 query key 经过 `createAuthedProjectAPIRoute.ts:402-406` 的 Zod parse 后不会成为 v1 handler 的 trace filter。
- `find_score_by_id`（`backend/eval_042/langfuse_export.py:112-119`）只在该列表结果中 client-side 比较 id。它没有调用 vendor 已提供的 exact GET：`vendor/langfuse/web/src/pages/api/public/scores/[scoreId].ts:15-41`；该 route 返回包含 `id/name/traceId/value` 的 v1 score。
- v2 列表才显式接受 `traceId`（`vendor/langfuse/packages/shared/src/features/scores/interfaces/api/v2/endpoints.ts:11-22`，route 为 `vendor/langfuse/web/src/pages/api/public/v2/scores/index.ts:13-103`）。v3 则使用 `GET /api/public/v3/scores` 的 `id`、`traceId` 和 cursor（`vendor/langfuse/fern/apis/server/definition/scores-v3.yml:29-107`；`vendor/langfuse/packages/shared/src/features/scores/interfaces/api/v3/endpoints.ts:52-107`），不是当前 `totalPages` 逻辑。

因此，当前 v1 list 调用不是“路径不存在”：本地 vendor 具备该 GET，且 E2E 后续 list GET 返回了 score；问题是 `traceId` 不属于 v1 的服务端过滤契约，当前代码不能把它解释为按 trace 过滤。v1 page/limit/totalPages 语义本身与 `scores.ts:2831-2847` 的 offset 分页一致，但扫描的是未按 traceId 过滤的列表。该错配会增加无关扫描并使回查依赖分页/排序，不是本次未写入的证据。

## 最小修复建议（供 backend-dev 实施）

1. 保留“score POST 只发一次”原则。将 verification 读路径改为 vendor 已证实的 exact-ID 读：`GET /api/public/scores/{score_id}`（或与部署版本明确绑定的 `/api/public/v2/scores/{score_id}`），回读后仍逐字段核验 `id`、`traceId`、`name`、`value`。exact route 已被当前 E2E 的只读后续核对验证存在和字段语义，不会靠旧同名 score 冒充。
2. exact GET 仍必须使用有界的真实时间 deadline（建议总窗口不超过 15 秒，具体 backoff 由实现与测试冻结），而不是继续使用 0.05/0.10 秒级窗口。将“尚未可见”的 404/空结果作为待可见状态重试；权限错误、参数解析错误、非 loopback/transport policy 错误不得重试。deadline 到期仍返回非零和 `verified=false`，不补 POST、不把分数改写为 0。
3. 如果为兼容性选择继续 list 回查，至少改用 v1 已定义的 `scoreIds=<score_id>`（或明确切换 `/api/public/v2/scores` 并同时传 `scoreIds`/`traceId`），不要在 v1 `/api/public/scores` 上依赖未定义的 `traceId` query。若切换 v3，必须另实现 `id` 过滤与 cursor 迭代，不能复用 `meta.totalPages`。
4. 补离线 fake transport 覆盖两条事实：第一，写回后前若干次 exact read 返回 404/空结果、deadline 内随后返回正确四字段时最终成功；第二，deadline 到期仍未可见时保持非零且只保留一次 POST。测试不得真实调用 Langfuse，也不得通过调大阈值伪造 score。

## 门禁判定

| 范围 | 判定 | 依据 |
|---|---|---|
| runner/report 本地代码门禁 | GO（仅代码/定向测试范围） | 既有 `test_evaluation_runner.py`、`test_evaluation_report.py` 通过记录；不扩大到 CLI/API/Spec 收口 |
| 本次真实 chat-quality E2E | NO-GO / BLOCKED | `report.json` exit 状态失败；canonical verification 在过短窗口内 `not_found` |
| “score 未写入”诊断 | 不成立 | 同一 id 后续 exact GET/list/trace GET 均返回匹配四字段 |
| Spec-042 完成 | 未通过 | 真实 E2E 尚未以 canonical verifier 成功结束，不能冒充 Spec 已完成 |

## 2026-10-23 P1 修复后的集中窄复审

### 复审对象与 vendor 契约

- `backend/eval_042/langfuse_export.py:113-135` 现在使用 `GET /api/public/scores/{score_id}` exact-ID 路径；`quote(..., safe="")` 将 id 当作单一路径段，空值和 ASCII 控制字符拒绝；仅把 HTTP 404 转换为 `None`，其它 HTTP、JSON 和 transport/guard 错误继续抛出。
- 该路径与当前 vendor v4.27.0 `vendor/langfuse/web/src/pages/api/public/scores/[scoreId].ts:15-41` 一致；该 handler 通过 `GetScoreQueryV1` 按 `scoreId` 取单条 score，而不是从列表第一页猜测。v1 返回的 score schema 包含 runner 需要的 `id`、`traceId`、`name`、`value`。
- `backend/eval_042/runner.py:28-29,346-361,377-430` 现在最多执行 6 次 exact GET，sleep 为 `1,2,3,4,5` 秒，总等待 15 秒；`None`（404 尚不可见）和 429/5xx/连接瞬态重试，401/403、解析、参数、loopback guard 错误 fail-fast。收到具体 score 后，`id`、`traceId`、`name`、`value` 任一 mismatch 立即失败，不等待、不换 id、不使用旧同名 score。
- `backend/eval_042/langfuse_export.py:65-78` 的 score POST 未改；现有 runner 路径仍只调用一次。精确读取不再依赖旧 v1 list 的未定义 `traceId` query，也不受 first-100/list pagination 影响。

### 本地验证证据

本复审未启动服务、未读取 `.env`、未发起真实 HTTP/POST/删除请求；原失败 artifact `runs/20261023-0431-real-e2e/` 保留未覆盖。

| 检查 | 命令 | 结果 |
|---|---|---|
| runner + Langfuse transport 精确回归 | `.venv/bin/python -m pytest tests/evaluation/test_evaluation_runner.py tests/evaluation/test_offline_transport.py -q` | **83 passed in 0.35s，exit 0** |
| 生产模块编译 | `.venv/bin/python -m py_compile backend/eval_042/langfuse_export.py backend/eval_042/runner.py` | **exit 0** |

定向测试覆盖了：exact endpoint 而非 trace list、404 可见性等待、401/403/坏 JSON fail-fast、延迟可见最多一次 POST、永久不可见 6 次后非零、瞬态重试、具体四字段 mismatch fail-fast，以及旧同名 score 不被接受。最新 backend report 另记录同一候选 evaluation 领域 `133 passed`；本次 reviewer 自行重跑的受影响集合为上述 83 项。

### 当前判定

**代码门禁 GO（仅 `langfuse_export.py`/`runner.py` 受影响范围）。** 修复与 vendor exact-ID route 对齐，且不会用同名旧 score 或 first-100 列表项冒充成功；15 秒有界最终一致性等待也保留失败非零和单次 POST 语义。

**真实 E2E 历史 NO-GO 保留。** 本复审没有新发请求，不能把修复后的代码门禁 GO 写成真实 API E2E GO；必须由根在冻结新 candidate 后用新的 run 目录重跑真实 E2E，再进行最终回归/验收。Spec-042 仍不得标记为完成。
