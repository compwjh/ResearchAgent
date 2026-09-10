# Spec018 Task06F-A：PDF 上传失败与错误可见性修复报告

## 结果状态

```text
task=06F-A
result=IMPLEMENTED-IN-ISOLATION-AND-VERIFIED
historical_400_reproduced=false
valid_pdf_common_multipart=pass
invalid_pdf_non_pdf_rejection=pass
frontend_error_visibility=pass
real_data_or_qdrant_touched=false
```

当前限定 diff 已完成最小上传兼容与错误可见性修复；本轮没有凭历史日志猜定单一根因。历史日志只记录 HTTP 400 且没有响应体，无法区分 multipart、MIME、文件头或业务失败；在受控 TestClient 矩阵中未复现无响应体 400。

## 改动文件

- `backend/app/api/routes_kb.py`
  - 对上传 part 的 MIME 做大小写、参数和空值规范化。
  - PDF 允许常见的 `application/pdf`、带参数、`application/x-pdf`、`application/octet-stream`、`binary/octet-stream` 和缺失 part MIME；仍由 application 的 `%PDF-` 魔数校验决定内容是否合法。
  - Markdown 仍要求 `text/markdown`；扩展名、MIME、容量和文件头失败均走 `_document_error` 稳定 JSON。
- `backend/app/knowledge_base/infrastructure/document_read.py`
  - PDF 魔数保持严格 `%PDF-`，不接受空文件、裸 `%PDF` 或伪造 `%PDFx`。
- `frontend/app.js`
  - 上传失败优先展示后端 `message` 与 `error_code`，兼容旧 `detail` 作为最后回退；JSON 解析失败也显示受控默认错误。
- `tests/test_kb_document_routes.py`
  - 覆盖 canonical upload 的常见 PDF multipart MIME、MIME 参数和非 PDF MIME 拒绝。
- `tests/test_kb_document_foundation.py`
  - 覆盖严格 PDF 版本魔数。
- `tests/test_frontend_paper_contract.py`
  - 覆盖前端使用 `message`/`error_code` 而非只读取 `detail`。

未新增上传、存储或索引实现；canonical `/api/kb/documents/upload` 与兼容 `/api/kb/upload` 继续调用同一个 `create_uploaded_document` application seam。未修改 Qdrant、embedding、论文下载或用户数据。

## 受控复现矩阵与 API 细节

| 请求 | 结果 | 响应/行为 |
|---|---:|---|
| `.pdf` + 合法 `%PDF-1.7`，part MIME 缺失 | 201 | 统一 immutable upload seam，返回 `document_id/media_type/file_name/source_sha256/status/chunkers/task_id` |
| `.pdf` + 合法 `%PDF-1.7`，`application/pdf`、带参数、`application/x-pdf`、`application/octet-stream`、`binary/octet-stream` | 201 | 两个 upload 路径均通过，未改写请求体或文件名 |
| `.pdf` + 非 PDF bytes | 400 `INVALID_PDF` | 返回 `error_code/message/retryable/request_id`，不进入成功写入 |
| 空 `.pdf` | 400 `INVALID_PDF` | 稳定 JSON，不含 `detail` |
| `.txt` 或其他非 PDF/Markdown 扩展名 | 415 `UNSUPPORTED_MEDIA_TYPE` | 在 application seam 前拒绝 |
| `.pdf` + `text/plain` | 415 `UNSUPPORTED_MEDIA_TYPE` | 即使魔数合法也拒绝非 PDF MIME |
| 缺 `file` 或 malformed multipart | 400 `INVALID_REQUEST` | 稳定 JSON，含 `message` 与 `error_code` |

失败响应继续使用统一形状：`{error_code,message,retryable,request_id,...}`。上传成功仍返回 201；不新增 ETag、任务或索引协议。浏览器 `FormData` 不手工设置整体 `Content-Type`，由浏览器生成 boundary；当前前端上传路径保持该行为。

## 决策依据

1. Spec018 冻结了 `.pdf`/`.md` 扩展名边界、PDF `%PDF-` 魔数、统一错误体和 immutable application seam；因此只兼容常见 multipart part MIME，不接受任意 MIME 或任意字节。
2. 受控矩阵证明当前严格 MIME 等值比较会拒绝浏览器/代理可能提供的空值、参数化 MIME 或通用 octet-stream；allowlist + magic-header 双重校验可兼容合法 PDF 且保持非法输入拒绝。
3. 历史 400 无响应体在当前 TestClient 无法重现；没有证据支持扩大 PDF 内容判定或增加第二套写入流程，所以保留现有边界并将真实服务/浏览器复测交给 Task06F-B。
4. 前端错误字段改为后端稳定 `message`/`error_code`，避免 canonical document API 的错误原因因不存在 `detail` 而丢失。

## 验证命令、退出码与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `./.venv/bin/python -m pytest -q tests/test_kb_routes.py tests/test_kb_document_routes.py tests/test_kb_document_foundation.py tests/test_frontend_paper_contract.py` | 0 | **73 passed**；5 个既有 PyMuPDF DeprecationWarning |
| `node --check frontend/app.js` | 0 | 通过 |
| `node tests/test_frontend_kb_inspection_interaction.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_pdf.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_renderer.js` | 0 | PASS |
| `node tests/test_frontend_kb_inspection_runtime.js` | 0 | PASS |
| `./.venv/bin/ruff check backend/app/api/routes_kb.py backend/app/knowledge_base/infrastructure/document_read.py tests/test_kb_routes.py tests/test_kb_document_routes.py tests/test_kb_document_foundation.py tests/test_frontend_paper_contract.py` | 0 | `All checks passed!` |
| `git diff --check` | 0 | 通过 |

