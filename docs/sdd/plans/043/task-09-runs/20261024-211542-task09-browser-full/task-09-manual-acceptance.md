# Task09 真实浏览器人工验收案例

最终裁决：`BLOCKED_PENDING_ROOT_FINAL_GATES`。

本运行时案例的地图交互、摘要队列、知识库全文门禁、全文分析结果和会话草稿均已有真实页面证据；但 Spec 043 的最终全量回归、覆盖率门禁和最终签字仍由主会话（root）完成，因此本文件不把 Spec 标记为完成，也不要求用户代替 Agent 排查。

## 1. 真实环境与实体

- 入口：`http://127.0.0.1:8000/#literature-maps-view`
- 探活：`GET /api/health = 200`
- 资源：`literature-maps.js?v=18`、`literature-maps.css?v=12`、`app.js?v=60`
- 浏览器：Chromium `156.0.8078.47`，本次截图 viewport `1440×1000 CSS px`
- 本次全文页面地图：`API E2E graph attention networks`，`map_id=9b1e4739443e40c98400cfb69aec1e45`
- 本次全文页面节点：`Exploring Visual Relationship for Image Captioning`，`node_id=2e35b888d3cb414090e2d8e55e5bae1a`
- 真实知识库文档：`document_id=ae3a1c3f7ee746bba031b06306ff3230`，PDF 为 `2018-Conference-Exploring-Visual-Relationship-for-Image-Captioning.pdf`
- 全文分析：`analysis_id=04ff00a37f8247379878ecaf7fc6703e`，`job_id=ca2e1852b8cc49cab80300c84347c89c`
- Fresh 自动摘要主例：`Task09 live graph attention networks 20261024-153416`，`map_id=858b78f0d9e047efa6d8d1559d83a6de`；真实状态保留为 20 节点、11 条关系、18 篇非空摘要、2 篇无摘要安全跳过、地图 `partial`。

浏览器没有使用 fixture、mock 或假数据；本次没有点击重新生成、导入、下载、重索引或全文分析按钮。页面打开时产生的 `analysis-queue/ensure` 是既有地图打开所需的幂等请求；禁止的 analysis/import/reindex/download/regen/message 请求均为 0。完整 API 状态轨迹及后台唯一一次合法 v1 reindex/full analysis 见 [`evidence.json`](../20261024-210815-task09-full-analysis-v1/evidence.json)。

## 2. 关键真实结果

在目标节点详情中，页面实际显示：

- `indexed`
- `已加入知识库 · 文档 ID：ae3a1c3f7ee746bba031b06306ff3230`
- `在知识库中查看`
- `入库状态：indexed。`

AI 面板实际显示可用依据为“摘要级、全文索引片段依据”，并显示摘要 source version `de788f55ac4bf0fa28bb823fbc2adf27f1be389b6ea329e742ac5eca970b30aa` 和全文 source version `70ed7281386eae343d39c479e8dec6962c8cd3954659db1e3d26b33c53aba862`。

选择“全文”页签后，实际页面显示：

- 页签已启用且选中；
- `v2 · 全文索引片段依据 · 已完成`；
- `全文分析结果（全文索引片段依据）`；
- `依据：全文索引片段依据 · 版本：70ed7281386eae343d39c479e8dec6962c8cd3954659db1e3d26b33c53aba862`；
- 非空全文结果，页面显示 `受控来源引用：6 条`。

API 交叉证据报告该结果为 592 字符、5 条 citation records，且所有 `citation_document_ids` 均为目标 document；页面的 6 条是 UI 的受控片段计数，两者都保留真实值，不互相改写。切换“摘要”再切回“全文”后，摘要历史 `v1 · 摘要级 · 已完成` 和 `摘要级分析结果（仅基于摘要）` 仍可读。

截图：[`01-full-analysis-ready.png`](screenshots/01-full-analysis-ready.png)。机器可读浏览器证据：[`browser-e2e.json`](browser-e2e.json)。

## 3. 可由无上下文用户复现的人工步骤

### 步骤 0：打开入口并确认候选版本

