# Spec-049 —— API 成功产物样例

生成时间：2026-11-13  
服务：`http://127.0.0.1:8000`（已在运行）  
采集方式：`curl -s -i <url>`；响应头、状态码、响应体全文原样保留。

---

## 1. 真实请求与响应

### 1.1 `GET /api/health`

请求行：

```bash
curl -s -i http://127.0.0.1:8000/api/health
```

响应（原样）：

```http
HTTP/1.1 200 OK
date: Fri, 13 Nov 2026 08:37:35 GMT
server: uvicorn
content-length: 327
content-type: application/json

{"status":"ok","model":"qwen3.8:27b","models":["qwen3.8:27b-q4_K_M","qwen3.8:27b-mlx","qwen3.8-27b-q4:latest","qwen3.8:27b","oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU","qwen3.8:27b-q4","dengcao/Qwen3-Reranker-0.6B:Q8_0","bge-m3:latest","deepseek-coder-v2:16b","qwen3.5:9b","deepseek-coder:33b"],"paper_discovery_enabled":true}
```

### 1.2 `GET /api/literature-maps/tags`

请求行：

```bash
curl -s -i http://127.0.0.1:8000/api/literature-maps/tags
```

响应（原样）：

```http
HTTP/1.1 200 OK
date: Fri, 13 Nov 2026 08:37:35 GMT
server: uvicorn
content-length: 48
content-type: application/json

{"schema_version":"literature-map-v1","tags":[]}
```

### 1.3 `GET /api/projects`

请求行：

```bash
curl -s -i http://127.0.0.1:8000/api/projects
```

响应（原样）：

```http
HTTP/1.1 200 OK
date: Fri, 13 Nov 2026 08:37:35 GMT
server: uvicorn
content-length: 948
content-type: application/json

{"projects":[{"project_id":"a4a1745f801441188dc1f75b0534be11","owner_id":"local-user","name":"文件记忆验收 20261026","instructions":null,"status":"active","created_at":"2026-10-26T02:02:36.684346+00:00","updated_at":"2026-10-26T02:02:36.684346+00:00","last_activity_at":"2026-10-26T02:12:55.037537+00:00"},{"project_id":"5c89771c08bc4aa39f8ff84b406cc837","owner_id":"local-user","name":"Task08 live project 24134dce4api","instructions":"temporary Spec043 acceptance scope","status":"active","created_at":"2026-10-21T15:27:24.156717+00:00","updated_at":"2026-10-21T15:27:24.156717+00:00","last_activity_at":"2026-10-21T15:44:24.456786+00:00"},{"project_id":"fb64e3d3bcde4f9b80e5cb5548c2bebd","owner_id":"local-user","name":"AI Agent","instructions":null,"status":"active","created_at":"2026-09-11T02:14:33.958153+00:00","updated_at":"2026-09-11T02:14:33.958153+00:00","last_activity_at":"2026-09-11T02:14:33.958153+00:00"}],"next_cursor":null}
```

### 1.4 `GET /api/literature-maps`

请求行：

```bash
curl -s -i http://127.0.0.1:8000/api/literature-maps
```

响应（原样）：

