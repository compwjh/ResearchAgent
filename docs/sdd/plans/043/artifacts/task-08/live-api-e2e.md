# BLOCKED — Task08 backend live API E2E (`134dce4`)

## 结论

**BLOCKED。** 本轮从真实 `POST /api/literature-maps` 入口创建了全新 project/map，并按约 10 秒事件/作业观测规则等待真实终态。地图作业真实返回 `partial/finished`，但 Semantic Scholar discovery 被限流，接受节点数为 `0`，因此无法安全继续保存重开、references preview/apply、引用/相似关系或摘要会话；未重试 provider、未伪造节点、未启动/停止服务、未重索引、未触碰既有验收地图 `0baabeae7268429c9f7e4de8098ae1d0`。

失败不是服务不可达：`POST` 创建返回 `202`，job/events/map/graph 读取均返回 `200`，服务阶段从 `queued/discover` 推进到 `running/discover`，最后进入 `partial/finished`，并持久化真实限流错误。

## 运行与证据

- Spec/Task：`043-literature-map-topic-exploration` / Task08 backend live API。
- 候选：`134dce4`，服务 `http://127.0.0.1:8000`，端口 `8000`。
- Run ID：`20261021-152724-134dce4-api`。
- 脱敏不可覆盖证据：[evidence.json](runs/20261021-152724-134dce4-api/evidence.json)。
- 运行时间：`2026-10-21T15:27:24.144385+00:00` → `2026-10-21T15:27:34.197203+00:00`。
- 本轮请求未携带或保存凭据、Cookie、授权头、隐藏推理；证据中的 `owner_id` 等字段已脱敏移除。

实体 ID：

| 实体 | ID | 实际状态 |
|---|---|---|
| 临时 project | `5c89771c08bc4aa39f8ff84b406cc837` | `POST /api/projects` HTTP 201，active |
| fresh map | `35a56c6f2da84fca85fc3c21dfa0055c` | HTTP 202 创建；最终 map status `partial` |
| create job | `270f948e1e924656a6d75371dc262759` | `partial/finished` |

## 真实请求与响应

### 创建入口

```http
POST /api/projects
Content-Type: application/json
```

请求体为本轮临时项目名称和验收说明，返回 HTTP 201 与 project ID `5c89771c08bc4aa39f8ff84b406cc837`。

```http
POST /api/literature-maps
Content-Type: application/json
```

实际请求体：

```json
{
  "topic": "graph attention networks",
  "name": "Task08 live graph attention networks 24134dce4api",
  "project_id": "5c89771c08bc4aa39f8ff84b406cc837",
  "limit": 20,
  "idempotency_key": "task08-134dce4-24134dce4api-map-create"
}
```

返回 HTTP 202，`map_id=35a56c6f2da84fca85fc3c21dfa0055c`、`job_id=270f948e1e924656a6d75371dc262759`，`requested_count=20`，map 初始 `revision=0`、`status=generating`。

### 状态轨迹

| 时间/观测 | 请求 | HTTP | 实际状态与证据 |
|---|---|---:|---|
| `15:27:24.166508Z` | `GET /api/literature-maps/{map}/jobs/{job}` | 200 | `running/discover`；节点、provider_count 均为 0 |
| `15:27:24.163927Z` | `GET /api/literature-maps/{map}/events?after_seq=0` | 200 | 事件 1–3：queued → started/running/discover |
| `15:27:27.324742Z` | `GET /api/literature-maps/{map}/jobs/{job}` | 200 | `partial/finished`；`provider_request_count=1`，`accepted_count=0`，`node_count=0` |
| `15:27:27.324960Z` | `GET /api/literature-maps/{map}/events?after_seq=3` | 200 | 事件 4：`completed` 事件载荷中的终态为 `partial/finished`，`error_code=SEMANTIC_SCHOLAR_RATE_LIMITED` |
| `15:27:34.188256Z` | `GET /api/literature-maps/{map}` | 200 | map `status=partial`、revision `0`、project 绑定仍为临时 project |
| `15:27:34.191844Z` | `GET /api/literature-maps/{map}/graph` | 200 | `nodes=[]`、`edges=[]`；citation layer `partial/SEMANTIC_SCHOLAR_RATE_LIMITED`，similarity layer `waiting` |

最终 job counts：

```json
{
  "provider_count": 0,
  "accepted_count": 0,
  "node_count": 0,
  "provider_request_count": 1,
  "citation_edge_count": 0,
  "similarity_edge_count": 0
}
```