1. **点击/输入**：在浏览器打开 `http://127.0.0.1:8000/#literature-maps-view`；若仍在其他工作区，点击左侧主导航“文献地图”。
2. **点击后提示**：页面标题区域显示“文献地图 / LITERATURE MAPS”，并出现“刷新状态”“新建地图”和“我的地图”。
3. **等待**：等待地图列表加载完成；条件是出现地图卡片，不以固定秒数代替。
4. **等待中显示**：列表可能短暂为空或显示加载；不要新建第二张 Task09 地图，也不要把空列表当作生成失败。
5. **下一步**：继续步骤 1，选择已存在的 `Task09 live graph attention networks 20261024-153416` 或 `API E2E graph attention networks`。
6. **失败恢复**：若入口无法加载，先确认 `GET /api/health=200`；若服务或资源版本不是本节列出的 v18/v12/v60，停止验收并交给 root，不由用户排查或重启服务。

### 步骤 1：打开 fresh 自动摘要主例

1. **点击/输入**：在“我的地图”中点击卡片 `Task09 live graph attention networks 20261024-153416`。
2. **点击后提示**：地图标题和主题显示；图谱区域显示节点，状态提示为“地图部分完成；已保留可用节点并标注失败阶段。”（实际卡片状态为“部分完成”）。
3. **等待**：等待图谱节点可见且摘要队列出现终态；成功等待条件是 20 个节点、11 条关系，队列显示 `状态：已完成`。
4. **等待中显示**：摘要面板显示 `完成 18/20 · 排队 0 · 运行 0 · 失败 0 · 跳过 2`。两篇跳过表示没有可用摘要，不得用论文标题冒充摘要结果。
5. **下一步**：在图谱中查看作者/年份短标签，继续步骤 2；可离开再返回验证持久状态，不要为跳过节点点击模型重新生成。
6. **失败恢复**：临时错误或失败项应使用页面“重试失败单元”；跳过项没有摘要时保持跳过。若队列仍 `running/queued`，继续等待真实状态变化，不重复打开地图来制造新任务。

### 步骤 2：验证标签三档、节点选择与图形等待条件

1. **点击/输入**：依次点击工具栏“标签”下的“全部”“选中及相邻”“隐藏”。在节点重叠时，先让目标圆点获得可访问焦点，再按 `Enter` 选择。
2. **点击后提示**：fresh 主例的标签数量分别为 20、7、0；“隐藏”只隐藏标签，节点仍可选择。目标标签示例为 `Petar Velickovic et al., 2017`（v17/v18 窄验中每个标签只含一个 `et al.` 和四位年份）。
3. **等待**：每次切换后等待 DOM 中节点和标签数量稳定；节点位置、关系和保存的视图不能改变。
4. **等待中显示**：图谱仍保留 20 个节点；标签切换不会触发新的建图或模型分析。滚轮缩放等待变换值更新后再取屏幕点对应的世界坐标。
5. **下一步**：在非画布中心留白点滚轮，确认锚点不漂移；使用工具栏“+”“−”时以画布中心为锚点；打开详情或滚动页面后重复一次。
6. **失败恢复**：若标签出现 `undefined`、`null`、空白或重复 `et al.`，保留截图与 run，不把该次验收判为通过；若缩放越界或节点位置变化，重置视图后交给实现/评审，不修改用户布局。

### 步骤 3：打开全文节点详情

1. **点击/输入**：选择地图卡片 `API E2E graph attention networks`，在图谱中选择标题为 `Exploring Visual Relationship for Image Captioning` 的节点；若 SVG 圆点被邻近节点遮挡，用键盘焦点 + `Enter`，这是同一真实可访问入口。
2. **点击后提示**：右侧“论文详情”显示标题、作者 `Ting Yao、Ying-Wei Pan、Ye-Hao Li、T. Mei`、年份 `2018`、来源 `European Conference on Computer Vision`、引用数 `934`，以及 `indexed`。
3. **等待**：等待详情中的 AI 面板读取节点分析与 source status；只读打开详情只应出现 GET，以及页面已有的幂等 `analysis-queue/ensure`。
4. **等待中显示**：知识库区域显示“已加入知识库 · 文档 ID：ae3a1c3f7ee746bba031b06306ff3230”“在知识库中查看”“入库状态：indexed。”；AI 区域显示摘要和全文 source version。
5. **下一步**：确认文档 ID 与本案例一致后，点击 AI 区域的“全文”页签；不要点击“重新生成全文（会调用模型）”。
6. **失败恢复**：若详情显示文档缺失、owner/project 不匹配或全文未就绪，不拿 `indexed` 标签冒充全文 ready；保留旧摘要结果并按页面实际引导处理，必要时停止并报告阻塞码。

