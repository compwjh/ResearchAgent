# Spec018 需求评审：知识文档切片检查器与双向原文定位

> 关联：[Spec018](../specs/018-knowledge-document-chunk-inspector.md) ｜ 任务索引：[Plan 018](../plans/018/README.md)
>
> 评审者：开发主管（独立需求评审） ｜ 评审日期：2026-09-08 ｜ 模型：gpt-5.6-luna xhigh（本轮指定） ｜ 首轮结论：打回；修订轮结论：通过
>
> 分派方式：主会话分派的独立评审任务 ｜ 进展日志：[20260908-195120.md](../../../.codebuddy/agent-logs/spec-018/task-00/architect/20260908-195120.md)
>
> 评审范围：需求目标、范围、产品使用步骤、边界与明确不做、验收可测性，以及 PDF/Markdown、双栏双向定位、旧文档补建、重复 embedding、窄屏和安全约束。未修改业务代码，未运行会改变项目状态的命令。

## 结论

**打回。**

Spec 018 的产品方向和主要边界已经清楚：它明确要查看已写入索引的真实 v1/v2 切片，支持 PDF 与 Markdown，首版只做文本块级只读联动，并禁止检查器重新切片或重新 embedding（Spec 018:9-19、23-29、141-145、164-173）。数据对象、端点清单、失败场景和固定样本方向也已具备初稿（Spec 018:31-108、147-162、175-185）。

但它目前还不能作为独立、可重复验收的需求基线：Spec 的“产品使用步骤”仍明确是占位文本（Spec 018:187-189）；双栏 PDF 的定位正确性、Markdown 块与行号语义、旧 PDF 补建后的身份/状态迁移、首次打开不触发 embedding，以及窄屏切换的可观察判据都没有形成足够精确的验收 oracle。按照项目 Gate 2 要求，需求评审必须确认产品步骤可操作、范围可测、边界和验收完整，因此在补齐以下阻断项并重新评审前，不得将 Spec 状态改为“已确认”，也不得进入 Task 02。

## 已确认的有效部分

1. **目标可理解。** 一句话目标把“切片检查 Tab、PDF/Markdown、原文/切片双向文本块联动、真实索引结果”放在同一范围内；背景也说明了不能把 Qdrant 检索索引当作原文展示唯一事实来源（Spec 018:9-19）。
2. **产品范围基本收敛。** 只读检查、单次一个版本、块级而非字符级映射、无 OCR/编辑/自定义切片版本等“不做”项有明确文字（Spec 018:110-121、164-173）。
3. **核心安全意图正确。** 服务端生成 ID、禁止文件系统路径入参、拒绝伪 PDF/非 UTF-8 Markdown、PDF 不执行脚本/表单/附件/远程资源、Markdown 先净化后渲染等原则已写入规范（Spec 018:102-108、147-162）。
4. **对既有系统的约束有事实依据。** 当前知识库仍以 `PaperRecord.paper_id`、PDF 文件和 `papers.json` 为核心（`backend/app/knowledge_base/infrastructure/store.py:1-5,46-67`），当前路由只提供 `/api/kb/papers`、`/api/kb/upload` 等 PDF 论文接口（`backend/app/api/routes_kb.py:102-132,150-178`），前端也仍是论文上传 + 问答布局（`frontend/index.html:80-117`）。因此提出通用文档迁移是必要范围，而不是可选的命名调整。

## 必改项（阻断或高风险）

### P0-1：补齐可执行的产品使用步骤

**问题证据：** Spec 018:187-189 把“产品使用步骤”留作“Spec 确认后由 PM 填写”，但 AGENTS.md 的需求评审门禁要求需求评审确认产品步骤可操作；Plan 018 也要求在需求/技术评审和 Spec 确认前不得执行 Task 02（`docs/sdd/plans/018/README.md:17-24`）。

**修改建议：** 在进入重新评审前写入逐条用户旅程，至少包括：