`failed_units` 仅包含真实 discovery 限流单元：`SEMANTIC_SCHOLAR_RATE_LIMITED`、`retryable=true`、`unit=discover`。本轮没有因为“可重试”而追加第二次 provider 请求，以遵守共享 1 RPS/退避及“核心失败停止”边界。

## 未执行项与原因

下列项目没有被伪造为成功，也没有在核心节点数为 0 后继续发请求：

- 保存视图/重开：没有节点可保存，未调用 `PATCH /view`。
- references preview/确认新增：没有真实来源节点，未调用 `/previews`，没有 candidate/apply ID。
- 引用方向、相似边及 provenance：图为空，不能声称存在关系。
- 摘要 conversation：没有节点，未调用地图会话入口。
- 幂等 apply 与 stale revision CAS：没有 preview，未执行。
- 临时 stop/restart、project 删除解绑、地图删除保护 KB/独立会话：本轮核心 fresh map 已失败；为避免增加 provider 压力，未创建第二张临时地图或人为制造 job。
- 浏览器可打开最终 map：当前 map 无节点且核心 API 门禁失败，不交给人工验收；本轮没有可推荐的成功 map URL。

主会话可在 provider 条件恢复、明确允许新的独立 run 后，再以新 `run_id` 从真实创建入口重跑；不得覆盖本 run，也不得把本轮 `partial` 重解释为成功。当前 fresh map/project/job 仍保留用于诊断，未删除。

## Readiness（本 backend run）

| # | 检查项 | 结果 | 证据 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | PASS | 创建、job、events、map、graph 均取得 HTTP 202/200 |
| 2 | 真实 API 创建入口成功 | PASS（受限） | project 201、map 202、真实 IDs 已落盘 |
| 3 | 参数正确解析 | PASS | topic、project_id、limit=20 被服务回显 |
| 4 | 作业状态推进 | PASS（partial） | queued → running/discover → partial/finished |
| 5 | 前端处理中提示 | N/A（backend run） | 需独立浏览器证据；不能由此报告代替 |
| 6 | 用户等待/点击条件 | N/A（backend run） | 需独立浏览器证据 |
| 7 | 核心业务产物生成 | FAIL | `node_count=0`，graph 无节点/边 |
| 8 | 失败有可操作恢复 | PASS | `SEMANTIC_SCHOLAR_RATE_LIMITED` 且 `retryable=true`，证据保留；恢复需新 run/受控 retry |
| 9 | 页面/API 状态一致 | N/A（无浏览器） | 未执行浏览器 |
| 10 | 无上下文步骤可复现 | PASS（失败路径） | 本报告与 evidence.json 含请求、响应、ID、阶段和停止原因 |

本轮 backend 证据计分为 `PASS=5`、`FAIL=1`、`N/A=4`，且核心 API 产物缺失，因此不能达到 `READY_FOR_USER`。

## 最终裁决

**BLOCKED — `SEMANTIC_SCHOLAR_RATE_LIMITED` 在 discovery 阶段导致真实地图没有任何节点。** 已完成：真实 project/map 创建、HTTP 作业状态与事件观测、map/graph 最终读取。未完成：所有依赖真实节点的地图扩展、保存重开、关系验证、摘要会话和隔离删除案例。需要在 provider 限流条件解除后由主会话授权新的独立 run；本轮不重试、不覆盖、不声称部署成功。

## 受控续查：候选 `1a3ff26`（保留上方失败记录，不覆盖）

在新候选服务 `ready=true` 后，按授权仅对上方既有 map/job 执行了一次公开 retry；没有新建主地图，也没有直连 provider。原失败证据保持不变：