### 步骤 4：验证摘要结果及历史保留

1. **点击/输入**：在 AI 面板点击“摘要”页签。
2. **点击后提示**：实际显示 `v1 · 摘要级 · 已完成`、`摘要级分析结果（仅基于摘要）` 和摘要 source version。
3. **等待**：等待历史卡片和正文出现；已完成结果出现后不需要再点任何生成按钮。
4. **等待中显示**：若用户明确触发摘要重新生成，页面应显示“重新生成摘要（会调用模型）”并进入 `queued/running`，旧 v1 正文仍可读；本次最终全文复核不重复触发昂贵模型。
5. **下一步**：切换到“全文”页签，验证全文结果；回看“摘要”时 v1 仍应保留。
6. **失败恢复**：若新版本失败，使用页面重试入口；不得清空、覆盖或把失败新版本当成旧摘要成功。fresh 主例唯一一次手动摘要再生成的真实 ID 为 `42cf77712d7c430fb4b4311a3d573931`（job `3264b0f9e3cf4e5f9183c9e4a6faf95c`），该动作已在旧 run 记录，本案例不重复执行。

### 步骤 5：验证全文页签、非空结果与依据

1. **点击/输入**：点击“全文”页签；在结果已完成时，不点击“重新生成全文（会调用模型）”。
2. **点击后提示**：页签保持选中且可用，显示 `v2 · 全文索引片段依据 · 已完成`、`全文分析结果（全文索引片段依据）` 和 `依据：全文索引片段依据`。
3. **等待**：如果是首次触发全文分析的合法人工验收，等待页面状态从 `queued` → `running` → `completed`，并等待 `result_present=true`；本次只读复核使用已完成真实结果。
4. **等待中显示**：等待期间保留摘要 v1；全文结果出现后显示非空正文和受控来源引用。当前结果的 source version 是 `70ed7281386eae343d39c479e8dec6962c8cd3954659db1e3d26b33c53aba862`。
5. **下一步**：读取全文结果和受控引用；必要时切回“摘要”确认 v1 历史，再切回“全文”。最终产物路径由 API artifact 和页面详情共同给出，不需要下载 PDF。
6. **失败恢复**：若全文页签仍显示“全文索引尚未就绪；请先主动入库并等待索引完成。”和“打开知识库处理全文”，不得自动下载、导入或生成全文分析；按正式知识库/索引恢复流程解除 gate 后重新打开节点。该文案是本 run 之前 `legacy_unknown/indexedhashnull` 阶段的真实未就绪分支，当前目标已由合法 v1 reindex 恢复为 manifest ready，不应把旧文案或 KB 列表的 `indexed` 单独当成 full ready。

### 步骤 6：验证“关于本篇提问”只预填、不覆盖、不发送

1. **点击/输入**：在目标节点详情点击“关于本篇提问”。若主聊天的 `#question` 已有草稿，例如 `用户已有草稿：请不要覆盖（Task09 indexed/full runtime）`，先保留该文本。
2. **点击后提示**：真实会话桥打开论文会话并显示可编辑输入框；有旧草稿时保留原文并显示“插入建议问题”。无旧草稿时预填包含论文标题、作者/年份、研究问题、方法、结论、局限和证据等级的建议。
3. **等待**：等待会话创建响应和输入框可见；本次真实草稿现场 conversation 为 `bedb0cdcb5194095abf35a1e464c493f`，只创建/打开会话，不提交消息。
4. **等待中显示**：输入框中的旧草稿不被替换；浏览器网络中没有 `/messages` POST、SSE 或助手消息。
5. **下一步**：用户可以手动编辑草稿；只有用户明确点击既有聊天的发送按钮，才进入发送步骤。全文后来 ready 时，只开启新的全文依据会话，不静默升级旧摘要会话。
6. **失败恢复**：如果草稿被覆盖或出现发送请求，立即停止该验收并保留网络记录；不要通过刷新或再次点击来掩盖覆盖。恢复方式是返回地图、重新打开节点并在发送前核对草稿。

