> 关联：[spec-019](../../specs/019-paper-import-status-feedback.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`

# Task02 只读定位"搜索会话不存在"真实触发路径

## 状态与一句话目标

`待执行`。只读定位：用户点击"添加到知识库"时为何返回 `SEARCH_NOT_FOUND`，明确**前端传的 `search_id` 是什么、后端为何解析不到**，产出可复现结论与修复点建议。**本任务不改任何业务代码**。

## 背景与前置条件

- 用户反馈：点击"添加到知识库"弹出"搜索会话不存在，请重新检索"。
- 已实测（`data/paper_search/state.sqlite3`）：`search_jobs` 全部 `expires_at` 未到期（状态 `partial`），`search_sessions` 为空 → **不是过期**导致。
- 相关代码：
  - 前端取 id：`frontend/app.js:920`（`paperState.candidateSearchIds.get(candidate.candidate_id) || candidate.search_id`）
  - 前端填充：`frontend/app.js:769`
  - 后端解析：`backend/app/api/routes_paper.py:619-639`（`_paper_server_snapshot`）、`595-616`（`_paper_catalog_import_inputs`）
  - 报错点：`routes_paper.py:605`、`654`
- 前置：spec-019 已确认（本任务在确认后执行）。

## 数据、配置与接口

- 不适用（只读任务，不改数据模型与接口）。
- 观察对象：`search_jobs.search_id / status / expires_at`、`search_results.snapshot`、`search_sessions`；前端 `paperState.searchId`、`candidateSearchIds`。

## 实施步骤与文件边界

1. 只读核查：列出最近若干 `search_jobs` 与其 `expires_at`、状态，确认候选 `candidate_id`（= `catalog_paper_id`）能被子段 615 的 `by_id` 命中。
2. 只读比对：`/api/papers/searches/{search_id}/results` 返回的每条 snapshot 是否带 `search_id` 与 `catalog_paper_id`（对照 `routes_paper.py:611-615`）。
3. 只读复现：用真实 `search_id` + `candidate_id` 调 `POST /api/papers/imports`，记录返回码与 `error.code`；对比"结果页加载后点击"与"直接构造请求"两种情形。
4. 判定三种可能并给出结论：
   - A：前端传的 id 不是 job id（来源错位）→ 修前端取 id；
   - B：snapshot 缺 `catalog_paper_id` 导致 `by_id` 键为 `None` → 修后端快照注入；
   - C：提示语义错误（实际是"未就绪/已过期"却报"不存在"）→ 修后端错误码映射与文案。
5. 产出结论文档（写入本文件"产出物"章节），不改代码。

**文件边界**：只写本 task 文件；禁止修改 `backend/**`、`frontend/**`。

## 子代理分派

- 角色 `tester`（`qwen3.5:9b`）：执行只读核查与复现，单次只产出本 task 的结论回填。
- 最小上下文：spec-019 背景章节 + 上述文件行号 + 本文件。
- 日志：`.codebuddy/agent-logs/spec-019/task-02/tester/<时间戳>.md`。

## 边界与明确不做

- 不做：调整 `search_jobs` 过期时间、清理机制或检索来源逻辑。
- 不做：修改任何错误文案或代码（结论仅用于 Task03/04）。
- 不做：性能优化。

## 验收、风险与回滚

- 验收：结论明确指出 A/B/C 中哪一种（或组合），并给出**可复现的最小请求**与**对应修复点文件行号**。
- 风险：若无法在只读条件下复现，退化为"补充可观测日志"建议并交由 Task04 一并落地。
- 回滚：只读任务，无回滚成本。

## 产出物、执行结果与变更日志

### 结论：假设 **C**（单篇导入路径缺失 `search_jobs` 回退，误报"搜索会话不存在"）

**判定**：用户点击"添加到知识库"触发的是**单篇导入路径** `_import_single_paper`，其仅查询 `search_sessions` 表，
而 catalog-search 的检索上下文只落在 `search_jobs` 表、`search_sessions` 恒为空，于是直接返回
`SEARCH_NOT_FOUND`（"搜索会话不存在"）。批量路径 `_paper_server_snapshot` 在 `session is None` 时会回退
到 `_paper_catalog_import_inputs`（基于 `search_jobs` 解析），故**同一合法 `search_id` 走批量路径不报此错**。
两侧不对称即根因。

### 三种假设逐条核验

- **A（前端传的 search_id 非 job id，来源错位 app.js:920）— 不成立**
  实测：用真实合法 job id（`f41e1fd2…`）调单篇接口仍返回 `SEARCH_NOT_FOUND`；而同一 id 走批量路径能被
  `_paper_catalog_import_inputs` 正常解析（`get_search_job` 命中）。且 `normalizePaperResult`(app.js:708-718)
  已把 `candidate.search_id` 补全为结果页合法 job id，`candidateSearchIds` 也以 `catalog_paper_id` 为键存了
  合法 job id。说明前端传入的 `search_id` 是合法 job id，来源未错位。
- **B（snapshot 缺 catalog_paper_id → by_id 键为 None）— 不成立**
  实测：`search_results.snapshot_json` 含有真实 `catalog_paper_id`（`_paper_catalog_import_inputs` 行 612 还
  有 `getattr(result,"catalog_paper_id")` 兜底），`by_id` 键非 None。且单篇路径在 routes_paper.py:433-435 已
  返回，**根本未触及候选解析**，故非 B。
- **C（提示语义错误，数据存在却报"不存在"）— 成立（精确机制为代码分支错误）**
  检索上下文以 `search_job` 存在且未过期，但单篇路径只查 `search_sessions`（该表对 catalog-search 恒空），
  缺失批量路径已有的 job 回退，于是把"无 server 会话"误报为"搜索会话不存在"。用户可见现象与 C 一致。

### 修复点（仅定位，未修改；交给 Task04/03）

- **主修复点**：`backend/app/api/routes_paper.py:433-435` —— `_import_single_paper` 中
  `session = store.get_search_session(request.search_id); if session is None: return _paper_api_error(404, "SEARCH_NOT_FOUND", "搜索会话不存在")`。
  应改为：当 `session is None` 时回退 `_paper_catalog_import_inputs(store, request.search_id, [request.candidate_id])`
  （与 `_paper_server_snapshot` 行 622-624 同构），再从 `by_id[request.candidate_id]` 取候选；仅当
  `get_search_job` 也为 None 时才返回 `SEARCH_NOT_FOUND`。
- 配套：行 438 `candidate = store.get_candidate(request.search_id, request.candidate_id)` 依赖 session，
  回退 job 后候选应改由 `by_id` 取得（参考行 627/659-664）。
- 非本次修复范围：行 697 批量路径 `except Exception` 的 503 `IMPORT_BATCH_UNAVAILABLE` 兜底（(a) 复现里批量的
  503 来自 `create_batch` 后续阶段，与"搜索会话不存在"无关，属 spec-019 背景点 3 的 503 兜底问题，归 Task04）。

### 执行的真实命令与输出

```bash
# DB 只读核查（.venv/bin/python）
# search_jobs 全部 status=partial、expires_at 未到期；search_sessions COUNT(*)=0；
# search_results.snapshot_json 字段集不含 search_id/candidate_id，含 catalog_paper_id（真实值）。

# 复现 (a) 批量形态：合法 search_id + candidate_ids=[catalog_paper_id]
curl -X POST http://127.0.0.1:8002/api/papers/imports \
  -d '{"search_id":"f41e1fd2f5f5414a9d62bf82984b25d4","candidate_ids":["9f737c445e6c1001e7323f9276114356"]}'
# => HTTP 503 IMPORT_BATCH_UNAVAILABLE（批量路径 job 解析回退成功，未报 SEARCH_NOT_FOUND）

# 复现 (a2) 单篇形态：合法 search_id + candidate_id（= 用户点"添加到知识库"的真实请求）
curl -X POST http://127.0.0.1:8002/api/papers/imports \
  -d '{"search_id":"f41e1fd2f5f5414a9d62bf82984b25d4","candidate_id":"9f737c445e6c1001e7323f9276114356"}'
# => HTTP 404 {"code":"SEARCH_NOT_FOUND","message":"搜索会话不存在","retryable":false}

# 复现 (b) 故意不存在的 search_id
curl -X POST http://127.0.0.1:8002/api/papers/imports \
  -d '{"search_id":"DEADBEEFNOTREAL","candidate_ids":["9f737c445e6c1001e7323f9276114356"]}'
# => HTTP 404 SEARCH_NOT_FOUND（对照预期）
```

### 可复现的最小请求（即用户真实触发路径）

```
POST /api/papers/imports
Content-Type: application/json
{ "search_id": "<任意合法 search_jobs.search_id>", "candidate_id": "<该 job 下任一 search_results.catalog_paper_id>" }
```
> 因单篇形态被路由到 `_import_single_paper`（routes_paper.py:701-705 按 `PaperImportRequest` 分发），
> 而该函数只查 `search_sessions`（恒空），故对任意未过期的合法 catalog-search job 都会稳定返回
> `404 SEARCH_NOT_FOUND` "搜索会话不存在"。前端"添加到知识库"单篇按钮（app.js:936）正是发送此形态。

### 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-09 | tester(qwen3.5:9b) | 只读定位"搜索会话不存在"真实触发路径：结论 C；根因在 `_import_single_paper`(routes_paper.py:433-435) 缺 `search_jobs` 回退；未改任何业务代码 |