- retry 入口：`POST /api/literature-maps/35a56c6f2da84fca85fc3c21dfa0055c/jobs/270f948e1e924656a6d75371dc262759/retry`，HTTP 200。
- retry 作业最终 `partial/finished`，真实 discovery 产生 20 个节点；计数为 `provider_count=20`、`accepted_count=20`、`node_count=20`、`citation_edge_count=11`、`similarity_edge_count=5`、`provider_request_count=22`。reference 子单元仍真实记录了限流/无效响应，故地图保持 `partial`，没有把 provider partial 伪装成完整成功。
- 真实主题候选图在 apply 后为 21 个节点、17 条边（11 citation + 5 similarity + 1 applied citation），保存视图后 revision 为 3；graph 中保留 provenance/provider、论文外部 ID 和引用方向。示例主节点为 `Graph Attention Networks`，引用方向样例为 `source_id → target_id`，provenance relation 为 `references`。
- references preview：`preview_id=0afcdd83ceb844e2bae89f77102af6d2`，preview job `58db790f57cf4096859667877f741718`，HTTP 202/200，完成候选数 45；确认新增 1 篇候选 `candidate-812a45f9239f2632d20662a0`（`Predicting multicellular function through multi-layer tissue networks`）。apply job `bc9fc2724e1f4f11a4b309fc644df393` 完成，新增 1 节点/1 citation relation；同键重放 HTTP 202 且返回同一 apply job；旧 revision CAS 返回 HTTP 409 / `MAP_CONFLICT`。
- 项目与会话：abstract conversation `f3f469faa8864d2ea8b27bf27471ff00` 通过真实单数 `/nodes/{node_id}/conversation` 创建；地图 PATCH 解绑后 map `project_id=null`，会话 GET 仍保留原项目快照 `5c89771c08bc4aa39f8ff84b406cc837`。
- 删除隔离：临时 project `9b1d87375b294e9b933691b83fe1cd55` 删除 HTTP 204 后，临时 map `932ed9c2b6fc499f941ed95619b937fd` 仍可读且 `project_id=null`；随后临时 map 删除 HTTP 204，map GET 为 404，旧 abstract conversation `4d53f25e00ba4c2d86f08db32113d5c1` GET 仍为 200，共享 KB 文档 `55afc3b8f01445429462fe78ed0d4c98` 删除前后均存在且 indexed。

续查不可覆盖证据：

- [retry evidence（原始请求响应）](runs/20261021-154304-1a3ff26-retry-api/evidence.json)
- [retry postcheck（只读终态，10/10 断言 PASS）](runs/20261021-154559-1a3ff26-retry-postcheck-api/evidence.json)

说明：retry 原始 artifact 的 `apply_job_id` 曾因脚本只读取顶层字段而显示为空，但原始 HTTP response 已包含嵌套 `job.job_id=bc9fc2724e1f4f11a4b309fc644df393` 与 `status=completed`；脚本已修正解析，未重放 retry 或覆盖旧 evidence。只读 postcheck 对 map/job/preview/apply/conversation/删除保护逐项复核，10 项均为 `PASS`。因此本续查结论是 **核心地图 E2E PASS、provider 状态 PARTIAL**，不是完整 provider 成功。

## 受控服务重启恢复：候选 `1a3ff26`

在主会话协调下，新建了与正式验收地图隔离的临时地图，随后由主会话对已验证的 PID `26999` 执行 TERM，并用同一候选重启服务。本 agent 只在重启后调用 GET，不调用 POST、retry 或 stop，也未触碰正式地图 `35a56c6f2da84fca85fc3c21dfa0055c`。

- 临时主题：`graph attention architectures`，`limit=20`。
- 原始实体：`map_id=e567077ddacc495dad8773c8018bc13c`，`job_id=ef5723506184480687a84495d334caff`。
- TERM 前读取：HTTP 200，job 为 `running/discover`，`accepted_count=0`、`node_count=0`、`provider_request_count=0`；事件序列为 1–3（queued → started）。
- 重启后 `/api/ready` 返回 HTTP 200、`ready=true`。同一 map/job 继续运行，恢复追加 event_seq 4 的 `started`，随后持久化推进至 metadata/references/similarity，未生成新 ID。
- 最终读取：map/job/events/graph 全部 HTTP 200；job `partial/finished`，20 nodes、23 edges（10 citation + 13 similarity），`provider_request_count=17`。真实失败单元包含 Semantic Scholar `RATE_LIMITED` 与 `INVALID_RESPONSE`，因此保留 `partial`，未将外部 provider 部分失败伪装为完整成功。
- 恢复断言：事件序列 1–8 单调；节点 ID 20 个无重复；外部身份 20 个无重复；关键持久化计数相对 TERM 前不下降；原 map/job ID 保持不变。结论为 **restart recovery PASS（provider PARTIAL）**，没有 P1 恢复故障。

不可覆盖的脱敏证据（仅 GET 续查，移除 owner/凭据值）：

- [restart recovery evidence](runs/20261021-155409-1a3ff26-restart-recovery/evidence.json)
