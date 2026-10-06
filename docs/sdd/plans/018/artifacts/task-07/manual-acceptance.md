# Spec018 新上传链路人工验收案例（历史阻塞 attempt + 成功补验）

> 说明：本文前半部分保留 run_id=spec018-api-e2e-20261006T133558Z 的真实失败 attempt，不能把它改写成成功。成功补验为 run_id=spec018-api-e2e-success-20261006T135538Z，API E2E 已通过；第 6 节按浏览器实读结果更新了实际入口、提示、等待条件和恢复步骤。

## 0. 成功补验索引

当前 API E2E 已通过；请直接从第 6 节开始，前半部分仅为历史失败归档。人工交付检查 9/10：服务、API 创建、入参解析、状态推进、可见索引状态、等待终点、核心产物、错误恢复、逐步说明均有当前证据；尚未在浏览器重复执行“文件选择器上传 → 双向点击”的完整操作，因此该项不冒充已测。历史双向点击验收保留，当前新增样本可直接用于查看。此准备度不代表成功概率的统计估计。

- 成功 API 报告：[current-api-e2e-success-report.md](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-success-report.md)
- 成功脱敏证据：[current-api-e2e-success-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-success-evidence.json)
- 历史失败证据（保留）：[current-api-e2e-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-evidence.json)
- 本轮 Markdown fixture：[upload-acceptance.md](/Users/wjh/ResearchAgent/docs/sdd/fixtures/spec-018/upload-acceptance.md)
- 固定 PDF fixture：[pdf-single-column-v1.pdf](/Users/wjh/ResearchAgent/docs/sdd/fixtures/spec-018/pdf-single-column-v1.pdf)

## 1. 历史失败状态与证据对照（当前已修复；执行第 6 节）

- **run_id**：`spec018-api-e2e-20261006T133558Z`
- **入口**：`http://127.0.0.1:8000`
- **证据**：[current-api-e2e-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-evidence.json)
- **API 报告**：[current-api-e2e-report.md](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-report.md)
- **当前结果**：`BLOCKED`。Markdown 与 PDF 的真实 upload 都返回 `400 MIGRATION_INPUT_INVALID`，没有新文档 ID，因此下游步骤只能作为“阻塞解除后的复现案例”，不能写成已完成。
- **禁止动作**：不要删除已有文档、不要点击“重建索引”、不要调用 reindex、不要清理 Qdrant；本案例只使用新样本。

## 2. 前置条件

1. 打开 `http://127.0.0.1:8000`，确认服务页面可访问。
2. 仅准备以下两个本轮样本：
   - Markdown：`/private/tmp/spec018-e2e-markdown-20261006-213558.md`。
   - PDF：`/Users/wjh/ResearchAgent/docs/sdd/fixtures/spec-018/pdf-single-column-v1.pdf`。
3. 确认当前 API health/kb health 为 200。`/api/kb/health.embedding=false` 与 `/api/ready.warmup.embedding.status=failed` 时，不得把页面的 ready 文案理解成 embedding 已预热；按实际 API 状态记录。
4. 成功案例的 run_id、document_id、task_id 和产物路径必须在新的证据 JSON 中记录；不得沿用本报告中失败 run 的空 ID。

## 3. 逐步人工验收案例

以下每一步都包含点击/输入、点击后提示、等待条件、等待中显示、下一步和失败恢复。当前 UI 文案在本轮未执行浏览器验收，所有“应”字样均是待补实证，不是当前通过证据。

