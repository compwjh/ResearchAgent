# BLOCK — Task04 阶段验收

日期：2026-10-20
角色：backend-reviewer / Task04 独立阶段验收
范围：Task04 真实 API、真实 Chrome、后端/前端精准验证，以及新增 refresh 空选择写入探针。
明确不做：不改业务代码或测试，不部署，不跑全量，不新增 provider 请求，不把本报告当作 Spec043 最终收口。

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

## 2. 新发现的 P1 阻塞：refresh 空选择确认是 no-op

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

这不是 mock 当作成功：真实 SQLite 持久结果证明“已确认”与实际 metadata 不一致。它直接违反 Task04 合同“refresh preview 差异经确认后应用”，因此在修复和重跑前不能阶段通过。

## 3. 准备度矩阵

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

准备度：**8/10 PASS**，但存在未解决 P1，因此不满足交付门禁。

## 4. 人工验收边界与恢复

当前不得把用户交给 refresh 确认路径。可复现的诊断步骤是：

1. 打开 `http://127.0.0.1:8000/#literature-maps-view`，选择地图 `0baabeae7268429c9f7e4de8098ae1d0`。
2. 点击“打开上次预览”，等待“预览状态：已完成”，确认看到 8 项真实中文 diff 和 warning。
3. 点击“确认刷新”。当前 UI 可能提示“已确认加入，新增节点正在保存；原有布局不会被重排”，但不能据此断言 metadata 已更新。
4. 以 API GET 或重新打开地图节点核对真实字段；若字段未变而 preview/job 为 applied/completed，即命中本 P1，停止继续验收。

修复后必须重新执行：refresh preview→空选择确认→GET 节点/graph 的真实 API 链路，并在 Chrome 核对确认后的 citation/title 等实际值；同时保留 provider partial/warning，不把 warning 当作全量成功。失败恢复应明确为重新读取并重新预览，不能自动重放覆盖用户变化。

## 5. 剩余任务边界

- **必须先修复并复审 Task04 P1**：refresh 空选择确认必须应用服务端 diff，或拒绝空选择并给出稳定、可操作的错误；不能把 preview 标记 applied 而不写数据。
- 修复后需要重新跑受影响后端精准测试、真实 API probe、真实 Chrome refresh confirm，以及现有 8/10 证据链；不要求 Task04 引入所有 provider 完整成功。
- Task04 其余已验证范围（references preview/apply、幂等、CAS409、remove/restore、布局与 KB 文档、持久 preview 重开）可作为保留证据。
- Task05/06 可继续独立开发，但若依赖 refresh apply 的最终行为，须等待该 P1 修复及重验；Task07/08 仍按原依赖与最终全量门禁执行。
- 本报告不是 Spec043 最终全量验收，不改变 Task03 已确认的 provider partial 或 KB v2 异步限制。

## 最终裁定

**BLOCK。** Task04 的真实 API 与真实 Chrome 已覆盖主要纵向路径，且 provider partial/warnings 被真实保留；但独立真实 SQLite/API-shape probe 证明 refresh 合法空选择确认会返回成功状态而不应用真实 diff，导致 UI、API 状态与持久数据不一致。该 P1 未修复前，不允许 Task04 阶段验收通过或交给用户完整人工验收。
