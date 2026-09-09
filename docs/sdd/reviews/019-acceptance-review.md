# 019 论文导入状态反馈一致性 — 验收报告

- Spec：`docs/sdd/specs/019-paper-import-status-feedback.md`
- 角色：跨端验收总控（tester 子代理，模型 qwen3.5:9b / hy3）
- 依赖任务：Task03（前端状态单一来源）、Task04（后端错误语义修正），两端评审均通过（P0=0）
- 验收时间：2026-09-10
- 结论：**通过**

---

## 一、验收结论

**通过**。

运行时三类场景（正常导入 / 失败与成功并存 / 三类检索上下文提示互斥）全部以真实 curl 命令验证为预期结果，未出现 spec 明确禁止的 `503 IMPORT_BATCH_UNAVAILABLE` 伪装；前端 P1 修复经静态核对 + 语法检查 + 契约测试确认；遗留项均为非阻塞 P2，按约定不修改业务代码。

---

## 二、验证环境与依据

| 项 | 值 |
|---|---|
| 服务地址 | `http://127.0.0.1:8002`（API 前缀 `/api`） |
| 健康确认 | `GET /api/papers/conferences` → HTTP 200 |
| Python | `.venv/bin/python`（含全部依赖） |
| 数据库 | `data/paper_search/state.sqlite3`（`search_jobs` 23 行，全部 `partial` 且未过期；`search_sessions` 为空） |
| 落盘目录 | `data/kb/papers/`（KB 论文 PDF 落地处） |
| 代码依据 | `backend/app/api/routes_paper.py`、`frontend/app.js` |

方法：① curl 实测三类场景；② 静态 grep 确认旧 503 兜底已移除、前端 P1 修复点；③ `node --check` + 前端契约测试；④ 对不可直接命中的状态（`SEARCH_EXPIRED`/`SEARCH_NOT_READY`）做**可逆临时改库**（UPDATE + `finally` 还原），改库前后 DB 行数与关键字段已确认一致。

---

## 三、三类场景运行时验收（真实命令与输出）

### 场景 1：正常导入（单篇形态）— PASS

命令：
```
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8002/api/papers/imports \
  -H "Content-Type: application/json" \
  -d '{"search_id":"f41e1fd2f5f5414a9d62bf82984b25d4","candidate_id":"0097e978e8e261e08b778db33dc0e657"}'
```
输出：
```
HTTP 200
{"paper_id":"abe90779738541d387733e54fbffc4f0","stored_name":"2025-USENIX-Security-We-Have-a-Package-for-You-A-Comprehensive-Analysis-of-Package-Hallucinations-by-Code-Generating-LLMs.pdf","status":"indexed","error_code":null,"existing":false}
```
- 终态 `status=indexed`、`existing=false`（真实新鲜导入，非已有）。
- 落盘：`data/kb/papers/2025-USENIX-Security-We-Have-a-Package-for-You-...pdf` 存在。
- `GET /api/kb/papers?limit=2000` 解析：共 9 篇，目标 `paper_id=abe90779738541d387733e54fbffc4f0` 存在且 `status=indexed`、`file_name` 与 `stored_name` 一致 → 可见。
- 与后端评审已知样例（USENIX 导入成功）一致。依据 `routes_paper.py:464-500`。

### 场景 2：失败与成功并存 — PASS

S2a（失败候选，不存在的 candidate_id）：
```
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8002/api/papers/imports \
  -H "Content-Type: application/json" \
  -d '{"search_id":"f41e1fd2f5f5414a9d62bf82984b25d4","candidate_id":"no-such-candidate-00000000"}'
```
```
HTTP 404
{"code":"CANDIDATE_NOT_FOUND","message":"候选论文不存在","retryable":false,"request_id":"74ad716b29c04898974c6a1b45dbccbd"}
```

S2b（成功候选，新鲜有效）：
```
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8002/api/papers/imports \
  -H "Content-Type: application/json" \
  -d '{"search_id":"f41e1fd2f5f5414a9d62bf82984b25d4","candidate_id":"00b035bd4d166bff62e637a481c630ea"}'
```
```
HTTP 200
{"paper_id":"b2ec1812dd1e4bfda3e4ae6bb4f9c2ab","stored_name":"2025-USENIX-Security-DarkGram-A-Large-Scale-Analysis-of-Cybercriminal-Activity-Channels-on-Telegram.pdf","status":"indexed","error_code":null,"existing":false}
```

S2c（批量：一个有效 + 一个无效 candidate_id）：
```
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8002/api/papers/imports \
  -H "Content-Type: application/json" \
  -d '{"search_id":"f41e1fd2f5f5414a9d62bf82984b25d4","candidate_ids":["00b035bd4d166bff62e637a481c630ea","no-such-candidate-00000000"],"idempotency_key":"tester-s2c-001"}'
```
```
HTTP 404
{"code":"CANDIDATE_NOT_FOUND","message":"候选论文不存在","retryable":false,"request_id":"96c114c94b2e4690a276af36932b6d77"}
```

静态确认：`grep IMPORT_BATCH_UNAVAILABLE backend/app/api/routes_paper.py` → **0 处引用**（旧 503 兜底已彻底移除，改为 `IMPORT_BATCH_ERROR` 424 + `logger.exception`，见 `:718-722 / :745-749 / :768-772 / :791-795`）。

