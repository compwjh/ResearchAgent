# Task 06F：PDF 上传失败与错误可见性修复

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task 04 上传契约、Task 06E 当前服务版本 ｜ 被依赖：Task 07 收口
> 当前状态：`已完成`

## 一句话目标

让浏览器和 API 对真实 PDF 的上传失败给出可操作的稳定错误，并在不放宽非 PDF 输入边界的前提下兼容合法上传。

## 当前证据

- `/api/health` 当前返回 HTTP 200。
- 已有 PDF 按 SHA-256 去重上传返回 HTTP 201；项目固定 PDF 样本作为新文档上传也返回 HTTP 201，随后已删除探针文档。
- 服务历史日志中用户此前两次 `POST /api/kb/upload` 返回 HTTP 400，但日志没有响应体，尚不能仅凭状态码判断是文件头、请求 MIME、空内容还是业务写入失败。
- 当前前端只读取错误体的 `detail` 字段，而 canonical document API 返回 `error_code`/`message`，导致真实失败原因被隐藏。

## 前置门禁

- 只在 Spec018 已确认的 immutable document upload 范围内修改；不得改变论文下载、Qdrant、embedding、索引或现有用户数据。
- 先用固定样本与可控变体复现，再决定是否调整 PDF 文件头/MIME 判定；不得把任意字节或非 PDF MIME 当成 PDF 接受。
- 不新增第二套上传、存储或错误协议；复用 `create_uploaded_document` 与 `_document_error`。

## 执行阶段、观察点与决策依据

1. 读取上传路由、来源校验、immutable document application、前端上传处理和现有测试，记录每个失败分支的稳定状态码/错误码。
2. 用不写入生产数据的固定样本、MIME 变体和浏览器路径复现；若需要真实新文档探针，必须随后删除并记录 ID。
3. 只实现最小修复：合法 PDF 可上传；非法/非 PDF 仍拒绝；前端展示后端 `message`/`error_code`；不把索引阶段错误伪装成上传成功。
4. 运行上传定向测试、前端静态/运行时测试和 ruff；再做一次 API 探针与浏览器可观察状态验证。

## 子任务拆分与子 Agent 分派

| 子任务 | 角色 | 允许范围 | 产物 |
|---|---|---|---|
| 06F-A | backend-dev（临时 Luna xhigh） | 上传校验/应用、前端上传错误处理及对应测试 | `pdf-upload-repair-report.md` |
| 06F-B | tester（临时 Luna xhigh） | API 与浏览器只读验收，不改业务代码 | 本 Task 报告追加验收结果 |
| 06F-C | 主 Agent | 审阅 diff、回归、部署与本地提交 | Spec/Task 执行结果 |

## 06F-A 分派 Prompt

```text
你是 Spec018 Task06F-A 的 backend-dev，使用临时 Luna xhigh。先读取本 Task、Spec018 上传契约、backend/app/api/routes_kb.py、backend/app/knowledge_base/application.py、backend/app/knowledge_base/infrastructure/document_read.py、frontend/app.js 与对应测试。当前证据是 health=200、去重上传=201、固定样本新文档上传=201，但用户历史请求出现 400；不要凭空认定根因。

只允许修改上传相关 backend 文件、frontend/app.js 和对应测试/任务报告。先复现并记录文件头、MIME、空文件、合法 PDF 与前端错误解析的实际结果，再做最小修复。必须保持非 PDF/非法内容拒绝，不得新增第二套上传/存储/索引实现，不得改 Qdrant、embedding、现有用户数据或 Git 历史。若只需前端错误字段修复，也不要无关改动；若要放宽 PDF 识别，必须有固定测试证明仍是 PDF 边界。

必须运行定向 pytest、node --check/相关前端测试、ruff、git diff --check，并将固定字段报告写入 docs/sdd/plans/018/artifacts/task-06/pdf-upload-repair-report.md，进度日志写入 .codebuddy/agent-logs/spec-018/task-06/pdf-upload-repair/backend-dev/。回传结果状态摘要、改动文件、测试命令/退出码/结果、产物路径、决策依据、风险阻塞、主 Agent 后续动作、开始结束总耗时，以及可用时模型/token/工具统计。
```

