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
