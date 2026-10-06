# BLOCKED — Spec018 当前 API E2E 验收报告

## 1. 运行范围与结论

- **Spec / Task**：Spec018 / Task07，tester 真实 API E2E 补验
- **run_id**：`spec018-api-e2e-20261006T133558Z`
- **服务**：`http://127.0.0.1:8000`
- **时间**：2026-10-06 13:35:58Z–13:40:22Z
- **HTTP 客户端**：`httpx.Client(trust_env=False)`；未使用 mock、fixture 替代 API、内部函数或浏览器绕过
- **授权范围**：允许创建本轮独立 Markdown/PDF 样本；不删除、不重建已有用户文档
- **实际动作**：Markdown upload 两次（第二次仅为捕获稳定错误字段），固定 PDF upload 一次；其余仅 GET

最终结论为 **`BLOCKED`**：canonical `POST /api/kb/documents/upload` 对两个新样本均返回 `400 MIGRATION_INPUT_INVALID`，没有返回新 `document_id`。因此不能伪造或借用已有文档来声称“新上传 → 状态轮询 → v1/v2 inspection → source”链路成功。

结构化脱敏证据见：[current-api-e2e-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-evidence.json)。本报告和证据均不包含样本文本、PDF 正文、完整 source hash、Cookie、授权头或完整 request id。

## 2. API E2E Artifact

### 2.1 前置健康与 readiness 边界

| 请求 | 状态 | 观察值 |
|---|---:|---|
| `GET /api/health` | `200` | `status=ok` |
| `GET /api/kb/health` | `200` | `generation.ready=true`、`generation.error_code=null`、`qdrant=true`、`embedding=false` |
| `GET /api/ready` | `200` | `ready=true`；`warmup.embedding.status=failed`、`error=timeout after 30s`；Qdrant/jieba/Ollama tags warmup 为 `ready` |

`ready=true` 不被当作 embedding 已预热的证明；本 tester 没有调用内部 embedding 函数，也没有为上传主动请求 embedding。generation/Qdrant 的读路径条件满足，但 embedding warmup 失败仍作为运行时风险保留。

### 2.2 本轮样本

| 样本 | 本地路径 | multipart 文件名 | MIME | 字节数 | SHA-256 前缀 |
|---|---|---|---|---:|---|
| Markdown | `/private/tmp/spec018-e2e-markdown-20261006-213558.md` | `spec018-e2e-markdown-20261006-213558.md` | `text/markdown` | 576 | `be0190595ad4` |
| 固定 PDF | `/Users/wjh/ResearchAgent/docs/sdd/fixtures/spec-018/pdf-single-column-v1.pdf` | `spec018-e2e-pdf-single-column-v1.pdf` | `application/pdf` | 1551 | `3cc6b61497f4` |

Markdown 是本轮创建的日期唯一小样本，内容只覆盖 heading/paragraph/list/table/quote/fenced-code 边界，不含隐私。PDF 使用现有 Spec018 固定 fixture；本轮只读取该 fixture 并作为 multipart 内容发送。

### 2.3 真实上传请求与响应

所有请求均为真实 multipart `POST`，字段名为 `file`，没有附带 `project_id`，服务响应如下：

| case | 请求 | HTTP | 稳定错误 | retryable | 新 `document_id` |
|---|---|---:|---|---|---|
| markdown-initial | `POST /api/kb/documents/upload` | `400` | `MIGRATION_INPUT_INVALID` | `false` | 无 |
| markdown-error-capture-retry | 同上 | `400` | `MIGRATION_INPUT_INVALID` | `false` | 无 |
| fixed-pdf | `POST /api/kb/documents/upload` | `400` | `MIGRATION_INPUT_INVALID` | `false` | 无 |

响应含 `request_id` 字段（仅记录其存在，不落盘具体值）；没有 `task_id`、`Location` 或成功响应体。第二次 Markdown 请求不是无限重试，而是为保留同一稳定错误的可复核字段；收到同样的非 retryable 400 后停止上传尝试。

### 2.4 失败后无半截记录核对

为验证上传失败没有创建用户实体，执行只读请求：