```http
HTTP/1.1 200 OK
date: Fri, 13 Nov 2026 08:37:35 GMT
server: uvicorn
content-length: 4617
content-type: application/json

{"schema_version":"literature-map-v1","maps":[{"map_id":"4ef8c03bffe24797acb090f4095a3a28","name":"地图易用性官方目录验证 task10-official-20261027-130257","topic":"fuzzing vulnerability discovery","owner_id":"local-user","project_id":null,"filters":{"conference_ids":["usenix-security"],"source_ids":["usenix"],"year_end":2024,"year_start":2024},"requested_count":20,"revision":1,"status":"partial","view_settings":{"label_mode":"all","layers":{"citation":true,"similarity":true},"node_style":{"fill_mode":"filled","fill_opacity":0.3},"view_initialized":true,"viewport":{"scale":0.35,"x":327.77162475585936,"y":183.03155364990238}},"created_at":"2026-10-27T05:02:57.624251+00:00","updated_at":"2026-11-07T10:43:39.236256+00:00","node_count":0,"tags":[]},{"map_id":"0baabeae7268429c9f7e4de8098ae1d0","name":"API E2E graph attention networks r2","topic":"graph attention networks","owner_id":"local-user","project_id":null,"filters":{"conference_ids":[],"source_ids":[],"year_end":null,"year_start":null},"requested_count":20,"revision":361,"status":"partial","view_settings":{"label_mode":"all","layers":{"citation":true,"similarity":true},"node_style":{"fill_mode":"filled","fill_opacity":0.5},"view_initialized":true,"viewport":{"scale":0.6820509850000009,"x":76.67858180495284,"y":254.19459813857404}},"created_at":"2026-10-19T14:06:06.042255+00:00","updated_at":"2026-11-07T10:43:07.431052+00:00","node_count":32,"tags":[]},{"map_id":"3853926bb0cc4a71ba49c50afdf04522","name":"地图易用性 API 验证 task10-smoke-20261027-125456","topic":"graph attention networks","owner_id":"local-user","project_id":null,"filters":{"conference_ids":[],"source_ids":[],"year_end":null,"year_start":null},"requested_count":20,"revision":0,"status":"partial","view_settings":{"label_mode":"all","layers":{"citation":true,"similarity":true},"node_style":{"fill_mode":"filled","fill_opacity":0.3},"viewport":{"scale":1,"x":0,"y":0}},"created_at":"2026-10-27T04:54:56.603943+00:00","updated_at":"2026-10-27T04:57:59.185457+00:00","node_count":0,"tags":[]},{"map_id":"35a56c6f2da84fca85fc3c21dfa0055c","name":"Task08 live graph attention networks 24134dce4api","topic":"graph attention networks","owner_id":"local-user","project_id":null,"filters":{"conference_ids":[],"source_ids":[],"year_end":null,"year_start":null},"requested_count":20,"revision":15,"status":"partial","view_settings":{"label_mode":"all","layers":{"citation":true,"similarity":true},"viewport":{"scale":1.0984499318523517,"x":111.72381974909865,"y":193.41714005559183},"node_style":{"fill_mode":"filled","fill_opacity":0.3}},"created_at":"2026-10-21T15:27:24.162911+00:00","updated_at":"2026-10-27T04:50:07.562370+00:00","node_count":21,"tags":[]},{"map_id":"858b78f0d9e047efa6d8d1559d83a6de","name":"Task09 live graph attention networks 20261024-153416","topic":"graph attention networks","owner_id":"local-user","project_id":null,"filters":{"conference_ids":[],"source_ids":[],"year_end":null,"year_start":null},"requested_count":20,"revision":37,"status":"partial","view_settings":{"label_mode":"all","layers":{"citation":true,"similarity":true},"viewport":{"scale":2.8,"x":-1003.445228693449,"y":-1607.767842086919},"node_style":{"fill_mode":"filled","fill_opacity":0.3}},"created_at":"2026-10-24T07:34:44.819896+00:00","updated_at":"2026-10-26T16:11:14.095351+00:00","node_count":20,"tags":[]},{"map_id":"e567077ddacc495dad8773c8018bc13c","name":"Task08 restart recovery 1a3ff26","topic":"graph attention architectures","owner_id":"local-user","project_id":null,"filters":{"conference_ids":[],"source_ids":[],"year_end":null,"year_start":null},"requested_count":20,"revision":12,"status":"partial","view_settings":{"layers":{"citation":true,"similarity":true},"viewport":{"scale":0.6702977382336576,"x":-503.56640625,"y":-1033.8046875},"label_mode":"all","node_style":{"fill_mode":"filled","fill_opacity":0.3}},"created_at":"2026-10-21T15:52:16.546582+00:00","updated_at":"2026-10-22T17:23:11.673774+00:00","node_count":20,"tags":[]},{"map_id":"9b1e4739443e40c98400cfb69aec1e45","name":"API E2E graph attention networks","topic":"graph attention networks","owner_id":"local-user","project_id":null,"filters":{"conference_ids":[],"source_ids":[],"year_end":null,"year_start":null},"requested_count":20,"revision":11,"status":"partial","view_settings":{"layers":{"citation":false,"similarity":false},"viewport":{"scale":1.44,"x":-60.0,"y":-60.0},"label_mode":"all","node_style":{"fill_mode":"filled","fill_opacity":0.3}},"created_at":"2026-10-19T13:36:32.318576+00:00","updated_at":"2026-10-19T14:07:42.719994+00:00","node_count":20,"tags":[]}]}
```