## 风险与阻塞

- 子 Agent 受控矩阵阶段未连接 live service（当时端口 8000 连接被拒绝），因此该阶段使用 FastAPI TestClient；主 Agent 后续已在服务重启后补做真实 HTTP 上传验收，见下文。
- 历史用户 400 没有原始响应体，根因仍不能归因到某一个请求字段；若 Task06F-B 在真实服务上复现，应保留原始响应 headers/body、request id、文件名、part MIME 和请求大小，再按稳定错误码处理。
- PDF 文件仍需 `%PDF-` 开头；损坏但带合法头的 PDF 由后续 parser/application 阶段按既有受控错误处理，不在本轮放宽。
- 本轮未启动真实服务、未写入/删除 `data/kb`、未连接 Qdrant、未执行 embedding 或索引任务。

## 主 Agent 后续动作

1. 审查当前限定 diff，确认没有把 upload 兼容逻辑扩展到非 PDF MIME 或第二套 storage/index pipeline。
2. 由 Task06F-B 在实际已启动服务和浏览器路径复测合法新 PDF、去重 PDF、非法头、空文件、非 PDF MIME，并保存 response body/headers 证据；若无法复现 400，保持本报告的“未归因”结论。
3. 复核新增探针文档不存在且用户 `data/kb` 集合未改变；再更新 Task06F 执行结果和 Spec018 状态，不要因 TestClient 通过直接宣称生产端到端完成。

## 时间、模型与工具统计

- 开始：2026-09-10 21:15（Asia/Shanghai）
- 结束：2026-09-10 21:35（Asia/Shanghai）
- 总耗时：约 20 分钟
- 模型：临时 Luna xhigh（backend-dev）
- Token：当前工具环境未提供精确统计
- 工具：约 20 次读取、受控测试、静态检查和报告/日志写入调用

## 进度日志

`.codebuddy/agent-logs/spec-018/task-06/pdf-upload-repair/backend-dev/20260910-upload-repair.md`

## 前端子任务补充（Task 06F 前端错误可见性）

- 前端上传路径已使用 `kbUploadErrorMessage(data)`，错误字段优先级为 `message`，其次为 `error_code`、旧格式 `detail`，最后使用受控默认文案；同时保留 `error.code` 供调用方识别。
- 该前端改动不修改后端、数据、Qdrant 或成功上传路径。
- `node --check frontend/app.js`：退出码 0。
- `.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py`：退出码 0，5 passed。
- `git diff --check`：退出码 0。
- 前端进展日志：`.codebuddy/agent-logs/spec-018/task-06/pdf-upload-repair/frontend-dev/20260910-upload-error.md`

## 追加浏览器缓存修复

- `frontend/index.html` 中 app.js 版本由 `app.js?v=18` 提升为 `app.js?v=19`，确保浏览器加载当前上传错误处理。
- 未修改业务逻辑。
- `git diff --check`：退出码 0。

## 主 Agent 真实服务补充验收

- 服务已重启并加载本轮后端代码，监听 `127.0.0.1:8000`；`GET /api/health` 返回 HTTP 200。
- 既有 PDF 使用 `application/octet-stream` multipart part MIME 上传，按 SHA-256 去重返回 HTTP 201，未新增文档。
- 固定 PDF 样本以 `application/octet-stream` 作为新文档上传，返回 HTTP 201、`status=pending`；探针文档 `79bd5829c6844d2dafc899f3a90fa564` 随后通过 canonical DELETE 删除，返回 HTTP 200。
- 非 PDF 内容伪装为 `.pdf` 上传，返回 HTTP 400 `INVALID_PDF`，响应包含 `message`、`error_code`、`retryable` 和 `request_id`。
- 浏览器入口已提供 `/assets/app.js?v=19`，其中包含 `kbUploadErrorMessage`；失败提示会显示后端具体原因。
- 删除探针后 `data/kb/papers.json` 仍只包含原有文档 `d4dfd2a620384ad5bece27320661f8f0`，未留下额外 source/metadata。

主 Agent 复跑：

```text
./.venv/bin/python -m pytest -q
944 passed, 5 warnings, 38 subtests passed
node --check frontend/app.js
node tests/test_frontend_kb_inspection_runtime.js
node tests/test_frontend_kb_inspection_interaction.js
node tests/test_frontend_kb_inspection_renderer.js
node tests/test_frontend_kb_inspection_pdf.js
```

以上前端命令全部退出码为 0；上传定向测试 73 passed，`git diff --check` 与 ruff 均通过。

### 收口结论

Task06F 的受控兼容、稳定错误可见性和真实 HTTP 上传验收均通过；历史用户 400 的具体文件尚无原始请求体，因此不把根因伪造为单一字段。后续若再出现失败，页面已能直接展示后端错误码与原因，可据此继续定位。