- 选择知识库 → 进入“切片检查”Tab → 文档列表显示 PDF/Markdown、原件状态、v1/v2 状态；不自动打开第一份文档。
- 选择版本并打开已索引文档；清单不存在时显示“构建中 + 进度”，ready/partial/failed/原件丢失/版本未完成时各有可观察结果和可执行下一步。
- PDF 普通段落、双栏、跨页切片、无文本层；Markdown 标题/段落/列表/表格/代码块/恶意 HTML；每类明确用户看到的原文块、切片列表、页码或行号、映射警告。
- 点击原文块和点击切片的目标、全部高亮项、滚动后的焦点；键盘 Enter/Space 等价行为。
- 桌面双栏和窄屏“原文/切片”切换的入口、当前栏、滚动位置保留、联动后自动切换目标栏。
- 旧文档首次打开、清单重建、并发打开、服务重启残留 building、删除/原件丢失的用户可见状态。

每一步都应写成功时可观察结果、失败时错误摘要/按钮状态和重新操作方式。不能以“待 PM 填写”作为 Gate 2 的输入。

### P0-2：为 PDF/Markdown 映射建立确定的验收 oracle

**问题证据：** 数据模型规定了 `pdf_bbox`、`markdown_lines` 和多对多 `SourceAnchor`（Spec 018:48-79），交互规定了“覆盖率最高且位置最近”和“第一个主锚点”（Spec 018:118-120），但没有定义规范化文本、PDF 阅读顺序/双栏列顺序、匹配阈值、覆盖率计算、主锚点并列时的稳定 tie-break、跨页块的归属或无法映射判定。验收只写“均正确”（Spec 018:175-180），不同实现可能得到不同但都声称正确的 manifest。

**修改建议：** 增加可提交的固定 fixture/manifest 期望表：每个 PDF 页、双栏列、跨页 v2 chunk 和 Markdown 块都给出稳定的 `block_id`、ordinal、locator、期望关联的 chunker/chunk_index、primary anchor 及允许的 bbox/行号误差；明确规范化规则和对齐阈值。规定所有关联块/切片的排序和 tie-break，并明确 `partial` 的触发条件、映射率显示、未映射项的读取行为。双栏样本必须同时验收“视觉列顺序”和“点击后目标页/块”，不能只检查文本最终出现。

Markdown 需要明确解析版本与块切分规则（尤其列表、表格、代码块、连续段落和恶意 HTML 被移除后是否保留块/行范围）。PDF 需要明确 `pdf_bbox` 是由同一解析事实生成还是由浏览器文本层重建，以及 bbox 超出页面、旋转页面、跨栏块的处理。

### P1-1：补齐端点返回契约和迁移后的兼容判定

**问题证据：** 端点表只给出“完整清单”“状态进度”等概括，没有给出 `KnowledgeDocumentSummary`、manifest、source block、chunk snapshot、anchor 的完整 JSON schema，`202` 后如何轮询、何时转 `200/409`、`partial/failed` 的 HTTP 与 payload 语义也未定义（Spec 018:97-108）。现有前端实际仍调用 `/api/kb/papers`、`/api/kb/papers/{id}/reindex`、`/api/kb/upload`、`/api/kb/papers/{id}`（`frontend/app.js:1505-1538,1541-1633,1661-1683`），后端也直接按 `paper_id` 建索引（`backend/app/api/routes_kb.py:107-147`）。

**修改建议：** 在 Spec 或链接的契约文档中写出成功/错误 JSON、`Content-Type`、`Retry-After`（如采用）、202 状态对象的字段、409 的精确原因和客户端动作；定义 `/api/kb/papers*` 是一次性迁移更新、短期兼容别名还是明确删除，并列出必须同步修改的调用方和测试。若要求“不保留两套长期模型”，应明确旧 HTTP 表面是否保留到哪个迁移点，不能让实现者自行猜测。

### P1-2：把旧 PDF 补建/迁移变成可验证的数据旅程

**问题证据：** Spec 要求既有 `paper_id` 原值迁移为 `document_id`，保留 `uploaded_at`、论文元数据，并可对旧 PDF 首次打开自动补建（Spec 018:35-46、115、177-180、204-214），但没有规定旧 `papers.json` 每字段如何迁移、原件缺失时如何迁移、旧记录缺少 `chunkers`/v2 时的状态、hash/fingerprint 首次生成、失败回滚和重复执行结果。当前存储的 `uploaded_at` 由 `datetime.now().isoformat(timespec="seconds")` 生成，未保证带时区（`backend/app/knowledge_base/infrastructure/store.py:194-223`）；旧记录读取时只在内存补齐双版本状态（`store.py:79-98,231-270`），不会生成新的文档/manifest 事实。