```text
GET /api/kb/documents?limit=100 → HTTP 200
total=40, page_count=40, next_cursor=null
新 Markdown 文件名存在=false
新 PDF 文件名存在=false
ETag 存在=true
```

因此本轮没有可合法轮询的 `document_id`，也没有触碰已有用户文档。

### 2.5 静态诊断（只读，不作为内部 E2E 替代）

对 `data/kb/papers.json` 和冻结 `knowledge-document.schema.json` 做了只读 schema 对照：共 40 条记录，13 条含 schema 禁止的 `auto_requeued_chunkers` 字段，重复 `document_id` 数为 0。`MIGRATION_INPUT_INVALID` 与严格 metadata 校验失败相符；由于服务没有返回更细的稳定子码，本项是根因诊断而不是伪造的堆栈结论。

本轮没有修正该 metadata、没有改 schema、没有重启或重建服务。上传失败后立即停止新实体 E2E，不用已有 d4df 文档的 inspection 结果掩盖创建入口失败。

## 3. 未执行项与停止依据

以下步骤要求先取得本轮新 `document_id`，本轮全部记为未执行：

- 新 ID 状态轮询（v1/v2）；
- 新 ID 的 `GET .../inspection?chunker=v1` 与 `chunker=v2`；
- 新 ID 的非空 anchors 验证；
- 新 ID 的 source `HEAD`、单 Range `206`、ETag/Content-Range 核对；
- 新 ID 最终产物路径与 UI 查看路径核对。

停止原因是上传返回 non-retryable `400 MIGRATION_INPUT_INVALID` 且没有实体句柄。继续轮询既无目标，也不能构成真实 E2E 证据；改用旧文档则改变验收问题。

已有 d4df 只读 inspection、Range 和 generation 证据仍保留在 [current-runtime-readonly-report.md](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-runtime-readonly-report.md)，但不计入本轮新上传链路成功。

## 4. Readiness Matrix

| # | 门项 | 结果 | 证据/原因 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | **PASS** | health 与 kb health 均 HTTP 200 |
| 2 | 真实 API 创建入口成功 | **FAIL** | Markdown/PDF upload 均 400 `MIGRATION_INPUT_INVALID` |
| 3 | 主路径参数被正确解析 | **FAIL** | multipart 类型与字段被接收，但创建入口没有返回实体成功体 |
| 4 | 任务/实体状态从初始态推进 | **FAIL** | 无新 `document_id`/`task_id`，无法开始状态追踪 |
| 5 | 前端显示处理中提示 | **FAIL** | 上传未接受，未进入前端处理态；本轮未用历史 UI 证据替代 |
| 6 | 用户知道何时点击或等待 | **FAIL** | 新上传没有可等待的任务句柄 |
| 7 | 核心业务产物真实生成 | **FAIL** | 新样本没有 inspection manifest/anchors/source 产物 |
| 8 | 失败状态有可操作恢复 | **FAIL** | 稳定错误可诊断，但当前服务没有给出可由用户完成的恢复入口；需修复 metadata 校验阻塞后重试 |
| 9 | 页面状态与 API 状态一致 | **FAIL** | 当前上传路径未产生页面实体，无法比对页面与 API 状态 |
| 10 | 步骤文档可由无上下文用户复现 | **FAIL** | 失败路径可复现，但成功验收路径缺少新实体、inspection 和 source 证据 |

**计分：1/10 PASS。** 任一真实创建入口失败时，根据验收协议不得交付用户人工验收。

## 5. Final Decision

**`BLOCKED`**

解除本轮阻塞需要负责实现角色先处理严格 metadata 校验与 `auto_requeued_chunkers` schema 漂移，或提供等价的已验证修复；随后在不删除既有文档的前提下重新运行本轮独立 Markdown/PDF upload。只有获得真实新 `document_id` 后，才继续轮询两个 chunker 至可观察终态，并验证 v1/v2 非空 anchors、source HEAD/Range/ETag 与 UI 产物。

本报告不授权删除、reindex、manifest rebuild、Qdrant 切换或修改用户数据。