结论：失败被正确归类为 `CANDIDATE_NOT_FOUND`(404) 精确码，成功为 `200 indexed`，**两者均未被伪装成 503 `IMPORT_BATCH_UNAVAILABLE`**。注：批量形态下不可解析候选会使整批在 resume 阶段报 `CANDIDATE_NOT_FOUND`（非逐条隔离），属既有行为；本次验收重点是错误语义不被 503 掩盖，已达标。

### 场景 3：三类检索上下文提示互斥 — PASS

S3a `SEARCH_NOT_FOUND`（不存在的 search_id，免改库）：
```
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8002/api/papers/imports \
  -H "Content-Type: application/json" \
  -d '{"search_id":"nonexistent-search-xyz-000000","candidate_id":"no-such-candidate-00000000"}'
```
```
HTTP 404
{"code":"SEARCH_NOT_FOUND","message":"搜索会话不存在","retryable":false,"request_id":"881bf125c81e4b309f71cf242d426f7e"}
```
别名 `/api/papers/import-batches` 同参数亦返回 `HTTP 404 SEARCH_NOT_FOUND`。

S3b `SEARCH_EXPIRED`（可逆临时改库：将 job `8a1dcff1...` 的 `expires_at` 改为 `2020-01-01T00:00:00Z` 后 curl，`finally` 还原）：
```
HTTP 400
{"code":"SEARCH_EXPIRED","message":"搜索会话已过期","retryable":false,"request_id":"c7f3f418fa414fad895cce695bb1f52f"}
```
还原确认：`expires_at` 恢复为 `2026-09-10T14:03:24Z`。

S3c `SEARCH_NOT_READY`（可逆临时改库：将 job `c16fcca3...` 的 `status` 改为 `running` 后 curl，`finally` 还原）：
```
HTTP 400
{"code":"SEARCH_NOT_READY","message":"搜索结果尚未冻结","retryable":false,"request_id":"e164cb31eca644a4b3f87c5b13e9de63"}
```
还原确认：`status` 恢复为 `partial`。

三态互斥性：错误码 `404/400/400` 与文案「搜索会话不存在」「搜索会话已过期」「搜索结果尚未冻结」互不混淆。依据 `routes_paper.py:626-629`（`_paper_catalog_import_inputs` 的 NOT_FOUND/NOT_READY 判定）、`:445-447`（单篇路径 EXPIRED 判定）、`_PAPER_BATCH_ERROR_STATUS:503-509` 与 `messages:528-543`。

DB 完整性：改库前后 `search_jobs` 均为 23 行，两个被测 job 原值已恢复，无新增/残留行。

---

## 四、前端 P1 复核（task-05 要求）

grep + node --check + 契约测试：

- `directSuccess`：`frontend/app.js:1021` `paperState.directSuccess = 0;`（每轮 `importPaperCandidates` 起始重置），`:1047` 本轮累加，`:934` `totalSuccess = completedItems + (paperState.directSuccess||0)` 引用本轮值 → **P1-1 已修**。
- `currentRoundBatchIds`：`:1022` 重置为 `new Set()`，`:1045` 本轮创建即入集；`:913-916` `batches = [...paperState.batches.entries()].filter(([id]) => roundBatchIds.has(id))` → 汇总只统计本轮批次 → **P1-2 已修**。
- `node --check frontend/app.js` → `NODE-CHECK: OK`。
- `pytest tests/test_frontend_paper_contract.py -q` → **9 passed**。

结论：前端 P1 两项状态泄漏均已修复并通过语法检查与契约测试。

---

## 五、遗留项清单（后端 P2，非阻塞，不修改业务代码）

以下为后端评审（019-backend-review.md）记录的 P2 建议项，均不阻塞本次验收，按要求**仅记录、不在本次修改**：

- **P2-a｜`CANDIDATE_NOT_FOUND` 状态码与 spec 接口表不一致（404 vs 400）**：`routes_paper.py:507` 与单篇路径 `:458/:462` 返回 404，spec 第 37-38 行标 400。属规格/实现标注澄清项，不影响核心目标。建议后续二选一统一。
- **P2-b｜单篇路径 `session = job` 死赋值**：`routes_paper.py:454`，之后不再读取 `session`，无害冗余。
- **P2-c｜单篇路径两处 `except Exception` 仍静默吞异常未落日志**：`routes_paper.py:459-460`、`:470-471`（`PAPER_DISCOVERY_STORE_UNAVAILABLE`），与本任务"未预期异常必须落日志"宗旨不完全一致，风险低、非回归。
- **P2-d｜单篇路径新增 `CANDIDATE_NOT_FOUND` 分支缺直接测试**：`routes_paper.py:449-453`，批量路径已覆盖语义，风险低。

---

## 六、单端回归结论汇总（引用两端报告）

- 后端：全量 `pytest tests/ -q` → **785 passed**（backend-review 实测佐证；5 处 503 兜底已改为 424 + `logger.exception`，`DATABASE_LOCKED` 仍保留 503 retryable）。
- 前端：契约测试 **9 passed**，`node --check` 通过，四项硬契约（DOM 契约 / `?v=N` / XSS / 无构建）全 PASS（frontend-review + 本次复核）。

---

## 七、签字

- 验收执行：由 tester 子代理（hy3）执行，主 agent 代行开发主管签字。
- 开发主管签字：________________（主 agent 代行）
- 验收日期：2026-09-10