**修改建议：** 添加迁移矩阵和验收样本：旧 PDF 有/无原件、v1 indexed/partial/failed、v2 pending/不存在、论文导入元数据存在/缺失、stored filename 含非法路径、重复执行迁移。每个样本明确 `document_id` 必须等于旧 `paper_id`、文件 basename、media type、时区化 created_at、source hash、page_count、chunker 状态及 Qdrant payload 的 ID 关系。原件缺失应保留诊断记录且不得删向量；部分失败必须原子落盘、可重试且不产生第二份文档或第二套索引。明确旧论文发现导入只能经 knowledge-base application 入口，并为该要求写一条可验收的调用边界场景。

### P1-3：将“首次检查不重复 embedding”写成可观测断言

**问题证据：** 禁止重复 embedding 的意图清楚（Spec 018:19、141-145、172），但当前真正写 Qdrant 时会调用 `embed_texts`（`backend/app/knowledge_base/infrastructure/index.py:101-150`），重建流程也会删除并重新 upsert（`index.py:260-357`）。仅比较 `chunk_fingerprint` 不能证明没有调用 embedding，也不能区分检查清单构建与用户显式 reindex。

**修改建议：** 验收应对“已有 PDF + v1/v2 已索引”安装可控的 `embed_texts`/Qdrant spy：首次 GET inspection、重复 GET、两个并发 GET、服务重启后重试均断言 embedding 调用次数为 0、point 数/ID/payload fingerprint 不变、原件 hash 不变；同时断言检查器未调用切分器。另写一条显式 `POST reindex` 的单独场景，说明 reindex 是用户主动行为、是否允许重新 embedding，避免把两者混成同一保证。对 202 building/409 未完成版本，必须断言没有偷偷先建索引来“凑”清单。

### P1-4：把安全约束落到 PDF.js、Range 和 Markdown 资源行为

**问题证据：** Spec 要求本地 vendored PDF.js 公共 display API 和禁止 PDF JavaScript/表单/附件/远程资源（Spec 018:115-117、150-152），但当前页面只加载 Marked 与 DOMPurify，没有 PDF.js 或 worker 资源（`frontend/index.html:248-250`）。当前 Markdown 渲染器会净化并禁止 `img` 等标签，但没有实现“相对图片显示占位和原地址”的产品语义（`frontend/app.js:1392-1401`）。

**修改建议：** 明确 vendored PDF.js 的版本、worker 加载方式、允许使用的 public display API、禁用/不暴露脚本/表单/附件/网络请求的配置，以及资源缺失时的安全降级。固定恶意 PDF 样本（JavaScript、表单、附件、远程 URL、加密/损坏）并断言不会执行或发出网络请求。为 source Range 写出合法/非法/越界/多 Range 的状态码、`Content-Range`、`Accept-Ranges`、`Content-Type`、inline disposition 和 ID/路径穿越拒绝断言。

对 Markdown 固定定义：恶意 HTML、事件属性和 `javascript:` 的净化结果；远程图片与相对附件都不发请求；若保留占位，规定占位文本和原地址如何以 `textContent` 安全展示；Marked/DOMPurify 缺失时必须只展示转义纯文本。安全验收应检查浏览器网络记录，而不只检查 DOM 文本。

### P1-5：让窄屏双视图的可测行为明确

**问题证据：** Spec 只说桌面左右双栏、窄屏用“原文/切片”切换器并保留滚动位置（Spec 018:120-121、183）。当前知识库在 `max-width:760px` 时只是把现有侧栏和聊天区堆成单列（`frontend/styles.css:194-200,720-725`），尚不存在检查器切换器。

