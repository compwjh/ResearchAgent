# PASS — Spec018 当前 API E2E 验收报告（成功补验）

## 1. 范围与结论

- **Spec / Task**：Spec018 / Task07，tester 真实 API E2E 补验
- **run_id**：spec018-api-e2e-success-20261006T135538Z
- **服务**：http://127.0.0.1:8000
- **时间**：2026-10-06 13:55:12Z–14:01:30Z
- **HTTP 客户端**：httpx.Client(trust_env=False)
- **动作范围**：创建本轮授权的 Markdown 与固定 PDF 两个新样本；其余请求为 GET/HEAD。没有删除、重建、reindex 或切换既有用户文档。

本轮真实上传均返回 201，随后两个新 ID 都在服务列表中推进到 indexed；v1/v2 inspection 均返回 200、manifest=ready、非空 anchors、source hash verified；source HEAD、Range 206、条件 GET 304 和缺失资源 404 均符合契约。因此本报告的 API E2E 结论为 **PASS**。

此前失败的冷启动/metadata attempt 未被覆盖，仍保留在 [current-api-e2e-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-evidence.json)、[current-api-e2e-report.md](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-report.md) 和 [manual-acceptance.md](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/manual-acceptance.md) 的历史段落中。本轮成功的脱敏结构化证据见 [current-api-e2e-success-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-api-e2e-success-evidence.json)。

## 2. 运行时与依赖状态

服务运行在当前本地工作区分支 codex/integrate-current-code-to-main。验收基线为 main 的 7bd9602；服务重启时加载的修复提交为 ecbb91f。验收后工作区又前进到 9a9733f；本报告不把后续提交推断成已经加载到当时运行中的服务。

| 请求 | 状态 | 观察值 |
|---|---:|---|
| GET /api/health | 200 | status=ok |
| GET /api/kb/health | 200 | generation.ready=true、qdrant=true、embedding=true |
| GET /api/ready | 200 | ready=true；embedding/qdrant/jieba/ollama_tags warmup 均为 ready |

本次 /api/ready 的 warmup 观测为 embedding 424.7ms、Qdrant 1166.3ms、jieba 299.1ms、Ollama tags 13.4ms。此前 30 秒 embedding timeout 属于冷启动/并行恢复阶段；本轮只记录当前真实结果，不用旧失败状态冒充当前状态。

generation/current、Qdrant meta 和 committed/run state 是快照来源，用于解释 topology 和 provenance，不替代 live API 真相。此前离线 497 与 live 460 的差异来自不同输入：in-memory 重建为 214 chunks，而持久快照为 308 chunks；本轮新样本以 live API 返回和 manifest 的 verified source_sha256 为准，不要求不同快照的 anchors 或 chunk 数相等。完整只读背景见 [current-runtime-readonly-report.md](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/current-runtime-readonly-report.md)。

## 3. 本轮样本与真实上传

样本内容未写入报告或 JSON；只保留路径、类型、字节数和 SHA-256。

| 样本 | 本地 fixture | multipart 文件名 | MIME | 字节数 | SHA-256 |
|---|---|---|---|---:|---|
| Markdown | /Users/wjh/ResearchAgent/docs/sdd/fixtures/spec-018/upload-acceptance.md | spec018-upload-acceptance-20261006.md | text/markdown | 642 | d6d2ba410fd582f28463408749ffae2e66175351d1dd376ff997756bbbe72764 |
| 固定 PDF | /Users/wjh/ResearchAgent/docs/sdd/fixtures/spec-018/pdf-single-column-v1.pdf | spec018-upload-acceptance-pdf-20261006.pdf | application/pdf | 1551 | 3cc6b61497f483fcb1933919cb00f1568ad1fd609953c96e4970c772cbe4e4ec |

| case | HTTP | document_id | task_id | 初始状态 |
|---|---:|---|---|---|
| Markdown | 201 | a95357cf37344160859a812852f7863f | dda321293959475ba78b3192406a9e8e | indexing，v1/v2 progress=0 |
| 固定 PDF | 201 | f51024342ecd46a7a0c17adefbd67abd | d729bfad744245d6826268cbaebb7dfc | indexing，v1/v2 progress=0 |

上传使用 canonical POST /api/kb/documents/upload，multipart 字段为 file。两个新实体均为本轮新建，没有用既有 d4df 文档替代。

## 4. 状态轮询与 inspection