| 步骤 | 点击/输入 | 点击后提示 | 等待条件 | 等待中显示 | 下一步 | 失败恢复 |
|---|---|---|---|---|---|---|
| 1. 进入知识库 | 在首页点击“知识库”；再点击“切片检查”二级 Tab | 应显示文档列表和上传入口（当前 UI 文案未验证） | 等待 documents 列表 GET 返回 | 应显示加载指示或空/已有列表状态 | 选择“上传文档”入口 | 若页面无法加载，记录 `/api/health` 状态和 request id，回到首页；不要重建索引 |
| 2. 上传 Markdown | 点击文件选择器，选择 `/private/tmp/spec018-e2e-markdown-20261006-213558.md`；点击“上传” | 当前真实 API 结果为 `400 MIGRATION_INPUT_INVALID`，不是成功提示 | 不等待后台任务；先等待上传请求结束 | 应显示可诊断的稳定错误；当前响应无可操作 UI 恢复按钮，文案未验证 | **当前 run 在此停止**；修复 metadata 校验后重新开始本步骤 | 保存错误码/request id；不要反复点击、不要删除或 reindex；确认 documents 总数仍为 40 |
| 3. 上传固定 PDF | 仅在步骤 2 的阻塞解除后，选择固定 PDF 并点击“上传” | 应返回新文档句柄、格式和 v1/v2 初始状态；当前未验证 | 等待 `POST /api/kb/documents/upload` 返回 201 | 应显示 indexing/pending 进度；当前未验证 | 记录新 `document_id` 与 `task_id`，进入文档详情 | 若返回非 retryable 4xx，记录稳定 error_code 并停止；不要使用旧文档代替 |
| 4. 等待索引状态 | 在新文档详情选择“切片检查”；保持 v1/v2 读取入口 | 应显示文档正在索引或可加载状态；当前未验证 | 轮询服务返回的状态/inspection URI，直到每个 chunker 达到 ready/partial 或明确 failed；每轮间隔按 UI 提示 | 应显示处理中、进度或可接受的静态等待提示；当前未验证 | 到达 ready/partial 后分别打开 v1、v2 | 若仍为 indexing 超过可接受窗口，记录最后状态/错误码并停止；不要手动重建 |
| 5. 验证 v1 inspection | 选择 `v1`，等待 inspection 首页和 opaque cursor 分页完成 | 应显示 `200` manifest、blocks/chunks/anchors，anchors 非空；当前未验证 | 继续使用服务返回的 `next_cursor`，直到 null | 应显示加载更多/分页进度；当前未验证 | 记录 total、唯一键、anchor 数和 manifest 状态 | 若为 202/409/503，记录 Location/Retry-After/error_code；不得自行 POST reindex |
| 6. 验证 v2 inspection | 切换到 `v2`，按同样方式加载全部页面 | 应显示 `ready` 或 `partial`，且 anchors 非空；当前未验证 | 等待 v2 LLM 相关阶段达到可观察终态 | 应显示处理中提示；当前未验证。不能把 indexing 写成通过 | 记录 mapped/unmapped、unmapped reason、总 anchors 与分页唯一性 | 若 v2 仍 indexing 或失败，保留失败 evidence；不要将 v1 成功扩写为 v2 成功 |
| 7. 查看原件与缓存契约 | 在文档详情打开原文；对 source 做 HEAD，再请求 `Range: bytes=0-15` | 应看到 PDF/Markdown 正确类型、ETag、Accept-Ranges；Range 应为 206 并带 Content-Range；当前新样本未验证 | 等待 HEAD/Range 响应结束 | 原文视图应显示可读/渲染状态；当前未验证 | 比对 headers 与 source 产物路径 | 若返回 404/416/503，记录稳定错误和 headers；不要换用既有 d4df 文档掩盖新样本失败 |
| 8. 结束并查看产物 | 在“切片检查”中加载完两个版本；检查页面状态与 API evidence | 应能看到 v1/v2 的切片数、anchor 数、未映射提示和原文定位；当前未验证 | 等待所有分页请求结束、加载更多按钮消失 | 页面应保持最终状态，不能回退到空列表；当前未验证 | 保存 evidence JSON 与 run_id/document_id 对照 | 若页面与 API 数字不一致，保存 DOM/HTTP 证据并标记 BLOCKED；不修改运行数据 |

## 4. 当前 run 的实际失败恢复

当前实际失败发生在步骤 2/3 的 API 创建入口：

```text
POST /api/kb/documents/upload
HTTP 400
error_code=MIGRATION_INPUT_INVALID
retryable=false
document_id/task_id=absent
```

正确恢复是：保存错误码与 request id → 确认 `GET /api/kb/documents?limit=100` 仍为 `total=40` 且两个新文件名不存在 → 由负责实现角色处理 metadata schema 漂移 → 生成新的 run_id 后从步骤 1 重新执行。不要继续轮询空 ID，也不要对已有文档执行删除、reindex 或 rebuild。

## 5. 成功判据与产物查看

只有在新的 run 中同时满足以下条件，才能把案例改为可交付人工验收：

- Markdown 与 PDF upload 都返回 201 且各有新 `document_id`/`task_id`；
- 两个新 ID 的状态可观察推进，v1/v2 inspection 最终为 ready/partial，且 anchors 非空；
- 所有 inspection 分页的 total 与汇总相等、复合键无重复；
- source HEAD/Range/ETag/Content-Range 符合 Spec018；
- 页面提示、等待条件、错误恢复和 API 状态一致；
- 产物和脱敏证据写入 `/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/`，不包含样本文本或私密原文。

当前这些条件没有满足，历史案例保持 **BLOCKED**。

## 6. 成功补验：实际 UI 点击、提示、等待和恢复

本节对应 run_id=spec018-api-e2e-success-20261006T135538Z。浏览器部分采用 Chrome 对 http://127.0.0.1:8000/ 的只读 DOM/accessibility 实读；成功状态改变来自同一轮已授权的真实 HTTP API 上传，浏览器没有再次上传，避免重复创建样本。

### 6.1 实际入口位置