**修改建议：** 规定桌面/窄屏断点（可复用 760px，但必须写入契约）、两个视图的可见顺序和切换控件语义；给出浏览器验收断言：在指定 viewport 下不会横向溢出，原文块点击会自动切到切片栏、切片点击会自动切回原文栏，双方切换前后的 `scrollTop`/定位项恢复，程序化滚动不会触发反向联动，键盘焦点不丢失且 Enter/Space 等价。至少固定一个长文档和一个 v2 跨页样本，避免只在空页面上通过。

## 次要但应在确认前澄清的需求项

1. `InspectionManifest.status` 使用 `pending/building/ready/partial/failed`，而既有存储的部分索引值为 `indexed_partial`（`backend/app/knowledge_base/infrastructure/store.py:17-21`）；须规定对外映射，避免列表和检查器显示两套状态。
2. `mapping_algorithm_version` 的初始值、`index_fingerprint` 的输入字段/排序/摘要算法尚未指定（Spec 018:81-95）。否则“失效判定”和“不变”不可重复计算。
3. “大文档虚拟化或分段渲染”是两个实现选项，但验收没有页数/切片数阈值、首屏/交互预算或主线程阻塞判据（Spec 018:158-160、177-185）。至少定义长样本规模和可观察性能门槛。
4. 清单损坏、schema 过期、原件 hash 或索引指纹变化时的“丢弃并重建”需与并发去重、原子写入和用户提示关联；当前后端启动残留 `indexing` 是标记失败后由用户重建（`backend/app/knowledge_base/infrastructure/store.py:322-347`），与 Spec 所称“可重试中断并重新构建”是否自动重建需要明确（Spec 018:154-158）。
5. `created_at` 要求带时区（Spec 018:43），但迁移旧 naive 时间没有时区来源。应规定按本地时区解释、保留原字符串另存，还是标记 unknown，避免无依据伪造时间。

## 重新评审准入条件

- Spec 018 补写完整“产品使用步骤”，并同步把每个场景的可观察成功/失败结果写进验收方式。
- 提供 PDF/Markdown 固定 fixture 与期望 manifest/anchor 表，明确双栏顺序、跨页、规范化和 tie-break。
- 补齐新端点 JSON/状态码/轮询/Range 契约和旧 `/api/kb/papers*` 调用方迁移决定。
- 补写旧文档迁移/补建矩阵、原子性/重复执行要求，并证明 document_id 保留旧 paper_id。
- 增加 no-embedding/no-reslice 的 spy 断言，明确显式 reindex 的例外边界。
- 补齐 PDF.js 资源与安全降级、恶意 PDF/Markdown 网络请求验证，以及 760px（或明确断点）窄屏行为断言。

上述项目完成并由需求评审重新核对前，结论保持**打回**，Spec 状态保持 `待确认`。

## 修订轮（2026-09-08）

### 复核范围与证据

本轮复核了上一轮提出的 P0/P1 项目及其落盘修改：

