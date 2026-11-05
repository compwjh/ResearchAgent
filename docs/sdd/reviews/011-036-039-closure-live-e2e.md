# Spec 011 / 036 / 039-test-infra 收口 — 当前部署版本真实运行时证据

> **主会话纯文档代行留痕**：本文件只记录运行时证据，不含业务代码改动，
> 不是独立的需求 / 技术 / 验收评审。收口评审与签字由 `architect` 子代理独立承担，
> 结论另见 `docs/sdd/reviews/011-requirement-review.md`、`011-acceptance-review.md` 签字栏
> 与 `docs/sdd/reviews/011-036-039-closure-review.md`。

- 日期：2026-11-05（Asia/Shanghai）
- 服务：`http://127.0.0.1:8000/`，`/api/health` 200；本地 `main` @ `546072e5` 运行时
- 口径说明：本轮是**历史已完成实现的状态补录收口**（011 / 036 / 039-test-infra 的实现代码在 2026-08～09 已完成且此后未变），
  因此按「Task 收口只跑受影响领域测试」执行定向验证，不重跑全量回归；历史全量回归证据见各 spec 原评审报告。

---

## 1. Spec 011 — 本地个人论文知识库（RAG）

**真实成功案例：自然语言提问 → 混合检索 → SSE 生成回答**

请求：

```http
POST /api/kb/ask HTTP/1.1
Content-Type: application/json

{"question":"知识库中关于比特币地址聚类验证的论文主要用了什么方法？","top_k":3,"chunker":"v1"}
```

响应：`HTTP 200`，`content-type: text/event-stream; charset=utf-8`，耗时 68.83s，原始响应 22708 bytes。

落盘产物：`artifacts/spec011-kb-ask-e2e-20261105.sse`

SSE 事件序列（解析自原始响应）：

| 事件 | 数量 / 内容 |
|---|---|
| `meta` | 1，`model=qwen3.8:27b`、`top_k=3`、`chunker=v1` |
| `stage` | 1，`retrieving`「正在检索知识库」 |
| `citations` | 1，含 **3 条真实引用** |
| `token` | 416 |
| `debug` | 1 |
| `done` | 1，`{"type":"done"}`（正常收敛，无 error 事件） |

真实实体 ID / 最终状态：

- 首个命中文档 `document_id = d4dfd2a620384ad5bece27320661f8f0`
  （`How to Peel a Million- Validating and Expanding Bitcoin Clusters.pdf`，`chunk_index=14`，`page=3`）
- 首个命中切片 `chunk_id = 747530eb-08c9-590d-b1ba-a625cbec0443`
- 生成正文累计 858 字符，最终状态 `done`
- 依赖健康：`GET /api/kb/health` → `qdrant=true`、`embedding=true`、`papers=63`、`chunks=16373`、`generation.ready=true`
- 真实已索引文档：`GET /api/kb/documents` → 50 条，`status=indexed`

结论：上传/索引成果已在库中，自然语言问走通「检索 → 引用 → 生成 → done」完整链路，非 mock、非内部函数直调。

---

## 2. Spec 036 — Tool 入口源码只读查看

**真实成功案例：`GET /api/tools/{name}/code` 全量 Tool 逐一读取**

`GET /api/tools` 返回 7 个 Tool：`paper_discovery`、`search_paper_catalog`、`download_and_import_paper`、`fetch_paper_detail`、`kb_search`、`kb_ask`、`session_search`。

逐一请求结果（均为实时 HTTP 200，`code` 非空、`file` 为仓库相对路径）：

| Tool | file | lineno | code 长度 |
|---|---|---:|---:|
| `paper_discovery` | `backend/app/paper_discovery/application/worker_tool.py` | 641 | 684 |
| `search_paper_catalog` | `backend/app/paper_discovery/application/paper_discovery_search.py` | 99 | 4003 |
| `download_and_import_paper` | `backend/app/paper_discovery/application/paper_import.py` | 447 | 9887 |
| `fetch_paper_detail` | `backend/app/paper_discovery/infrastructure/usenix_publication_source.py` | 1170 | 2721 |
| `kb_search` | `backend/app/knowledge_base/infrastructure/retrieve.py` | 139 | 4207 |
| `kb_ask` | `backend/app/api/routes_kb.py` | 988 | 5872 |
| `session_search` | `backend/app/memory/session_search.py` | 395 | 1763 |

7/7 成功；M-01 行号判据由 `036-acceptance-review.md` 历史实测复核（以接口返回值为准，不写死行号）。
`036-acceptance-review.md` §4 已有验收总控与 tech-lead 双签、结论「达到 DoD，可转 `已完成`」；
`docs/sdd/spec-status-changelog.md:397` 亦已记录「已确认 → 已完成」（2026-09-13）。
**本轮缺口仅为 spec 文件自身的状态行与评审记录段未同步。**

---

## 3. Spec 039 — 测试补全与测试基建整理

**真实成功案例：当前 `main` 上的测试布局 / 命名 / 全量收集**

| 命令 | 退出码 | 真实输出 |
|---|---:|---|
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 0 | `test naming check passed: no spec/task numbers under tests` |
| `.venv/bin/python -m pytest --collect-only -q` | 0 | **`3875 tests collected in 4.70s`**（仅 1 条 `swigvarlink` DeprecationWarning） |

历史阻塞已消解：`docs/sdd/plans/039-test-infra-validation.md` 记录的「隔离分支基线缺失 Spec032 文件导致
`2057 tests collected, 37 errors`」是当时 `chore/update-archify` 基线的问题；当前 `main` 全量收集 **0 errors / 3875 collected**，
改名后的定向收集（16 文件 202 passed）与 `node tests/frontend/*.js`（现 15/15）亦持续通过。

结论：改名、分类、命名规则固化（`test-naming` skill 与两个检查脚本）均已在当前部署版本验证通过。

---

## 4. 产物路径

| 内容 | 路径 |
|---|---|
| 本证据文档 | `docs/sdd/reviews/011-036-039-closure-live-e2e.md` |
| 011 原始 SSE 响应 | `artifacts/spec011-kb-ask-e2e-20261105.sse` |
| 011 验收评审（签字栏） | `docs/sdd/reviews/011-acceptance-review.md` |
| 011 需求评审（本轮补） | `docs/sdd/reviews/011-requirement-review.md` |
| 036 验收评审（已双签） | `docs/sdd/reviews/036-acceptance-review.md` |
| 039 测试基建验证报告 | `docs/sdd/plans/039-test-infra-validation.md` |
| 收口评审总控结论（本轮） | `docs/sdd/reviews/011-036-039-closure-review.md` |
| 状态台账 | `docs/sdd/spec-status-changelog.md` |