### 步骤 7：保留真实失败/限流路径

1. **点击/输入**：只读打开历史失败地图 `map_id=0baabeae7268429c9f7e4de8098ae1d0` 的节点 `node_id=56c7189f4f9343c98be3f9a95563cfd6`；不要点击“人工重试入库”。
2. **点击后提示**：实际页面显示“失败原因：Semantic Scholar 提供方暂时限流；arXiv 身份匹配不确定。”“当前可人工重试；不会自动重试。”“人工重试入库”“入库状态：失败。”
3. **等待**：等待诊断 GET 完成并确认 `document_id=null`、`retryable=true`；不需要等待 provider 自动恢复。
4. **等待中显示**：全文来源版本为“未提供”；页面不自动下载、不自动导入、不自动创建全文分析。
5. **下一步**：只有用户明确决定恢复时才点击“人工重试入库”；本 Task09 浏览器 run 不执行该动作。
6. **失败恢复**：将 `SEMANTIC_SCHOLAR_RATE_LIMITED` 与 `ARXIV_MATCH_UNCERTAIN` 作为来源/元数据诊断记录，不称作模型失败，也不把该失败节点当作 fresh 全图成功。fresh 主例的 2 个 skip 同样保留真实状态。

## 4. 产物查看路径与请求边界

- 本次真实截图：[`screenshots/01-full-analysis-ready.png`](screenshots/01-full-analysis-ready.png)
- 本次浏览器结构化证据：[`browser-e2e.json`](browser-e2e.json)
- 合法 v1 reindex + full analysis API 证据：[`../20261024-210815-task09-full-analysis-v1/evidence.json`](../20261024-210815-task09-full-analysis-v1/evidence.json)
- Fresh 图形/队列/标签主例：[`../20261024-153416-task09-live-graph/task-09-browser-e2e.md`](../20261024-153416-task09-live-graph/task-09-browser-e2e.md)
- v17 标签窄验：[`../20261024-155602-task09-label-v17/task-09-browser-e2e.md`](../20261024-155602-task09-label-v17/task-09-browser-e2e.md)
- v18 窄画布、详情、失败诊断：[`../20261024-204619-task09-v18-narrow/task-09-browser-e2e.md`](../20261024-204619-task09-v18-narrow/task-09-browser-e2e.md)
- indexed 但 full gate 尚未恢复的旧阶段：[`../20261024-205007-task09-import-full/stage-result.md`](../20261024-205007-task09-import-full/stage-result.md)

本次浏览器阶段没有读取 PDF 正文、没有下载文件，也没有新建地图或假节点。API artifact 中的 `reindex_post_count=1` 和 `analysis_post_count=1` 是主会话/API tester 负责的唯一既有恢复与全文分析动作；本次浏览器只读复核未重复这些 POST。

## 5. 准备度矩阵与最终裁决

本阶段“已完成功能”的真实浏览器检查为 10/10：服务可访问、真实地图实体存在、参数/状态可观察、处理中与完成提示可见、摘要和全文产物真实存在、失败诊断有人工恢复路径、页面与 API source version 一致、步骤可独立复现。

但按 Spec 043 收口门禁，最终裁决仍为：`BLOCKED_PENDING_ROOT_FINAL_GATES`。

- 阻塞项：root 尚需完成当前候选的全量回归、覆盖率/最终验收签字与状态台账收口。
- 已解除项：目标 document 的 v1 source hash 已 verified，manifest 已 ready；全文 source gate 已 `fulltext_ready=true`；全文分析已 completed，非空结果和目标 document citations 均真实存在。
- 不应误报：fresh map 仍是 `partial`（18 non-empty + 2 skipped）；provider 限流/metadata 失败与模型成功分开；旧 `indexed`/full gate 缺失阶段的失败证据保留，不覆盖为成功。
- 用户交付：在 root 完成最终门禁并签字前，不把本案例作为“可直接交用户最终验收”的 Spec 完成声明；本文件已提供实际按钮、提示、等待、下一步、恢复和产物路径，用户不需要替 Agent 进行排错。