- Spec 018 已将产品使用步骤改为 11 步桌面/窄屏用户旅程，覆盖空库、版本未完成、清单构建、PDF/Markdown 渲染、双向点击、键盘操作、重建/删除和恶意输入（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:206-216`）。
- Spec 018 已列出固定 PDF/Markdown 样本、`*.expected.json` 约定以及 manifest/anchor、bbox/行号、状态/进度、错误和 fingerprint 观测字段（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:188-205`）。
- 文本规范化、coverage/primary 排序、`mapping_algorithm_version`、`source_sha256` 和 `index_fingerprint` 已固定；旧 `paper_id → document_id` 补建矩阵、重复迁移、原件缺失和 no-embedding/no-reslice spy 断言已写入验收（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:75-81,194-199`）。
- 新端点的成功/错误状态、202/409 轮询、Range headers、旧 `/api/kb/papers*` 迁移边界已补入接口契约（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:114-121`）。
- PDF.js 本地资源/worker 和 hostile PDF 网络观察、Markdown 净化/资源请求、760px 窄屏切换、`scrollTop`/焦点恢复与长文档观测已写入验收；Plan 018 README 同步写明技术评审、用户确认、fixture 落盘和 Task 02 门禁（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:199-205`、`docs/sdd/plans/018/README.md:25-30`）。

### 修订轮判定

**通过（需求评审）。**

本轮补充已经把上一轮的需求阻断项转换为可执行旅程、固定样本目录约定、稳定 manifest/anchor oracle 和可观测字段；能够让后续实现/测试在不依赖聊天上下文的情况下判定双向定位、旧文档补建、检查器不触发 embedding、安全资源行为和窄屏联动是否符合需求。没有发现需要继续打回的需求层阻断。

以下不是本轮需求评审阻断，但仍是后续硬门禁：

1. 技术评审必须确认数据模型、迁移、PDF.js 依赖和接口实现边界；技术评审通过前不得进入 Task 02。
2. Task 02 必须实际创建 `docs/sdd/fixtures/spec-018/` 中列举的原件和 `*.expected.json`，并给出来源锚点 Go/No-Go；规范中的样本约定不能被空文件或口头结果替代。
3. 用户仍需明确确认 Spec；本次只把需求评审结论更新为通过，不改变 Spec 的 `待确认` 状态，也不授权修改业务代码。

因此，最新需求评审结论为**通过**，Spec 018 可进入技术评审；在技术评审通过、样本落盘和用户确认完成前，仍不得进入实现阶段。

## 自动重建修订待重新评审（2026-09-08）

首轮 Task02 `NO-GO` 后，用户通过 Grill with Docs 改变了旧文档产品语义：旧 PDF 首次打开检查器时自动重建已有 v1/v2，失败恢复旧索引，首次失败后仅手动重试；升级期间旧原文/切片可读但双向联动禁用；部分锚点缺失允许以 `partial` 切换。该范围与本报告上一版“旧文档零 embedding 补建”前提不同。

因此上一版“通过”仅作为历史结论保留，**不覆盖当前自动重建修订**。当前修订的需求评审状态为：`待评审（未执行）`。重新评审至少核对首次自动升级、原地替换风险提示、升级中只读体验、失败后手动重试、partial 展示和原件 hash 冲突的用户旅程；通过前不得执行 Task02A。

## 自动重建修订独立需求复审（2026-09-08）

> 评审者：开发主管（独立需求评审） ｜ 模型：gpt-5.6-luna xhigh（仅本轮） ｜ 评审时间：2026-09-08 22:07 +0800
>
> 进展日志：[20260908-220742.md](../../../.codebuddy/agent-logs/spec-018/task-01/architect/20260908-220742.md)
>
> 评审范围：只读核对自动重建修订后的 Spec、Plan README、Task02A、Task02B、上一版需求评审和首轮 Task02 `NO-GO` 报告；未修改业务代码，未修改首轮历史证据。

### 逐项核对

| Grill 决策 / Gate 要求 | 结论 | 证据与可验收行为 |
|---|---|---|
| 旧 PDF 首次打开自动升级已有 v1/v2 | 通过 | `LegacyInspectionUpgrade` 明确只包含升级前已存在且可用的版本，首次打开最多自动提交一次（Spec:109-120、169-172）；接口固定返回 `auto_attempted`、`old_snapshot_available` 和 `interaction_mode`（Spec:135-147）。产品步骤也明确旧 PDF 首次打开触发已有版本升级（Spec:352）。 |
| 升级中可观察、旧内容只读且禁用联动 | 通过 | 升级状态有 `pending/running/validating/restoring/restored/failed`、单调进度和 `read_only_no_link`（Spec:109-124）；清单构建中显示 0–100% 并复用同一任务（Spec:343-347）；升级中旧原文/切片可读、联动禁用（Spec:146-147、177、352）。 |
| 失败恢复、失败后只允许手动重试 | 通过 | 删除旧 points 前完成预计算并保存含向量的快照，失败/中断先恢复旧索引（Spec:124、171-177）；失败后 GET 不再自动提交，只能通过 `reason="inspection_upgrade_retry"` 的 reindex（Spec:146-147）。Task02A 要求故障注入和“首次自动失败后仅手动 retry”（Task02A:48、67-73），Task02B 固定验证同一行为（Task02B:44-46、69-80）。 |
| partial 与未映射块交互 | 通过 | 锚点不全允许 `partial/linked_partial`，必须显示覆盖率、未映射数量和稳定原因；零映射不得通过（Spec:176、298、328；Task02B:69-75）。产品点击未映射块时保留阅读位置并显示警告（Spec:348）。 |
| hash 冲突、原件缺失和状态失败的用户动作 | 通过 | 原件缺失保留诊断并返回受控 404；hash 与记录不一致固定为 `SOURCE_HASH_MISMATCH`，不会静默索引替换文件；索引未完成/失败显示状态、进度/摘要和可执行重建入口（Spec:144-147、166、211-217、343-346）。 |
| 验收是否能证明“没有偷偷重切片/embedding” | 通过 | 新文档/已有 provenance 仅构建派生清单且 embedding、切分、Qdrant 写均为 0；旧 PDF 首次升级单次幂等，验收要求记录调用次数、删除前预计算、快照 hash、写入窗口、恢复前后 fingerprint、并发单任务及失败后重复打开调用为 0（Spec:318-326）。 |
| 首轮 `NO-GO` 是否被错误覆盖 | 通过 | 历史报告仍明确 parser/Markdown 实现/hostile 网络证据缺失并裁决 `NO-GO`（`docs/sdd/plans/018/artifacts/task-02/source-anchor-feasibility-report.md:9-12,111-132`）；README 和 Task02B 要求只读消费首轮 hash，Task02B 任何硬门失败即 `NO-GO`，仅严格 `GO` 放行 Task03（README:27-33,50-74；Task02B:16-28,58-80）。 |

### 复审结论

**通过（需求评审）。**

本轮自动重建修订已把 Grill 决策完整转化为可操作的用户旅程、状态/进度/交互模式、失败恢复和手动重试入口，并为 `partial`、原件 hash 冲突、升级中只读和 no-embedding/no-reslice 提供了固定验收断言。首轮 `NO-GO` 作为不可改写历史证据保留，Task02A/02B 的实现与重新验证门禁也已明确，未发现新的需求层阻塞项。

本结论不改变 Spec 的 `待确认` 状态，也不授权修改业务代码。进入 Task02A 前仍必须满足：技术评审通过、用户明确确认 Spec；Task02A 完成后必须由 Task02B 以严格 `GO|NO-GO` 重新裁决，任何 `NO-GO` 都停止 Task03–07。实现阶段应把“重建索引”按钮在自动升级失败时绑定到 `reason="inspection_upgrade_retry"`，但该绑定已由接口契约冻结，不构成需求阻塞。

## 全库索引替换修订待重新需求评审（2026-09-09）

用户已撤销“旧 PDF 首次打开自动升级、逐 point/vector 快照恢复、失败后手动 retry”的未完成产品语义，并通过 Grill with Docs 确认：旧 vectors/manifest 可丢弃；原件、元数据与身份必须保留；重建由管理员在停服维护窗口显式执行；页面未迁移时只显示 `INDEX_REBUILD_REQUIRED`；原件不可原位修改，只能删除后重新提交并生成新 ID。

因此以上历史“通过”仅保留审计价值，不覆盖当前修订。当前修订状态为：**待独立需求评审（未执行）**。复审至少核对全库失败语义、维护状态、用户可见提示、不可变原件、删除再提交、PDF/Markdown 双栏旅程和 Task06 真实切换验收；通过前不得继续业务代码。

## 全库索引替换修订独立需求复审（2026-09-09）

> 评审者：开发主管（独立需求评审） ｜ 模型：gpt-5.6-luna xhigh（仅本轮） ｜ 评审范围：Spec018、Plan README、Task02A/02B/03/04/05/06/07，以及本文件历史与最新待评审段。
>
> 本轮只读核对需求与验收契约；未修改 Spec、Plan、业务代码或任何历史评审段。仅在本文件末尾追加本次结论。

### 逐项核对

| 核对项 | 结论 | 证据与可测行为 |
|---|---|---|
| 用户旅程与维护提示 | 通过 | Spec 已给出桌面/窄屏 11 步旅程：文档与版本选择、空库/原件丢失、ready/partial/failed、双向联动、键盘、删除确认和新 ID 提交（Spec:351-363）。全库未完成只显示 `INDEX_REBUILD_REQUIRED`，`finalize_pending` 保持维护状态；页面、GET、启动和普通问答均不得隐式重建（Spec:171、264、362；Task05:20-29、66）。 |
| 失败提示与恢复动作 | 通过 | 统一错误体、稳定 error code、HTTP 映射、`Location`、`Retry-After`、任务状态和建议动作已冻结（Spec:204-225）。Task04 明确 `INDEX_REBUILD_REQUIRED`、`INDEX_FINALIZE_REQUIRED`、`INSPECTION_BUILDING`、`DELETE_PENDING`；Task06 明确 build 失败清理、alias switch 失败的 `resume-switch`、finalize 失败的 `resume-finalize` 和拓扑歧义 fail-closed（Task04:42-49；Task06:50-53、95-98）。 |
| 不可变原件与删除再提交 | 通过 | `document_id` 保留历史身份；原件提交后禁止 PUT/PATCH/同 ID 覆盖，删除成功后重新提交产生新 `document_id`，不建立版本链（Spec:162-167、217、322、362；Task03:31-44）。删除先写 tombstone，按 Qdrant→manifest→原件→metadata 顺序处理；部分失败只能返回 `DELETE_PENDING`，不得用不完整 200 掩盖（Spec:200、221）。 |
| 全库失败语义与切换边界 | 通过 | 正式元数据是唯一权威集合，缺原件/损坏/配置不可用在 preflight 失败，孤立文件只报告；空库返回 `NO_DOCUMENTS_TO_REBUILD`；每篇文档必须同时成功生成 v1/v2、dense/sparse，任一失败删除未验证候选、保持当前入口不变并从头重建（Spec:172-179；README:28-37）。首次 alias 切换失败停服保留候选，finalize 失败禁止正常启动，未知拓扑不得猜测或删除；Task06 覆盖同一故障矩阵（Task06:60-62、95-98）。 |
| PDF/Markdown 双栏与双向验收 | 通过 | 固定 PDF（普通、双栏重叠、跨页、无文本层、hostile）和 Markdown（结构块、hostile）样本、expected manifest/anchor、PDF bbox ±0.005、Markdown 行号 100%、双栏页面/列顺序/bbox、v1 重叠和 v2 跨页均有断言（Spec:327-342）。桌面 `>=761px` 双栏、窄屏 `<=760px` 切换器，要求保存两侧 `scrollTop`、焦点/目标、键盘等价且无横向溢出；Task05 将 vendored PDF.js、DOMPurify、图片零请求和真实浏览器网络记录列为交接硬门（Spec:344-348；Task05:39-59）。 |

### 复审结论

**通过（需求评审）。**

本次全库索引替换修订已把产品旅程、维护窗口、失败/恢复提示、不可变原件、删除再提交新 ID、全库候选失败语义和 PDF/Markdown 桌面/窄屏双栏验收转化为稳定状态、动作、fixture、阈值和浏览器观测，需求层面没有新的阻断项。

本结论不改变 Spec 的 `待确认` 状态，也不授权继续业务代码。后续必须先完成技术评审并取得用户对当前修订的明确确认；确认后按 Task02A-D/E → Task02B 严格 `GO|NO-GO` 门禁推进，真实用户索引只能在 Task06 停服维护窗口执行。实现时应保持“全库未迁移只显示 `INDEX_REBUILD_REQUIRED`、`finalize_pending` 不启动正常服务、删除部分失败只允许 tombstone 重试”的契约，但这些已由需求和 Task 文档冻结，不构成当前需求阻塞。

### 检查记录

- 读取命令：`wc -l`、`rg`、`sed`、`nl -ba`；退出码均为 `0`。
- 检查范围：Spec018、Plan README、Task02A/02B/03/04/05/06/07 和本评审文档；未读取聊天或运行中 Agent 日志。
- 本轮未运行会改变项目状态的命令，未修改业务代码、Spec、Plan 或历史评审内容；仅追加本节。
- 风险：本结论只覆盖需求完整性，Task02A-D/E、Task02B、Task03–07 的实现、测试、评审和真实运行时证据仍未完成。
- 主 Agent 后续动作：等待技术评审与用户确认；在此之前保持 Spec `待确认`、暂停 Task02A-D/E 及后续业务实现。
- 复审耗时：约 10 分钟。