## 子 Agent 返回后主 Agent 必须执行的校验

- 确认每个失败条件有稳定 `error_code` 与用户可见 `message`，前端不再只读取不存在的 `detail`。
- 确认合法 PDF、去重 PDF、非 PDF 扩展名、MIME 不匹配、空文件和非法文件头的行为符合 Spec018。
- 确认上传成功仍经过唯一 immutable document application，不触发额外下载/索引实现。
- 复跑上传与全量回归，检查新增文档探针已删除且 `data/kb` 仅保留用户原有文档。

## 测试与验收标准

- 浏览器选择真实 PDF 后，成功或失败均显示后端返回的稳定原因；不再只显示“上传失败”。
- 合法 PDF 上传返回 201，重复内容按既有 hash 去重；非法内容仍返回 400/415/413 等既定状态。
- 不改变现有文档、manifest、Qdrant collection、embedding 或安全下载语义。

## 风险、停止条件与回滚

- 无法复现用户 400 时不得猜测性放宽校验；保留复现矩阵并停止在诊断结果。
- 发现 generation marker、metadata 或 Qdrant 写入失败时，停止并保留原件/元数据，不做清理或回滚用户数据。
- 不执行 reset、stash、clean、push、合并 main 或覆盖用户修改。

## 产出物

- `docs/sdd/plans/018/artifacts/task-06/pdf-upload-repair-report.md`
- `.codebuddy/agent-logs/spec-018/task-06/pdf-upload-repair/backend-dev/`

## 执行结果

`已完成`。

- 后端允许常见 PDF multipart part MIME（参数化、`application/x-pdf`、`application/octet-stream`、`binary/octet-stream` 或缺失），仍要求 `.pdf` 扩展名和 `%PDF-` 魔数。
- 前端上传错误显示稳定 `message（error_code）`，兼容旧 `detail`，并通过 `app.js?v=19` 强制刷新浏览器缓存。
- 服务端现在在 generation gate 通过后自动复用既有 `submit_document_reindex(..., "all")`，新文档响应返回 `status=indexing`、双版本进度和 `task_id`，不再静默停留 `pending`；重复内容不重复入队。
- 真实服务验证：合法去重 PDF 201、中文文件名新 PDF 201 后清理、非法 PDF 400 `INVALID_PDF`；已为 `2105.07447.pdf` 补提交索引并完成 v1/v2（79/61 片段）。
- 定向上传/重建测试 69 passed；本轮未跑全量 pytest；ruff、`py_compile`、`git diff --check` 全部通过。
- 追加修复：索引任务现在用同一批 provenance chunks 同时写入 Qdrant 和 `InspectionManifest`；缺失清单的 canonical 文档会复用既有 reindex worker 实际补建，重复检查请求在任务运行期间保持 202 可轮询，完成后返回非空 `chunks/anchors`。
- 追加验证：切片检查定向测试 118 passed（含 foundation/routes/reindex）；真实 `2105.07447.pdf` 与 `MAD-HTLC...pdf` 的 v1/v2 检查请求均已验证可从 202 转为 200 且返回非空切片。

## 变更日志

- 2026-09-10：用户反馈新 PDF 无法上传；已确认服务可用但历史上传 400 缺少响应体，进入受控复现与最小修复。
- 2026-09-10：完成 MIME 兼容、魔数校验与错误可见性修复；真实服务 HTTP/探针上传和回归通过，Task06F 收口为已完成。
- 2026-09-10：用户反馈合法上传长期显示“待索引”；确认上传只写入 immutable metadata、未调用既有 reindex seam，补充 generation gate 与自动入队，并为 `2105.07447.pdf` 完成一次真实索引恢复。
- 2026-09-10：用户反馈索引完成后切片检查无内容；确认 direct reindex 只写向量且 inspection 缺失清单时没有实际 worker。修复为同批 provenance chunks 发布 manifest，并将重复检查请求保持为 202 轮询；完成定向测试、真实文档 v1/v2 运行时验证并提交本地修复。
