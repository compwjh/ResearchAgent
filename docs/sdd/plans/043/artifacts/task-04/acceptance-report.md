# PASS_WITH_LIMITATIONS — Task04 阶段验收

日期：2026-10-20
角色：backend-reviewer / Task04 独立阶段验收
范围：Task04 真实 API、真实 Chrome、后端/前端精准验证，以及新增 refresh 空选择写入探针。
明确不做：不改业务代码或测试，不部署，不跑全量，不新增 provider 请求，不把本报告当作 Spec043 最终收口。

> 文中“空选择 no-op P1”是修复前的真实失败证据，保留用于追溯；文末“最终阶段裁定”已基于当前部署的 r2 API 与 9be1707 Chrome 重验覆盖并取代修复前 BLOCK。

## 1. 已完成的真实证据

### 真实 API

- API artifact：[`api-e2e.md`](./api-e2e.md)，JSON：[`api-evidence.json`](./api-evidence.json)，run `task04-api-e2e-20261019T184828Z-r1`。
- `/api/ready` 返回 HTTP 200；真实 HTTP 链路完成 references preview（202→200，45 个候选）、单候选 apply（202）、幂等重放（无重复节点）、refresh preview（200，8 个真实 diff）、stale CAS（409 且无写入）、remove/restore 和最终 graph reopen。
- 最终真实图为 21 nodes / 18 edges；viewport 与既有节点位置保留；原 GAT 节点的 `document_id=55afc3b8f01445429462fe78ed0d4c98`、`download_status=indexed` 保留。
- refresh 的真实 warnings `SEMANTIC_SCHOLAR_INVALID_RESPONSE` 与 `SEMANTIC_SCHOLAR_RATE_LIMITED` 被保留。地图及已有 job 为 `partial`，这是本 Spec 允许的 provider 部分失败状态，不把它误判为完整成功，也不要求本 Task 所有 provider 均无失败。
- 该 API artifact 的运行 revision 是 `a54c119`；后续 `3a99d5f`/`abcad3a` 为前端及验收证据接续。后端 API 证据与当前工作树的关系须由主会话在后续修复重跑时重新固定。

### 真实 Chrome

- [`browser-e2e.md`](./browser-e2e.md) 的 r1 在真实 Chrome 验证了 queue→completed→确认、capacity/duplicate suppression、remove→显式恢复、布局/KB 文档保留；早期 diff formatter 缺陷已修复。
- 最新 run `task04-browser-e2e-20261020-refresh-r3`、revision `abcad3a` 在新 Chrome 会话、无 storage 注入下，点击“打开上次预览”，仅通过服务器事件/job/preview 的 GET 重开 persisted preview。
- 最新浏览器确实显示 8 项真实 diff 的中文字段及 `from → to` 值（如 GAT 引用数 `29000 → 29014`），并显示 21/200 容量、已有候选禁选；indexed 文档入口及 `v1 已索引 · 57 片段` 保留（报告同时记录 v2 已索引 92 片段）。
- 浏览器证据没有伪造新 provider 请求；r3 为只读重开。r1 的“确认刷新”已暴露下面的 P1：UI 显示确认成功，但当 selected list 为空时后端并未应用真实 diff。

## 2. 历史 P1 复现：refresh 空选择确认曾是 no-op（已修复）

### 生产路径与实际代码

- 前端在 refresh 有 diff 时允许空选择并发送真实合同请求：`frontend/literature-maps.js:1188-1194,1434-1451`；payload 的 `selected_candidate_ids` 为空是合法且由真实 UI “确认刷新”触发。
- 服务层 `backend/app/literature_maps/application/service.py:597-629` 只为 selected candidates 构造 `updates`；空选择得到 `updates=[]`。
- Store `backend/app/literature_maps/infrastructure/store.py:764-793` 只遍历 `updates` 写节点，并以 `changed_map = bool(nodes or (updates or []))` 判断是否变更；空选择不更新任何节点或 revision，却继续在 `store.py:795-800` 创建 completed apply job 并把 preview 标为 `applied`。

### 独立真实 SQLite + 实际 API shape probe

命令：

```text
PYTHONPATH=/Users/wjh/ResearchAgent .venv/bin/python /private/tmp/task04_refresh_empty_apply_probe.py
```

退出码 **0**，输出：

```text
EMPTY_REFRESH_APPLY BUG confirmed http_create=202 http_get=200 http_apply=202 diff=10->99 persisted=10 preview=applied revision=0
```

probe 使用生产 FastAPI route/Pydantic 请求 shape 和真实 SQLite 文件，仅将 provider client 替换为确定性 fake，未发真实外部请求：

1. 创建一个已有 `citation_count=10` 的地图节点。
2. 通过实际 `POST /api/literature-maps/{map_id}/previews` 创建 refresh preview，实际 `GET` 返回 diff `citation_count: 10 → 99`。
3. 以实际合同请求 `POST /previews/{preview_id}/apply`、`expected_revision=0`、`selected_candidate_ids=[]` 发送确认。
4. HTTP 返回 **202**，map revision 仍为 0，preview=`applied`、job=`completed`。
5. 重新打开 SQLite，节点仍为 title `Old title`、`citation_count=10`，没有应用 `10 → 99`。