1. 打开 http://127.0.0.1:8000/，确认首页可访问。
2. 点击左侧主导航的“▤ 知识库 42”。进入“知识库 / 论文 RAG”后，默认可见两个二级 Tab：“问答”和“切片检查”。
3. 上传入口实际位于“问答” Tab，不在“切片检查” Tab。问答 Tab 中按钮的可见文案是“＋ 点击上传 PDF 论文”，旁边的提示是“本地解析 · 本地向量化 · 不出本机”。
4. “切片检查”Tab 的实际控件是文档下拉框、v1/v2 版本选择和“原文/切片”面板；实读未发现上传按钮。不要在该 Tab 里寻找上传入口。

### 6.2 成功案例（直接查看已生成样本）

本轮 API 成功实体如下。系统按内容 SHA-256 去重，仅改文件名不会创建新实体。首次人工检查直接选择这两个已生成样本；若要再次验证上传，请选一份内容不同、尚未入库的普通 PDF，不要删除既有文档来规避去重：

| 样本 | document_id | task_id | 最终页面状态 | v1 / v2 |
|---|---|---|---|---|
| Markdown | a95357cf37344160859a812852f7863f | dda321293959475ba78b3192406a9e8e | 已索引 | 9 / 6 片段 |
| 固定 PDF | f51024342ecd46a7a0c17adefbd67abd | d729bfad744245d6826268cbaebb7dfc | 已索引 | 1 / 1 片段 |

按产品主路径进行 PDF 人工复现时：

1. 在“问答”Tab 点击“＋ 点击上传 PDF 论文”。
2. 文件选择器中选择一份内容不同、尚未入库的 PDF 后提交。固定 fixture 已在本轮入库，重命名其副本仍会返回 409；要查看固定样本，请直接在列表选择 spec018-upload-acceptance-pdf-20261006.pdf。
3. 点击后应在论文列表看到新行；等待条件是该行从索引中/处理中推进到“已索引”，并出现 v1 与 v2 片段计数。等待期间不要点击“重建索引”或“删除”。
4. 点击“切片检查”Tab，在“文档”选择器中选择刚刚上传的行；选择 v1，等待原文与切片面板出现，再选择 v2 重复。最终应看到非空切片和原文定位。
5. 页面计数应与对应 API inspection 的 totals 一致；本轮两个成功实体的 API 证据已写入成功 JSON。

Markdown 的成功创建在本轮通过 canonical HTTP multipart API 完成；当前 UI 上传按钮的可见文案明确为 PDF，因此不要声称 UI 已执行 Markdown 上传。Markdown 的 v1/v2 inspection 与 source 契约仍已由真实 API E2E 验证。

### 6.3 点击后提示与等待条件

- 上传后：列表行应先显示索引中/处理中，API 初始状态为 indexing，v1/v2 progress=0。
- 等待中：保持当前页面，观察行状态和 v1/v2 进度；不要重复点击上传，也不要把旧文档的完成状态当作新实体完成。
- 完成：列表行显示已索引；API 状态为 indexed，两个 inspection manifest 为 ready，anchors 非空，next_cursor=null。
- 切片检查：切换版本后等待“原文”和“切片”面板的内容出现；若仍显示“等待检查”或空列表，不得记录为通过。
- source 契约由 API evidence 记录：HEAD 200、Range 206、ETag 一致、条件 GET 304、缺失资源 404；不把正文复制到验收材料。

### 6.4 失败恢复

- 若上传返回 409：先用返回或列表中对应的 document_id 核对同名/同 SHA-256 记录；只能把它标记为已存在的对应 case，不能冒充本轮新创建。
- 若返回 non-retryable 4xx 或 5xx：保存 status、error_code、request_id（只记录存在性即可），停止重复点击；不要删除、reindex 或 rebuild。
- 若持续 indexing：记录最后的 document_id、task_id、v1/v2 status/progress/error，按等待窗口分段观察；仍未到 indexed/ready 就标记失败，不把中间态写成 PASS。
- 若 inspection 仍为空、anchors=0、分页 cursor 异常或 source HEAD/Range 不符合契约：保留失败 evidence，停止本例，不切换到旧文档掩盖失败。
- 若 UI 与 API 数字不一致：保存页面可见状态和 API 脱敏统计，标记 BLOCKED，等待负责实现角色处理；不改运行数据。

### 6.5 产物查看路径

- 成功 API 报告：/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-success-report.md
- 成功脱敏 JSON：/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-success-evidence.json
- 历史失败报告与 JSON：/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-report.md、/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-evidence.json
- Markdown fixture：/Users/wjh/ResearchAgent/docs/sdd/fixtures/spec-018/upload-acceptance.md
- 固定 PDF fixture：/Users/wjh/ResearchAgent/docs/sdd/fixtures/spec-018/pdf-single-column-v1.pdf

本节人工验收步骤已按实际 UI 位置更新；API E2E 成功，但浏览器本轮只读核验了入口和最终列表，没有再次提交上传动作。