通过真实 GET /api/kb/documents?limit=100 观察到最终列表 HTTP 200、reported_total=42、returned_count=42，并找到上表两个新 ID，二者 document status 均为 indexed。

| 样本 | chunker | manifest | blocks | chunks | anchors | mapped | unmapped | source hash | 分页 |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| Markdown | v1 | ready / 100% | 9 | 9 | 9 | 9 | 0 | verified | next_cursor=null |
| Markdown | v2 | ready / 100% | 9 | 6 | 9 | 6 | 0 | verified | next_cursor=null |
| 固定 PDF | v1 | ready / 100% | 3 | 1 | 3 | 1 | 0 | verified | next_cursor=null |
| 固定 PDF | v2 | ready / 100% | 3 | 1 | 3 | 1 | 0 | verified | next_cursor=null |

四个 inspection 请求均为真实 GET，HTTP 200，mapping_algorithm_version=source-anchor-v2，unmapped_reasons={}，anchors 非空，inspection ETag 存在。page_size=500 已覆盖本轮全部条目，next_cursor 均为 null；没有把 indexing 或空 anchors 写成通过。

## 5. Source HEAD / Range / ETag 契约

对两个新 ID 分别执行 HEAD、GET Range bytes=0-15、If-None-Match 条件 GET，以及不存在 ID 的 source GET。没有保存 source 正文；只记录 headers 和字节计数。

| 样本 | HEAD | Content-Type / 长度 | Range | Content-Range | ETag | 条件 GET | 缺失 ID |
|---|---:|---|---:|---|---|---:|---:|
| Markdown | 200 | text/markdown / 642 | 206 | bytes 0-15/642 | 存在，Range 与 HEAD 一致 | 304，0 bytes | 404 |
| 固定 PDF | 200 | application/pdf / 1551 | 206 | bytes 0-15/1551 | 存在，Range 与 HEAD 一致 | 304，0 bytes | 404 |

两个 HEAD 均返回 Accept-Ranges=bytes、body bytes=0；两个 Range 均返回 body bytes=16、Content-Length=16。该项同时覆盖了有效 Range、ETag/条件缓存和非法资源 404。

## 6. 产品 UI 入口实读

使用 Chrome 只读查看 http://127.0.0.1:8000/：

1. 左侧主导航显示“▤ 知识库 42”；点击后进入“知识库 / 论文 RAG”。
2. 默认选中的二级 Tab 是“问答”。该 Tab 内实际显示按钮“＋ 点击上传 PDF 论文”，旁边提示“本地解析 · 本地向量化 · 不出本机”。
3. “切片检查”是另一个二级 Tab；实读确认该 Tab 没有上传按钮，只有文档选择、v1/v2 版本选择以及原文/切片面板。
4. 问答 Tab 的列表实际显示本轮两个新文件名和最终状态：Markdown 为已索引、v1 9 片段、v2 6 片段；PDF 为已索引、v1 1 片段、v2 1 片段。

浏览器本轮只做 DOM/accessibility 观察，没有再次点击上传；状态改变只来自上面的授权 HTTP API 上传。详细的点击、提示、等待与失败恢复步骤见 [manual-acceptance.md](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/manual-acceptance.md)。

## 7. 安全边界与产物

- 既有用户文档删除：否。
- 既有文档 reindex/rebuild：否。
- Qdrant 切换或 tester 主动写入：否。
- mock、内部函数、伪造响应：否。
- 样本文本、PDF 正文、Cookie、授权头：未记录。
- 失败 attempt：保留，未静默覆盖。
- 成功 fixture：[upload-acceptance.md](/Users/wjh/ResearchAgent/docs/sdd/fixtures/spec-018/upload-acceptance.md)；固定 PDF：[pdf-single-column-v1.pdf](/Users/wjh/ResearchAgent/docs/sdd/fixtures/spec-018/pdf-single-column-v1.pdf)。
- 成功证据目录：[task-07 artifacts](/Users/wjh/ResearchAgent/docs/sdd/plans/018/artifacts/task-07/)。

## 8. Final Decision

**API E2E：PASS。** 本轮已完成真实创建 → 状态推进 → v1/v2 inspection → 非空 anchors → source HEAD/Range/ETag/404 的闭环。人工验收案例已按实读 UI 入口补齐；若用户再次从 UI 上传，应使用新的唯一文件名，并以页面的 indexing → 已索引提示和 inspection Tab 的最终计数为等待终点。遇到 409 或非 retryable 错误时，应核对已有对应 ID 并保留证据，不把重复实体冒充新创建。