---

## 2. 响应 JSON 关键字段 / 实体 ID

| 字段 | 值 | 来源 |
|---|---|---|
| `schema_version` | `literature-map-v1` | `GET /api/literature-maps/tags`、`GET /api/literature-maps` |
| `project_id` | `a4a1745f801441188dc1f75b0534be11` | `GET /api/projects` |
| `map_id` | `4ef8c03bffe24797acb090f4095a3a28` | `GET /api/literature-maps`（E2E 刷新时捕获） |
| E2E 结论 | `passed/total/failed_checks/conclusion` = `31/31/[]/PASS` | `docs/sdd/plans/049/runs/task-04/browser-e2e.json` |

---

## 3. 最终状态（刷新后）

- 状态栏文案：`选择一张地图查看已保存的图谱。`（`browser-e2e.json` `status_bar_after_refresh`）。
- `is-spinning` 已移除：三轮 `spin_add_events=1` / `spin_remove_events=1`；连点 3 次 `spin_residue=0`；`no_unhandled_rejection=true`、`page_errors=[]`。
- 真实耗时（`elapsed_ms` / `spin_duration_ms_js`）：desktop-native `2521.27` / `2205.4`；desktop-throttled-250ms `299.03` / `256.4`；mobile `1699.06` / `1680.8`。
- 刷新链路真实响应：连点 3 次 `GET /api/literature-maps` 状态码 `[200, 200, 200]`。

---

## 4. 部署验证（真实状态码）

| URL | HTTP |
|---|---|
| `/api/health` | `200` |
| `/` | `200` |
| `/assets/literature-maps.js?v=49` | `200` |
| `/assets/literature-maps.css?v=36` | `200` |
| live `<script>` | `/assets/literature-maps.js?v=49` |
| live `<link>` | `/assets/literature-maps.css?v=36` |
| 末尾 marker（最后一次出现） | `js?v=47` / `css?v=34` |
| `conclusion` | `PASS` |

---

## 5. 产物路径

- E2E JSON：`docs/sdd/plans/049/runs/task-04/browser-e2e.json`
- 首跑原始证据：`docs/sdd/plans/049/runs/task-04/browser-e2e-run1.json`
- 截图：`docs/sdd/plans/049/runs/task-04/refresh-desktop.png`、`docs/sdd/plans/049/runs/task-04/refresh-mobile.png`
- 部署验证 JSON：`docs/sdd/plans/049/runs/task-04/deploy-verification.json`
- 单端回归报告：`docs/sdd/plans/049/runs/task-04/frontend-regression.md`
- 代码评审：`docs/sdd/reviews/049-frontend-review.md`

---

## 6. 调用约束 / 已知限制

- `browser-e2e.json` `console_errors` 共 8 条，去重文案 1 种：`Failed to load resource: the server responded with a status of 404 (Not Found)`；明细见该文件。
- E2E 捕获的 `/api/` 响应中非 200 项共 4 个去重 URL：
  - `http://127.0.0.1:8000/api/conversations/271aade840684c48b2b3188fe690b6dc` → `404`
  - `http://127.0.0.1:8000/api/conversations/05122fc2af7a49259b33c9867d331793` → `404`
  - `http://127.0.0.1:8000/api/conversations/cfaa2bcc133c4a04892197d4a0aa9a0d` → `404`
  - `http://127.0.0.1:8000/api/conversations/e06d6635a7bc4adc9629dfb548854bb9` → `404`
- `page_errors=[]`、`unhandled_rejection_count=0`、`no_pageerror=true`。
- 首跑原始证据 `browser-e2e-run1.json`：`28/29`、`failed_checks=["spin_not_fixed_700ms"]`、`conclusion=FAIL`；正式证据 `browser-e2e.json`：`31/31`、`conclusion=PASS`。
- 全量回归输出 `docs/sdd/plans/049/runs/task-04/full-regression.txt` 由后续 Gate 5 汇总，本次不等待、不判定。