这不是 mock 当作成功：真实 SQLite 持久结果证明“已确认”与实际 metadata 不一致。该事实保留为修复前阻塞证据；随后代码/SQLite 窄复审已验证 10→99、revision 递增、幂等、CAS 与保护字段修复，最终部署闭环见文末。

## 3. 修复前准备度矩阵（历史）

| # | 检查项 | 结果 | 依据 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | PASS | API artifact `/api/ready` HTTP 200；真实 Chrome 页面可访问 |
| 2 | 真实 API 创建/预览入口成功 | PASS | references/refresh 真实 POST→GET，真实 preview/job IDs |
| 3 | 参数与服务端身份正确解析 | PASS | node_id、candidate_id、external IDs、refresh diff node_id/from/to 均来自服务端 |
| 4 | 实体状态推进 | PASS | preview queued/running→completed，apply/remove/restore job 持久完成 |
| 5 | 前端处理中提示 | PASS | Chrome 观察到“预览状态：排队中，候选仍在读取。”→“预览状态：已完成” |
| 6 | 用户知道何时等待/点击 | PASS | “打开上次预览”、 “确认刷新”、容量及 warning 文案均真实可见 |
| 7 | 核心 Task04 产物生成 | PASS | 45 候选、1 新节点、8 real diffs、21/18 图、remove/restore；partial/provider warning 按限制保留 |
| 8 | 失败状态有可操作恢复 | FAIL | CAS409 与 tombstone recovery 可恢复，但 refresh 空选择会返回 202/completed 而不写 diff，形成不可见的 false success |
| 9 | 页面状态与 API/持久数据一致 | FAIL | UI 显示“已确认加入”，但 SQLite 节点 citation_count 仍为 10，preview/job 却为 applied/completed |
| 10 | 无上下文用户可复现步骤 | PASS | API artifact、browser artifact、当前报告均包含入口、真实文案、ID、等待与边界 |

修复前准备度：**8/10 PASS**；该矩阵仅解释历史 BLOCK，不作为当前部署裁定。

## 4. 修复前人工验收边界（历史）

当前不得把用户交给 refresh 确认路径。可复现的诊断步骤是：

1. 打开 `http://127.0.0.1:8000/#literature-maps-view`，选择地图 `0baabeae7268429c9f7e4de8098ae1d0`。
2. 点击“打开上次预览”，等待“预览状态：已完成”，确认看到 8 项真实中文 diff 和 warning。
3. 点击“确认刷新”。当前 UI 可能提示“已确认加入，新增节点正在保存；原有布局不会被重排”，但不能据此断言 metadata 已更新。
4. 以 API GET 或重新打开地图节点核对真实字段；若字段未变而 preview/job 为 applied/completed，即命中本 P1，停止继续验收。

该步骤已由文末 9be1707 Chrome + API r2 只读闭环重新执行；provider partial/warning 仍按限制保留。

## 5. 修复前剩余任务边界（历史）

- **必须先修复并复审 Task04 P1**：refresh 空选择确认必须应用服务端 diff，或拒绝空选择并给出稳定、可操作的错误；不能把 preview 标记 applied 而不写数据。
- 修复后需要重新跑受影响后端精准测试、真实 API probe、真实 Chrome refresh confirm，以及现有 8/10 证据链；不要求 Task04 引入所有 provider 完整成功。
- Task04 其余已验证范围（references preview/apply、幂等、CAS409、remove/restore、布局与 KB 文档、持久 preview 重开）可作为保留证据。
- Task05/06 可继续独立开发，但若依赖 refresh apply 的最终行为，须等待该 P1 修复及重验；Task07/08 仍按原依赖与最终全量门禁执行。
- 本报告不是 Spec043 最终全量验收，不改变 Task03 已确认的 provider partial 或 KB v2 异步限制。

## 修复前最终裁定（历史）

**BLOCK。** Task04 的真实 API 与真实 Chrome 已覆盖主要纵向路径，且 provider partial/warnings 被真实保留；但独立真实 SQLite/API-shape probe 证明 refresh 合法空选择确认会返回成功状态而不应用真实 diff，导致 UI、API 状态与持久数据不一致。该 P1 未修复前，不允许 Task04 阶段验收通过或交给用户完整人工验收。

---

## 6. 当前部署闭环（r2 API + 9be1707 Chrome）

### 真实 API r2

- Follow-up run：`task04-api-e2e-20261020T032543+0800-r2`，`/api/ready` HTTP 200；地图 `0baabeae7268429c9f7e4de8098ae1d0`，未创建新地图。
- refresh preview `3e1c582efb704b188599e8ef805f8dda`：POST 202，GET 200，21 candidates、8 diffs、warning `SEMANTIC_SCHOLAR_INVALID_RESPONSE`。
- Chrome 单次确认后，read-only API GET 观察到 preview `applied`；job `1dc9a2492fdb432491be82efefc3ce46` completed，`added_count=0`、`updated_count=8`、`relation_count=4`。
- revision 从 8 到 9；21 nodes / 18 edges；GAT `29000→29014`、AASIST `674→676`、IoT `76→77`。GAT document/download/position 保持，viewport `{x:10,y:20,scale:1.1}` 保持。
- 真实 SQLite read-only reopen 再次观察 revision 9、18 edges 和上述 metadata，证明不是 UI-only 假状态。
- 原始幂等 key 由前端持有且未暴露，本次 API tester 没有伪造 key 重放；这是当前证据的明确限制。此前真实 API references apply 幂等重放及修复后的 FastAPI+SQLite probe 已覆盖幂等机制，但 refresh 当前部署没有新 key replay 证据。

### 真实 Chrome r4

- Run：`task04-browser-e2e-20261020-refresh-r4`，candidate `9be1707`，真实 Chrome、新 preview 不重复创建。
- “打开上次预览”通过服务器持久事件/job/preview GET 恢复；8 项真实中文 from/to diff 可见，容量 `0/20`、21/200、已有候选禁选。
- 点击“确认刷新”一次，UI GAT 显示 `29014`；随后服务端 GET/SQLite read-only 与 revision 9、updated=8、relation=4 一致。
- provider warning 明确保留，未把 partial 伪装成 provider 全成功；indexed 文档 ID、布局和关系数量保持。

### 历史 P1 与当前闭环关系

修复前的真实失败 `diff=10→99 persisted=10, preview=applied, revision=0` 仍保留在本报告第 2 节；修复后的窄 probe 为 `EMPTY_REFRESH_APPLY_FIXED PASS`，当前部署 r2/r4 又以真实 8 项 diff、revision 8→9、SQLite reopen 进行了闭环确认。因此本 P1 不再是当前阻塞。

## 7. 当前准备度矩阵

| # | 检查项 | 结果 | 当前证据 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | PASS | r2 `/api/ready` HTTP 200；r4 Chrome 可访问 |
| 2 | 真实 API 创建/预览入口成功 | PASS | references 与 refresh 均真实 POST 202→GET 200 |
| 3 | 参数与服务端身份正确解析 | PASS | node/candidate IDs、真实 diff node_id/from/to 均服务端生成 |
| 4 | 实体状态推进 | PASS | queued/running→completed；apply completed；revision 8→9 |
| 5 | 前端处理中提示 | PASS | Chrome 观察排队中→已完成及 provider warning |
| 6 | 用户知道何时等待/点击 | PASS | “打开上次预览”“确认刷新”、容量及 warning 文案可见 |
| 7 | 核心 Task04 产物生成 | PASS_WITH_LIMITATIONS | 45 候选、增 1 节点、8 diff、更新 8/关系 4、remove/restore；地图仍 partial/provider-limited |
| 8 | 失败状态有可操作恢复 | PASS | stale CAS 409、显式 restore、provider warning 保留；旧 no-op 已修复并重验 |
| 9 | 页面状态与 API/持久数据一致 | PASS | UI GAT=29014 与 API/SQLite reopen 一致，布局/doc 保持 |
| 10 | 无上下文用户可复现步骤 | PASS | API/browser artifact 与本报告含真实入口、提示、等待、ID、边界 |

当前严格 PASS **9/10**；第 7 项的 `PASS_WITH_LIMITATIONS` 是继承的 provider partial，不是本 Task 的 P0/P1。

## 8. 命令与退出码

以下为当前修复链受影响范围的已落盘验证，不启动全量回归：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=/Users/wjh/ResearchAgent .venv/bin/python /private/tmp/task04_refresh_empty_apply_fixed_probe.py` | 0 | 10→99、revision=1、幂等、CAS409、保护字段、关系均通过 |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_expansion.py` | 0 | 15 passed |
| `.venv/bin/python -m pytest -q tests/literature_maps` | 0 | 108 passed |
| `.venv/bin/ruff check backend/app/literature_maps/application/service.py backend/app/literature_maps/infrastructure/store.py tests/literature_maps/test_map_expansion.py` | 0 | All checks passed |
| 前端授权 Chromium 精准套件 | 0 | 13 passed，无 skip；地图可行性 3 passed（见 frontend-review） |

## 当前阶段裁定

架构师阶段签字：主会话，2026-10-20 03:32 +08:00。接受以下独立裁定，允许进入Task05/06；不等于Spec最终签字，不抹去旧失败与provider限制。

**PASS_WITH_LIMITATIONS。** Task04 已完成真实 API + Chrome 的 refresh 空选择确认闭环，旧 no-op P1 已真实修复并验证；真实 provider partial/warning 被保留，不被误报成全量成功。允许接续 Task05/Task06 的独立开发与验收准备，但不得将本报告视为 Spec043 最终收口、全量回归签字或无 provider 限制的最终用户交付。refresh 当前部署的原始前端幂等 key 未暴露，未伪造重放；若后续需要 refresh 端到端幂等证据，应由拥有该 key 的真实 UI/API run 单独补证。
