# Spec 043 — 交互式文献地图与自动主题探索

## 状态

**当前状态：已完成（2026-10-29 Task11 已通过最终回归、真实API/浏览器验证、tester/architect双签并部署8000）**。用户要求打开地图时合理放大；既有可用保存视图、节点位置和分组仍保留，后台刷新不打断手动操作。此前2026-10-24候选已通过独立复审、真实入库/全文API与浏览器、最终全量3384 passed/0 failed/2合法skip/67 subtests及覆盖率82.38%，部署8000；这些历史证据不代替本次前端定向验证。来源限流partial与缺摘要跳过仍按合同如实展示。
需求与技术独立评审均通过，用户明确授权实现；先执行Task02可行性门禁，通过后Task03冻结v1合同并实现桌面MVP。Spec032保持暂停。

## 一句话目标

用户输入主题即可自动生成并保存可探索的文献地图，区分真实引用与主题相似关系，并从节点查看论文、主动入库和继续探索。

## 背景与依据

- 截图参考为 LitGraph 风格：左侧工具/列表、中央图谱、右侧论文详情；不是要求复制另一个产品的代码或每项功能。
- Grilling Q1–Q27 均已确认：面向通用主题，自动首批与按需扩展，独立地图可绑定项目，桌面纵向 MVP 优先，后续补 AI、分组导出与手机。
- 自动搜集目标为有界的 C，不降为只能从既有论文手动构图的 B。缺少可选元数据不构成降级理由。
- 本 Spec 不依赖 Spec032 正式报告生成。032 保持暂停；只复用已存在模块，遇必要接缝缺陷在本任务记录，不恢复其全部范围。
- 目前只有 API/client、目录 RAG、研究 Claim 资产；不能将它们描述为已有可用文献地图。Claim 的支持/反对不是论文间引用。

## 数据模型

| 实体 | 核心字段 | 约束 |
|---|---|---|
| LiteratureMap | map_id、owner_id、name、topic、project_id、filters、revision、view_settings、timestamps | 独立保存；主题非空；project 可空；所有写入校验 owner |
| MapPaper | node_id、map_id、external_ids、metadata、provenance、catalog_paper_id、document_id、position、group_id | 稳定 ID；外部 ID 含 S2/DOI/arXiv；目录与 KB 关联可空 |
| MapEdge | edge_id、map_id、kind、source_id、target_id、provenance、score、basis、model_version、content_hash | citation 有向；similarity 无向端点排序去重；不允许自环 |
| MapJob | job_id、map_id、operation、status、step、cursor、counts、failed_units、idempotency_key | 操作为 create/expand/refresh/repair；持久恢复，不伪装 research task |
| MapEvent | map_id、job_id、event_seq、type、safe_payload、created_at | 单调游标；只输出安全状态、ID、计数和可行动错误 |
| MapPreview | preview_id、map_id、base_revision、operation、candidates、diff、status | 预览不修改已保存地图；确认必须通过版本及预算检查 |
| MapRemoval | map_id、paper_identity、removed_at | 普通补缺不自动加回已移除论文；显式重新加入可清除记录 |
| MapAnalysis | analysis_id、map_id、node_id、evidence_level、source_version、status、result_ref | 摘要自动排队；全文用户触发；分版本保存，不覆盖旧分析 |
| 请求/向量缓存 | request_key、response/provenance、content_hash、model_version、status | 元数据/引用缓存跨地图复用；不得包含密钥；不写个人 KB Collection |

- 复用现有 SQLite 迁移与事务模式，增量建表，不删除原有数据；地图专属仓储放独立 literature_maps 领域。
- 共同身份优先通过确定匹配的外部 ID 关联；S2 paperId 不能硬塞为 catalog_paper_id。只凭标题近似不能自动合并。
- 同图稳定身份去重；不确定记录保留为未合并并显示依据。地图节点不是强制已下载的知识库文档。
- 项目删除仅解绑地图；删除地图清除其专属节点/边/偏好/分析关联与作业，不删除共享目录、缓存、KB 原件或既有会话。
- 项目删除接缝必须owner-scoped且fail-closed：地图解绑失败则保留项目并返回稳定错误，不留下已删除项目的悬空绑定。

## 端点 / 接口

资源前缀为 `/api/literature-maps`；详细请求/响应由 Task03 冻结 v1 后供后续 Task 版本化扩展。

| 动作 | 接口与关键输入 | 成功与失败边界 |
|---|---|---|
| 地图列表/创建 | GET/POST 集合；topic、可选 years/source/conference/project、limit=20/30/50、idempotency_key | 默认 30；创建 202 返回 map_id/job_id/status；400 非法范围；不创建审批 |
| 读取/更新/删除 | GET/PATCH/DELETE /{map_id}；更新 expected_revision | 本地保存状态；owner 隔离；404 不存在/不可访问；409 版本冲突 |
| 图与节点 | GET /{map_id}/graph；GET /{map_id}/nodes/{node_id} | 节点/关系/布局/来源/缺失状态；下载入口不因读取而执行 |
| 布局及视图 | PATCH /{map_id}/view；positions、filters、viewport、expected_revision | 原子应用；冲突重新读取；不覆盖他人更新 |
| 事件与作业 | GET /{map_id}/jobs/{job_id}；GET /{map_id}/events?after_seq=；POST jobs/{job_id}/stop 或 /retry | 持久进度；停止保留成果；重试仅 failed/missing 单元 |
| 扩展/刷新预览 | POST /{map_id}/previews；operation=topic/references/citations/refresh、node_id、scope | 返回 preview_id/job_id，不直接加入；主题继承原地图范围 |
| 确认预览 | POST /{map_id}/previews/{preview_id}/apply；selected_ids、expected_revision、idempotency_key | 显式确认；每次新增最多 20；总节点不超 200；409 过期/版本冲突 |
| 移除/重新加入 | DELETE /{map_id}/nodes/{node_id}；重新加入复用 preview/apply | 移除仅地图内关系；墓碑防补缺复活；显式加回仍去重 |
| 主动入库 | POST /{map_id}/nodes/{node_id}/imports | 桥接既有安全下载/导入，返回现有句柄；不另造下载器 |
| AI/会话 | POST /{map_id}/nodes/{node_id}/analyses；POST /{map_id}/nodes/{node_id}/conversations | 摘要自动排队、全文手动；返回既有句柄与 evidence_level；项目绑定校验；单复数以已冻结实现合同为准，不另造同义接口 |
| 分组与导出 | 地图分组资源；GET /{map_id}/export?format=json；PNG 为前端图谱快照 | JSON 保留身份、依据、版本；PNG 不含凭据和临时工具 UI |

所有命令幂等，非幂等内容变更沿用 expected_revision；同一 key 不得执行不同参数。图查询、预览及作业状态不因读取隐式下载。错误使用现有结构化错误包，区分未配置/限流/来源失败/向量不可用/冲突。

## 产品行为与界面

### 主题自动建图

1. 主题必填，其他筛选可选，年份默认不限；limit 默认 30，允许 20/30/50。没有研究目标必填项和研究计划批准。
2. 通用发现以现有 S2 Academic Graph 为主，限定已支持会议时官方目录优先，再聚合补缺。不能把 venue 标签冒充官方认证。
3. 按相关性选首批，在选中集合内补引用和相似关系；不会自动递归添加引用邻居。真实候选不足返回 partial 与实际数，不拿不相关论文凑满。
4. 显示“寻找论文 → 补充元数据与引用 → 计算相似关系 → 地图可用”，分段展示节点，不等待所有字段齐全；不承诺固定秒数。
5. 后台保存，离开页面不停任务；显式停止在安全边界停止后续获取，保留已完成结果。重启恢复既有作业，不重新创建整图。
6. 打开只读本地，刷新先预览差异再确认；节点位置、人工分组、移除记录不被刷新覆盖。

### 引用与相似关系

- 引用为“引用者 → 被引用者”实线箭头，保留来源；references/citations 响应方向必须归一，缺失不能视为没有引用。
- 相似为无向虚线，基于既有 embedding 的 dense 向量余弦；每节点选择阈值至少 0.75 的 top-3 邻居后无向去重。最终无向度数可能大于 3，不把 top-3 误写为度数硬上限。
- basis 为 title_abstract 或 title_only，模型版本与内容摘要哈希用于缓存失效；不以阈值保证每节点必有边。
- 向量不可用时保留引用图和元数据，标记相似层待补算；无关系论文允许孤点。不造引用、支持、反对或关键词。
- 默认两层开启，可独立关闭；选中高亮邻居，其他连线淡化。引用关系不为画面简洁而删掉持久证据，可视觉弱化。

### 布局与交互

- 主导航增加“文献地图”，复用现有应用侧栏。工作区左侧为地图列表、新建和筛选，中间图谱，右侧为可关闭详情。
- 浅色背景、现有紫色风格与紧凑控件，参考截图布局而非复制其论文/关系数据。
- SVG 独立组件，受限迭代布局及动画帧调度；200 节点拖动/缩放不得持续阻塞主线程，不能每次点选全量重新布局。
- 支持缩放/平移/适应画布/定位/拖动与保存位置，按年份及下载状态筛选；隐藏不等于移除，移除不等于删除 KB。
- 节点默认全部显示第一作者（多作者加 et al.）与年份，缺作者回退短标题，缺年份标“年份未知”；悬浮显示全标题。提供全部/仅选中及相邻/隐藏三档，局部避让不改已保存节点位置，不承诺200节点零重叠；缩小时保持文字可读下限。
- 半径为 min(28, 8 + 2 × ln(1 + citation_count))，引用数为来源元数据总被引数，不是图内度数；缺失使用最小尺寸但显示“未知”。固定尺度，不随地图扩展归一化；选中用描边而非改变半径，标签偏移随半径调整。颜色仍为默认或人工分组，不推断学术立场。
- 滚轮以鼠标对应图谱坐标为缩放锚点，工具栏加减以可视画布中心为锚点，双指以中点为锚点；验证非中央、留白、页面滚动及详情面板切换后的坐标。
- 详情显示真实标题、作者、年份、发表来源、摘要、原始关键词、可取得引用数及来源、下载/索引状态；缺失明确标记，不由模型填充。

### 后续 AI、会话、整理与手机

- 摘要自动分析：新增节点后台持久排队，旧地图首次打开为缺失分析补入队；默认逐篇执行，不阻塞建图或浏览，离页继续、重启恢复。按确定论文身份、摘要内容及分析配置复用结果，重开不重复调用；摘要变更生成新版本。无摘要明确跳过，不用标题冒充摘要分析。自动分析仅使用已保存摘要，不因打开地图重新检索元数据或下载。
- 显示完成/总数、排队及失败数；临时错误/429有限退避，配置/鉴权错误暂停并提示修复；支持当前地图暂停/继续、重试失败项。暂停不影响建图/聊天，当前一篇可完成，后续等待；手动重新生成明确提示模型调用并幂等，旧版可读，新版失败不清空旧版。
- 摘要/全文分析分页显示各自状态、依据及历史；全文成功后切至全文页签但保留摘要。全文不可用时显示获取全文、登录/上传/重试、索引等待/修复等实际入口，复用现有安全导入与恢复；全文下载且索引可用、owner/document allowlist通过后才手动分析，不自动下载或自动生成全文结果。
- 关于本篇提问复用既有会话与确定论文上下文，新会话预填可编辑解读Prompt，不自动发送、不覆盖旧草稿；有草稿时提供“插入建议问题”。标注仅摘要/全文索引片段；全文后来就绪时提示开启全文会话，不静默升级旧会话依据。
- 论文问答复用现有 conversations，绑定 map/node 上下文；新会话继承当时地图项目，未绑定项目不使用项目记忆。后续解绑不追改旧会话。
- 人工分组、PNG 和 JSON 导出在 MVP 后完成；不做自动聚类。
- 手机在独立 Task 提供触控缩放/平移、论文详情抽屉、搜索与扩展，避免三栏硬挤屏；MVP 只验收桌面。

## 现有实现复用与替换边界（实现硬约束）

| 资产 | 既有位置 | 复用方式及缺口 |
|---|---|---|
| Academic Graph 搜索/详情/引用与全局限流 | backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py | 复用 batch/search_bulk/graph_edges、解析器与1秒限流；地图负责持久缓存，不抓 Reader HTML |
| 目录身份/来源 | backend/app/paper_discovery/domain/paper_discovery.py；infrastructure/paper_discovery_store.py | 确定匹配才关联目录，不改会议身份为通用 S2 ID |
| 向量能力 | backend/app/paper_discovery/application/catalog_search_graph.py 的 CatalogRagAdapter | 复用 embedding 客户端；地图两两相似是新增应用算法，不新建模型服务/个人KB Collection |
| 作业与事件 | backend/app/api/common.py；routes_paper.py；目录任务模式 | 共享执行器/恢复思想，但独立 map job 语义、owner 与事件计数 |
| 原文导入/恢复 | backend/app/api/routes_paper.py；routes_kb.py 既有链 | 只桥接返回句柄，安全下载/登录/上传/补偿不重写 |
| 项目和会话 | backend/app/api/routes_conversations.py | 复用 owner/project 和文档范围门禁；不另建聊天系统 |
| 前端壳 | frontend/index.html；frontend/app.js 的 showView | 新独立地图组件/视图，保留 DOM 和资产版本约定 |

实现前先核对接口缺口；不适配时优先参数化/窄适配器，不能因“复用”拒绝必要修改，也不能绕过接口复制第二套实现。Spec032 下的 Claim/Matrix 不作为地图引用图的存储模型。Semantic Scholar 已有 batch enrichment 的进程缓存不等于已有持久 graph/search 缓存。

## 边界与失败场景

- 空主题、非法年份、重复 ID/外部身份冲突、无匹配/不满目标数、同一预览重复确认、图满 200、单批超过 20均有测试。
- 外部429沿用 Retry-After和有限退避，单进程共用1 RPS；多进程共享限流不在本期。缺 key/未配置必须可行动提示，不回传凭据。
- 零引用、孤点、标题级相似、向量中断、单来源失败可 partial，不把 partial 当完整。source/embedding错误分开显示。
- 后台取消、进程重启、浏览器离开/重开与并发写入不丢已完成结果；删除地图不被旧作业复活。
- 任何跨 owner/project/node/job/preview访问必须拒绝；PNG/JSON不得包含 Cookie/API key/内部 prompt。
- 按地图当前项目创建会话，不复用到错误项目；正文/元数据不进入错误论文的全文问答。
- 显式用户移除与 source 新增的差异冲突先预览，不静默加回。
- 停止/重试/API E2E 不篡改旧研究任务或清理用户修改。

## 明确不做

无限抓取、自动 PDF 下载、自动聚类、整图综述、论文整体支持/反对判断、新下载器、新 embedding 服务、新聊天框架、新图数据库、千节点大图、跨机器分布式调度、自动 push/合并 main、恢复 Spec032 全部开发。
截图的 AI 面板不在桌面首个 MVP 完成；手机不在 Task03 验收。

## 产品使用步骤（规划核心场景；确认后由 doc-updater 细化）

1. 点击主导航“文献地图”→“新建地图”，输入“模糊测试与漏洞发现”，可选 USENIX Security/2024 和20篇，点击“开始建图”；显示作业阶段和节点计数，不要求批准。
2. 等待来源获取，先出现节点，引用/相似层逐步补充；partial/等待重试/相似不可用均展示具体提示。选择真实节点，右侧显示该论文及来源，不自动下载。
3. 切换两种关系、缩放拖动并保存，离开后重开，节点/位置/筛选保留且不自动联网。
4. 点击继续主题探索，或选中节点点“参考文献/引用它的论文”，预览候选勾选后确认；显示新增/重复/达上限结果。
5. 点击“加入知识库”才进入原有导入流程；失败给登录/上传/重试入口，成功后节点状态更新；移除节点不删 PDF。
6. 节点加入后观察后台摘要分析进度；打开详情查看摘要结果或重新生成，全文页签按实际状态引导获取/索引/手动分析。关于本篇提问跳转并预填草稿，用户修改后自行发送；人工分组、PNG/JSON导出与手机操作保持现有行为。
7. 最终手工步骤须基于真实部署补齐：精确按钮、每步提示、等待条件、恢复和结果路径。此处主题仅为候选，不声称已跑通；Task02选择并落盘可复现真实主题。

## 验收方式与证据

- MVP必须有真实 API 创建→完成/明确partial→真实论文和引用→图保存读取的证据，以及实际浏览器截图；真实 API 验收不使用写假图替代。
- 相似模型可用时验证真实相似边及依据；不可用时单独验证降级，但最终不能仅降级就宣称相似功能已验收。
- 相似阈值不保证任意主题存在边；Task02选择真实相似对，并记录依据，禁止降低阈值凑数。
- 最终涵盖真实扩展预览/确认、停止与重启、项目删除解绑、地图删除不删原件、AI依据、导出与手机。
- 每个 Task只跑精准及受影响测试；Task08最终候选全量回归，修复后重跑最终全量。
- 人工交付准备度至少9/10，且无P0/P1、API E2E失败或关键产物缺失。记录命令/退出码/通过数量/请求响应/实体ID/终态/产物路径。
- 部署必须真实验证首页及ready/相关接口，报告实际地址、端口、命令；仅启动进程不算可用。

## 回滚与隔离

建档时仓库为 codex/spec032-final-acceptance，HEAD bc0da65，工作区干净；这是基线事实，不是本 Spec 实现分支。实施前创建本 Spec 分支，保留032暂停快照。新增领域表与前端入口可独立禁用；迁移前备份实际数据库。失败不reset/stash/clean、不删KB数据、不覆盖其他工作。

## 执行配置

架构师：自身，64k–200k。其余模型基线来自2026-10-19读取的角色model字段 `Deepseek-V4.1-Flash`，只是当前配置快照；实际分派遵循当次用户临时指派，不修改角色文件或长期规则，不把临时模型写成规范。未来使用本地模型时才核实 ollama list；本轮不调用模型/服务。

| 职责 | 实际角色 | 模型/上下文 | 分派与边界 |
|---|---|---|---|
| 架构师 | architect（主会话） | 自身 /64k–200k | spec、决策、门禁总控；本次纯文档由主会话落盘 |
| 产品使用步骤 | doc-updater | 当前角色配置；32k | 确认后只补使用步骤与真实验收旅程 |
| 需求/技术/代码评审 | architect；backend-reviewer/frontend-reviewer | 当前角色配置；32k–64k | 独立实际评审；不虚构模板中的旧角色名 |
| 开发 | backend-dev、frontend-dev | 当前角色配置；32k | 分端分派，代码与测试各自范围；无跨端通吃分派 |
| 测试 | backend-tester、frontend-tester；tester总控 | 当前角色配置；32k | 精准验证、最终全量与真实验收汇总 |

纯文档落盘由主会话代行，非独立需求/技术/验收评审；不包含业务代码。代行说明同步于README与本次变更日志。

## 任务计划

### Task05 真实验收补充：共享池来源解析

2026-10-21，Spec018修复后目标PDF已真实发布v1 ready/verified；全文仍不可用的剩余原因是既有`list_documents_for_project(None)`过滤条件要求存在非空项目关联，而解绑行为会删除关联，导致共享池永远为空。沿当前已确认全文/owner隔离范围修复：未绑定范围只读取合法canonical且无项目关联的共享记录；任何已关联其他owner或项目的记录均不得落入共享池，指定项目仍严格owner/project匹配。不得从map node的document_id反推授权，不手写生产关联、不新增sidecar schema；补真实helper共享池/跨owner排除测试后独立复审，再重跑当前部署全文E2E。

| 编号 | 标题 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | Spec与规划文档 | 本文件 | — | 已完成（仅建档） |
| 02 | 准备与可行性门禁 | [Task02](../plans/043/task-02-validate-feasibility.md) | 01 | 已完成（Go） |
| 03 | 桌面自动建图 MVP | [Task03](../plans/043/task-03-desktop-map-mvp.md) | 02 | 阶段已完成（PASS_WITH_LIMITATIONS） |
| 04 | 扩展与恢复 | [Task04](../plans/043/task-04-expansion-recovery.md) | 03 | 阶段已完成（PASS_WITH_LIMITATIONS） |
| 05 | AI分析与会话 | [Task05](../plans/043/task-05-analysis-conversations.md) | 04 | 阶段已完成（摘要/全文API与真实界面PASS） |
| 06 | 整理与导出 | [Task06](../plans/043/task-06-groups-exports.md) | 04 | 阶段已完成（真实API/PNG/JSON PASS） |
| 07 | 手机适配 | [Task07](../plans/043/task-07-mobile-map.md) | 05、06 | 阶段已完成（真实375/390/桌面PASS，非真机） |
| 08 | 最终验收与收口 | [Task08](../plans/043/task-08-acceptance-deploy-retro.md) | 02–07 | 已完成；全量3224通过，真实API/浏览器/独立验收签字通过 |
| 09 | 图谱交互与自动摘要修订 | [Task09](../plans/043/task-09-map-interaction-analysis.md) | 03、05、07旧版资产 | 已完成：不可用操作反馈；最新51项前端测试、独立签字及真实页面通过 |
| 10 | 地图间距、配色与详情反馈 | [Task10](../plans/043/task-10-map-usability.md) | 03、05、06、07、09历史资产 | 已完成（Task10双签，498b6ded） |
| 11 | 论文关联扩展与后台分析 | [Task11](../plans/043/task-11-paper-expansion.md) | 04、09既有资产 | 已完成（7364a26b，真实双向扩展/手机链与双签） |

## 评审记录

- 需求评审：[043-requirement-review.md](../reviews/043-requirement-review.md)（独立评审通过，2026-10-19）。
- 技术评审：[043-tech-review.md](../reviews/043-tech-review.md)（独立评审通过，2026-10-19）。
- 验收评审：[043-acceptance-review.md](../reviews/043-acceptance-review.md)（独立tester与architect通过，2026-10-22；READY_FOR_USER，签字后准备度10/10）。
- 建档为主会话纯文档代行；需求、技术、实施和最终验收分工真实执行。部署地址 http://127.0.0.1:8000/ ，启动命令 `PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`。保留provider partial、非物理真机及RRF降级限制；Spec032仍暂停，不push或合main。
- 人工验收阶段 UX 缺陷复审：[043-node-style-disclosure-frontend-review.md](../reviews/043-node-style-disclosure-frontend-review.md) 与 [043-node-style-disclosure-frontend-regression.md](../reviews/043-node-style-disclosure-frontend-regression.md)（四轮独立复审通过、0 阻塞；单端回归 READY，含真实浏览器可见性与变异验证；第三、四轮结论均追加于同两份报告）。第四轮另由主会话落盘[当前部署版本真实服务端到端证据与人工验收步骤](../reviews/043-node-style-disclosure-live-e2e.md)：真实地图 `0baabeae…` 上验证「不修改直接点应用外观」与「多选模式应用到 N 篇」两条路径，并恢复测试写入的节点颜色。主会话仅代行纯文档，不含业务代码。

- 2026-11-07 卡片设置列表增量批次：[需求评审](../reviews/043-card-settings-requirement-review.md) 通过、[技术评审](../reviews/043-card-settings-tech-review.md) 通过、[后端评审](../reviews/043-card-settings-backend-review.md) GO（含 P0 增量复审）、[前端评审](../reviews/043-card-settings-frontend-review.md) GO（含 3 次 P1 集中复审）、[跨端验收](../reviews/043-card-settings-acceptance-review.md) 通过 16/16（tester 出具、architect 签字）、[合并裁决](../reviews/043-card-settings-merge-decision.md) APPROVE。分工真实发生，主会话仅做编排、最小增量落地校验与纯文档同步。

## 变更日志

- 2026-11-07：卡片设置列表 + 重命名／删除地图批次收口（详见文末「2026-11-07 卡片设置列表收口记录」）。用户 `直接开工` 确认选项 C 的 6 项默认值：`⋯` 先弹紧凑一级「卡片设置」列表（恰好 3 项：设置标签／重命名地图／删除地图），二级标签面板缩小到 `200×94.8`（原 `260×141`），760px 触发器 22→44px，复用既有 `PATCH /{map_id}` / `DELETE /{map_id}` 做重命名与删除，`delete_map()` 同事务清理标签绑定。跨端两次分派（`backend-dev` / `frontend-dev`）后经 4 轮定向修复：P0（`service._UNSET` 与 `store._UNSET` 非同一对象导致「只改 name」的 PATCH 503）、P1-01（删除刷新失败提示）、P1-02（内联 max-width 锁死二级宽度）、P1-03（空态高度 121.8>105）。`css?v=30→31`、`js?v=44→45` 双点 + 7 测试文件同步；前端 439 passed、后端 315 passed、真实 API E2E 16/16、真实浏览器 E2E 32/32、部署 `?v=31/45` 5/5 200。全量回归 `4011 passed / 2 failed / 67 subtests`，2 个失败位于 `tests/paper_discovery/`，HEAD 未改快照复跑同样失败、本批次零文件涉及，判为既有独立缺陷并建议另开 Bug Spec。评审与验收分工真实发生，主会话仅同步纯文档；临时 429 换档 `hy3` 已还原。仅本地提交，不 push、不合 main。

- 2026-11-07：七项合并批次收口（详见文末「2026-11-07 收口记录」）。用户授权子代理临时档位后解除 Gate 4 阻塞，跨端实现全部落地：后端新增 `literature_map_tags` / `literature_map_tag_bindings` 与 6 端点、列表 `tags` 派生、队列 `skipped_items` 投影、单篇会话 Intake 短路与分类器负向特征；前端新增标签区／⋯ 菜单／卡片徽标／标签筛选，修 5 项 UX/Bug，`css?v=29→30`、`js?v=43→44` 双点同步。回归 exit 0（后端 306 passed、前端 427 passed）、真实 API E2E 8 项全绿、真实浏览器 E2E 含三列 bottom `[1020,1020,1020]` 与「可用」筛选 5 张、跳过明细可见。需求／技术评审通过（附意见）、前端评审 GO、后端评审 GO（主模型代行）、验收通过 10/10（代行签字留痕）。部署 8000 重启生效（PID 29829，health/home/静态资源 200）。主模型代行仅限纯文档（后端评审、验收报告、评审记录／本日志／台账／复盘），实现与前端评审分工真实发生；仅本地提交，不 push、不合 main。

- 2026-11-05：用户人工验收反馈文献地图「节点样式」浮层一打开就展开，要求点击才弹出。两轮修复：①`frontend/literature-maps.js` 删除两处 `nodeStyleDisclosure.open = ...`（桌面默认展开、视口切换强制展开），`?v=37→38`；②真实浏览器复测发现仅删 `open` 不够——`literature-maps.css` 给 fieldset 显式 `display:flex` 覆盖 UA 折叠隐藏，补 `:not([open]) > .literature-map-node-style { display:none }`，CSS `?v=25→26`。新增 2 个按能力命名的测试（JS 契约 + 真实浏览器可见性）并同步全部版本号断言。`frontend-reviewer` 两轮复审通过（0 阻塞）、`frontend-tester` 两轮回归 READY（72 passed/0 failed、4 可见性用例、变异验证）；主会话浏览器复测：折叠 `display:none / 0×0`、点击展开 `flex / 416×47`、700↔1280 切换仍折叠、summary 常驻可点。主会话代行纯文档同步（评审记录、本变更日志、状态台账），无业务代码改动；实现、测试、两份评审报告同分支同提交，本地 ff 合并 main，未 push。

- 2026-11-05（第三轮）：用户反馈点击「应用外观」保存成功后节点样式详情不隐藏。根因：`frontend/literature-maps.js` 的 `saveNodeStyle()` 两个成功分支只更新状态、未收起 `<details>`，`refs.nodeStyleDisclosure` 此前只写不读。修复：在 `updateSavedNodeStyle()` 成功更新末尾统一置 `open=false`（失败 / 409 / 结果未确认路径保持展开以便重试），JS `?v=38→39`（CSS 仍 v=26），同步全部版本断言，新增 `node:vm` 四路径测试与真实浏览器用例。第三轮复审通过（0 阻塞）、单端回归 READY；主会话真实地图浏览器复测通过后恢复透明度原值。

- 2026-11-05（第四轮）：用户反馈「什么都不修改点击『应用外观』没反应」及「多选模式点『应用到 N 篇』设置页面不消失」。根因：①`renderNodeStyleControls()` 的 `apply.disabled` 含 `!dirty`、`saveNodeStyle()` 含 `!nodeStyleIsDirty()` 早退；②`applyNodeColor()` 成功后 `finally → renderMultiSelectControls()` 依据「多选仍开启且有选中节点」把颜色调色板重新显示。修复：无变更时按钮可用且走「零请求、收起详情、明确状态文案」分支；新增 `state.selectionPaletteDismissed`，成功后隐藏调色板，开启/退出多选与改变节点选择时重置，失败 / 409 / 未确认保持可见以便重试；刻意不退出多选、不清空选中集合。JS `?v=39→40`，同步 fixture 与 6 处 py 断言（含 2 处正则），新增 2 个测试并扩充 2 个既有测试。`frontend-reviewer` 第四轮独立复审通过（0 P0 / 0 P1 / 0 阻塞）、`frontend-tester` 单端回归 READY（`node --check` 退出 0、15 个 JS 测试 15/15、pytest 80 passed / 0 failed，2 项变异验证均被捕获并还原）。主会话在真实服务 v=40 上端到端复测两条路径通过，并落盘 [真实服务证据与人工验收步骤](../reviews/043-node-style-disclosure-live-e2e.md)；测试写入的节点颜色已恢复。主会话仅代行纯文档同步（评审记录、本变更日志、状态台账），无业务代码改动；实现、测试、报告同分支同提交，本地 ff 合并 main，未 push。

- 2026-10-24：Task09收口。标签/引用尺寸/鼠标锚点/持久自动摘要/全文引导/提问草稿及最后KB接缝修复已独立复核；原失败论文真实入库、合法v1 reindex和全文分析通过。首轮冻结矩阵快照失败保留，最小维护后最终全量3384 passed/0 failed/2合法skip/67 subtests/5 warnings、exit0、覆盖率82.38%。tester与architect双签10/10，主会话纯文档同步完成台账与复盘，已部署8000JSv18；仅本地提交，不自动push/合main。

- 2026-10-24：用户确认本轮Grilling Q1–Q15及鼠标中心缩放。Spec从历史已完成转本轮已确认；新增[Task09](../plans/043/task-09-map-interaction-analysis.md)，承接Task03/05/07的修订与Task08增量验收。主会话仅落盘文档（代行，非独立评审），未改业务代码；原需求/技术/验收签字仅证明旧候选，本轮须独立复核。

- 2026-10-22：分端开发/复审与独立tester/architect完成Task03–08，修复KB安全发布接缝、移动导航遮挡、API分层及测试竞态；最终a328932全量退出0（3224 passed、2合法skip、67 subtests、5 warnings），真实建图/扩展/stop/restart、全文问答、导出及浏览器通过。主会话纯文档同步状态与复盘，Spec已完成，仅本地提交。

- 2026-10-19：Grilling Q1–Q27与截图布局确认，选择自动有界主题图谱、独立项目绑定、分层引用/相似与阶段交付。
- 2026-10-19：只读复用核对确认现有S2客户端/目录RAG/作业/会话资产；明确身份不可混用、引用方向、持久缓存缺口。
- 2026-10-19：用户要求先落盘；主会话代行纯文档建档，状态待确认，Task02–08待执行，无代码/部署/数据迁移。
- 2026-10-19：用户明确授权实现，独立需求/技术评审通过，状态转已确认再实施中；Task02开始。纳入真实30/50返回数量、owner-scoped解绑失败保留项目和合同先行门禁，未宣称真实API已通过。
- 2026-10-19：Task02独立合并Go（8项精准测试、真实S2引用和200节点620边浏览器压力档），Task03合同冻结并开始分端实现；尚无生产地图API/部署成功证据。


## 2026-10-27 地图易用性修订（已确认，实施中）

### 一句话目标与选择状态

让图谱节点有明确间距、单点/多点/整组配色可发现且持久，打开详情不丢图，全文分析和入库状态明确可行动。用户已对Grilling Q1–Q10全部采用推荐；用户已明确“共同理解 继续工作”，本轮授权实施。旧Task09、旧评审与验收只证明历史候选。

### 数据模型与迁移

- MapPaper新增nullable `color_override`（六位#RRGGBB，规范化大写），旧记录默认为null；有效色优先级override→单个group.color→默认色。group_id仍为单值，不新增多组归属。
- `view_settings.node_style` 正式扩展 `{fill_mode: filled|outline, fill_opacity: 0..1}`，默认filled/0.3，拒绝非有限值/未知字段；地图级保存，旧图读取应用默认，不把样式塞入filters。
- 多选/预览只属前端临时状态；最近8色仅owner分隔的浏览器localStorage，不进入数据库/地图导出，不做跨设备同步。
- 当前地图schema基线v6，规划无损增量至v7增加节点覆盖色；实施门禁复核并行迁移，不能复用已占版本、重建/清空表或改变稳定ID。
- 图/节点API保留现有字段并增量返回可选色/样式，旧调用可继续；JSON导出明确升级`literature-map-export-v2`，保留旧字段并增加色/样式，不新增JSON导入器。

### 端点/接口增量

- 沿用现有分组POST/PATCH、节点group PUT与view PATCH的owner/expected_revision保护。
- 新增 `PATCH /api/literature-maps/{map_id}/node-styles`：`{expected_revision, node_ids:[1..200个唯一ID], color_override: HEX|null}`（三个字段均必填，null须显式传入），单点也复用；成功返回新revision及目标节点色值。全体身份/未移除状态通过后才事务写入，任何错误全不改；不换组，不碰未选节点。
- 现有 `PATCH /{map_id}/view` 增加严格可选node_style；位置保存继续用现有positions，整理预览不发写请求。
- 未授权/无地图沿现有404、revision冲突沿现有409；字段/范围非法按现有验证错误格式，事务不得部分成功。网络中断不等于事务失败，先显示结果待核对并GET核验，不谎称已回滚；最近色只在确认保存结果后更新。GET保持只读。PNG同步渲染样式，JSON白名单加入正式字段，不能导出owner凭据/临时预览/最近色。

### 产品边界

1. 自动布局净空>=2倍较大圆直径，半径仍按现有总被引数对数公式；新图自动、旧图显式整理预览/确认，拖动/筛选不自动重排。允许扩大图面，用缩放平移浏览，不压回重叠。
2. 打开/关闭详情不重排、不自动全图fit，保留缩放；仅必要小范围平移保持所选可见。图空白先按真实数据/宽度复现，不能把源码疑点伪写成根因。
3. 单点详情节点外观、多选工具栏、整组色块共用12预设/自定义HEX/最近8色。点色预览、应用保存、取消恢复；批量全成/全不改，成功才记最近色。
4. 填充模式/强度为每图统一设置，默认30%不透明度，描边100%；仅描边内部透明，选中不改实心色；保存重开和PNG/JSON保持一致。
5. 页签改为摘要分析/全文分析。全文所有状态在邻近明显卡片展示，入库/索引/全文门禁分开，所有面向用户状态中文，移除常驻学术立场文案。

### 明确不做

不新增图数据库/前端框架/下载器；不恢复Spec032其余暂停工作；不新增PDF阅读器、跨设备最近色、节点多组归属、框选、每节点独立透明度、布局历史库或学术立场推断；不改变论文大小公式，不自动下载/全文分析，不静默覆盖人工位置。

### 产品步骤与验证

[Task10](../plans/043/task-10-map-usability.md)提供旧图整理→点选详情→单/多点/分组色→填充与导出→全文状态→版本冲突的核心人工案例。开发后补每步真实提示/等待/失败恢复和产物。必须跑通当前部署真实API保存/冲突/重读/导出，以及真实地图浏览器间距/视口/PNG/全文ready成功案例；不是仅检查字符串或合成夹具。至少9/10准备度且无P0/P1才交用户。

### 执行配置与任务

架构师为自身（主会话），64k–200k，负责Spec、决策与门禁；独立architect负责需求/技术与验收签字，64k。doc-updater负责人工案例，32k。backend-dev/frontend-dev各32k分端代码与测试；独立backend-reviewer/frontend-reviewer各32k复审；backend-tester/frontend-tester各32k单端验证，tester32k汇总真实API/浏览器和最终候选。

2026-10-27实际读取上述角色配置model均为`Deepseek-V4.1-Flash`；本会话用户当次临时指派的Luna xhigh覆盖该默认，只作用于本次分派，不修改角色/长期规则。历史Spec的执行配置不作新分派型号真源。

任务新增[Task10 — 地图间距、配色与详情反馈](../plans/043/task-10-map-usability.md)，依赖历史Task03/05/06/07/09，状态实施中。实施步骤与分端边界只维护在Task文档。

### 本次评审与变更记录

- 需求评审：`docs/sdd/reviews/043-requirement-review.md` 的2026-10-27 Task10增量，已独立GO；历史结论不作为本轮替代。
- 技术评审：`docs/sdd/reviews/043-tech-review.md` 同轮增量，已独立GO；下列强制门槛须在实现与验收逐项验证。
- 验收评审：`docs/sdd/reviews/043-acceptance-review.md` 同轮增量，未执行，不复用历史完成结论。
- 2026-10-27：主会话作为架构师落盘两轮产品选择、数据/API增量与Task10；纯规划，无业务代码/部署/Git变更；独立需求/技术评审已GO，用户已确认共同理解，进入独立工作目录实施。

### Task10 独立评审强制门槛

1. v6→v7无损、幂等、失败回滚；旧记录/位置/分组不丢，API literature-map-v1不变，导出独立v2。迁移在初始化/启动门禁完成，GET不补迁移或业务写入。
2. node-styles字段/显式null/唯一200上限/owner/revision/removed与原子回滚均为服务端责任；网络未知先核验，不伪报回滚。
3. node_style不得藏入filters；node/graph读取、重开、PNG/JSON的有效样式一致，临时预览及最近色不进入地图导出。
4. 有限布局与兜底须以200混合半径实际浏览器验证，旧图预览不写，详情开关不自动fit；真实空白未复现前不宣称根因或修复成功。
5. 全文ready由服务端source_status门禁决定，indexed/document_id不足以证明；纯GET不下载/分析/补队列，不扩来源和下载范围。

上述门槛来自2026-10-27独立需求/技术评审，不是已实现或已验收声明。用户于2026-10-27确认共同理解，状态已确认并进入实施。

## 2026-10-27 论文关联扩展修订（待确认）

用户希望针对单篇论文，统一查看参考文献与引用本文两类候选，多选加入地图并后台分析。沿Spec043新增[Task11](../plans/043/task-11-paper-expansion.md)，复用Task04/09已有资产。数据和接口增量、范围及验证草案见Task11；[Grilling决策](../plans/043/2026-10-27-paper-expansion-grilling.md)尚未确认，不授权实现或部署新功能。Task10已确认范围及收尾状态独立保留。

### Task11 增量合同提案

Q1–Q15均采用推荐，待共同理解确认与独立门禁。统一单种子双向引用候选面板，每方向50条/页、累计500；跨两侧每批20新增、地图200。范围外候选标记后可选；来源顺序及已加载集合排序；真实引用，不推断和递归。确认原子写节点/边，后台仅对新增节点补元数据并摘要分析，未知/失败/无摘要区分。旧布局/配色和已完成分析保留，草稿当前浏览器按owner/map/seed隔离。

数据增量复用MapPreview分页游标/版本/页失败、既有MapJob/事件/MapAnalysis，增加批次关联；需要迁移则无损增量。接口提案：复用POST /previews并补分页选项、POST /previews/{preview_id}/load-more显式加载/补失败页、新增POST /previews/batch-apply跨预览原子确认；复用只读预览/图/作业及队列状态。服务端校验owner/map/seed/候选版本、revision和20/200容量，不以两次串行旧apply冒充原子操作。精确包形、重确认及迁移在技术门禁冻结。

实施顺序、核心真实API/浏览器案例、恢复与明确不做详见[Task11](../plans/043/task-11-paper-expansion.md)。本轮仅修改规划文档，未授权新代码，不触发来源请求、数据库迁移、部署或远程操作。

Task11接口与持久化细节见[接口合同](../plans/043/task-11-interface-contract.md)：v8仅增预览版本/分页状态，页作业与批次outbox复用MapJob；增加显式revalidate解决冲突后重确认，batch-apply单事务写图及定向队列；补全白名单仅缺失摘要与来源、保留历史source hash与分析。该合同已获独立技术复审GO，需求复审亦GO；仍待用户确认共同理解，未执行迁移或实现。

### Task11 用户确认

独立需求／技术最终GO后，用户在共同理解摘要后明确“继续工作”，本修订转已确认。按既定依赖先收尾Task10，随后开始Task11；此前待确认/BLOCK记录保留为历史，不作为当前状态。

### 2026-10-27 当前增量状态

Task10已完成并双签READY_FOR_USER，部署源码498b6ded（JS31/CSS19），见Task10最终验收及复盘。Task11用户已确认，依赖满足后转实施中，按冻结合同开发；历史待确认文字不代表当前状态。整个Spec因Task11保持实施中。

### 2026-10-29 Task11 最终收口

Task11已完成，Spec043由实施中转已完成。最终部署源码7364a26b（JS37/CSS25），当前8000首页/JSON图谱与真实摘要产物可访问。后端全量3183通过、3合法skip、67subtests、覆盖率82.32%；最终前端387通过、0失败/跳过，Node合同33通过。API三篇、桌面UI三篇、手机UI一篇均生成真实摘要，分别保留批次和analysis ID；手机引用分页50→100、选择、确认、排队到完成通过。历史失败与来源partial/缺摘要边界均保留，非物理手机实测。

最终[Task11验收双签](../reviews/043-task11-acceptance-review.md)、[人工步骤](../plans/043/2026-10-29-expansion-manual-acceptance.md)、[运行时证据](../plans/043/2026-10-29-expansion-browser-validation.md)、[复盘](../retro/2026-10-29-literature-map-expansion.md)。主会话仅同步状态/部署和本地提交，不代表用户已亲自验收，未push或合并main。

变更记录：2026-10-29｜主会话（编排/文档）、临时Luna xhigh（前端开发/独立复审/分端测试/QA/架构师）｜完成Task11、修复真实手机预览及触控回归，补齐真实产物、回归、签字、复盘及状态同步。

## 2026-11-05 地图列表论文数显示缺陷（待确认）

**状态：已完成（2026-11-06 验收通过、部署验证通过）。** 本段为 Spec043 收口后用户反馈的缺陷修订，按 Bug 处理规则不新建编号；主实现状态仍为「已完成」。用户已确认「卡片用只显当前篇数」并要求 `部分完成` 徽标一并修，自本条起转入实现；冻结范围见文末「用户确认与冻结范围」。

### 复现证据（2026-11-05，当前部署版本，全部为只读核实）

- 用户反馈（截图 `Screenshot 2026-11-05 at 22.59.28.png`）：地图卡片 `API E2E graph attention networks r2` 显示「部分完成 20 篇」，但用户刚通过 Task11「扩展关联论文」新增了 4 篇（可能更多），卡片数字未变。
- `GET /api/literature-maps`：该 map 为 `requested_count: 20`、`status: "partial"`、`revision: 286`、`updated_at: 2026-11-05T15:02:44+00:00`；返回字段全集 `map_id / name / topic / owner_id / project_id / filters / requested_count / revision / status / view_settings / created_at / updated_at`，**不含任何当前节点数**。当前 7 张地图的 `requested_count` 均为 20。
- `GET /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/graph`：`nodes: 32`、`edges: 29`、`removed: 0`。与 2026-10-29 验收快照 28 nodes / 25 edges 相比为 **+4 节点 / +4 边**，与用户描述一致。
- 结论：**新增已成功写入、数据未丢失**；显示不变不是「没刷新」，而是计数口径错误。

### 根因

1. `frontend/literature-maps.js:1768` 的 `renderMapList()` 把 `map.requested_count` 直接渲染为 `${map.requested_count} 篇`。`requested_count` 是建图时用户选择的**目标篇数**（`backend/app/literature_maps/domain/models.py:69`，创建时写入 `literature_maps.requested_count`），属静态配置，不随节点增删变化。
2. `GET /api/literature-maps`（`backend/app/api/routes_literature_maps.py:346-352`）只序列化 `item.to_dict()`；`store.list_maps()`（`backend/app/literature_maps/infrastructure/store.py:574-577`）只查 `literature_maps` 表。两处都不提供当前活动节点数。
3. 批量确认后 `loadMaps()` 已被调用（`frontend/literature-maps.js:4428`），但拉回的仍是静态 `requested_count`，因此反复刷新列表也不会变成 32。
4. 附带混淆：卡片「部分完成」是建图作业 `status: partial` 的旧状态，与 Task11 批次无关（`docs/sdd/plans/043/2026-10-29-expansion-manual-acceptance.md:59` 已说明）。本修订不顺带改它。

影响范围：所有地图列表卡片；凡经 Task11 扩展、节点移出/恢复或其他增删节点后，卡片篇数都不反映实际。

### 目标

地图列表卡片显示**当前活动论文篇数**，与打开图谱所见节点数一致；新增/移出/恢复节点后随既有 `loadMaps()` 刷新同步更新，且不与「建图目标数」混淆。

### 数据模型与接口（拟）

- 不新增表、不新增迁移、不回写历史数据；`literature_maps.requested_count` 的值与语义保持不变。
- `GET /api/literature-maps` 每个 map 新增只读派生字段 `node_count: int`，口径为 `SELECT COUNT(*) FROM literature_map_nodes WHERE map_id=? AND removed_at IS NULL`，与 `store.py:2587 / 2759 / 3212` 及 `service.export_map()` 的活动节点口径一致（排除移出墓碑）。要求一次批量查询得出，避免每张地图一次 N+1；响应其余字段保持向后兼容。
- `GET /api/literature-maps/{map_id}/graph` 响应结构不变，`map` 对象不加字段。
- 前端 `renderMapList()` 以 `node_count` 为主展示「N 篇」；`node_count` 缺失或非数时回落 `requested_count`（兼容旧后端与测试 fixture）。`requested_count` 仅在两者不同时作为辅助信息（如「目标 20」）或 `title` 提示，不覆盖主数字。
- `normalizeMap()` 需透传/规范化 `node_count`；静态资源 `literature-maps.js?v=40 → 41`，同步 `frontend/index.html` 与既有版本断言。

### 边界与明确不做

- 不改 Task11 预览、分页、batch-apply、revalidate、后台补摘要与分析逻辑。
- 不改建图作业状态徽标（`partial` 等）、不改 `status` 语义、不清理历史作业状态。
- 不改 `requested_count` 持久化值、不新增 DB 迁移、不批量刷新历史地图。
- 不新增前端轮询或 SSE；复用现有 `loadMaps()` 调用点（批量确认 4428、移出/恢复 6784、进入视图 6921）。
- 不改移动端布局、卡片其他信息、导出 PNG/JSON 内容。
- 不新建 spec 编号；本修订挂 Spec043（同 2026-10-27 修订先例）。

### 验证方式（确认后执行）

1. 后端定向：`GET /api/literature-maps` 每个 map 的 `node_count` 与对应 `.../graph` 活动节点数逐一相等；含 `removed_at` 墓碑时正确排除；多地图不串号、无 N+1；旧字段全部保留。
2. 前端定向（node vm）：卡片渲染 `node_count`、缺失时回落、两者不同时辅助信息正确、非数输入不产生注入。
3. 静态检查：`node --check`、ruff、既有前端版本断言同步。
4. 当前部署版本真实服务 E2E：硬刷新后卡片显示 `32 篇`；只读 GET 列表与 graph 逐 ID 对照；再按 Task11 人工新增 1 篇后回到列表确认数字 +1（写操作仅在确认后执行），落盘请求、响应、实体 ID、最终状态与产物路径。
5. 人工验收材料：逐步点击、点击后提示、等待条件、下一步、失败恢复（显示旧数字时先硬刷新并核对 `literature-maps.js` 版本号）与产物查看路径。
6. 分端执行：跨端改动拆成 `backend-dev` / `frontend-dev` 两次分派，`backend-reviewer` / `frontend-reviewer` 复审，`backend-tester` / `frontend-tester` 单端回归；`tester` 汇总跨端验收并出具 `NNN-acceptance-review.md`，架构师签字后再部署验证。

### 用户确认记录（2026-11-05）

- **卡片计数**：用户明确「卡片用只显当前篇数」→ 主显 `node_count`，**不显示目标数辅助信息**；`requested_count` 仅作为 `node_count` 缺失／非数时的回落值。
- **状态徽标**：用户明确「`部分完成` 徽标…修了」→ 纳入本轮范围，修法见文末「用户确认与冻结范围」第 2 条。
- 本段状态：`待确认 → 已确认`。

## 2026-11-05 人工验收阶段 UX 缺陷（二）：知识库跳转定位与地图视图保存（待确认）

**状态：已完成（2026-11-06 验收通过、部署验证通过）。** 三项缺陷由用户一次性确认后一并转入实现；冻结范围见文末「用户确认与冻结范围」。本节两项均落在 Spec043 已确认范围内：产品使用步骤第 3 条「切换两种关系、缩放拖动并保存，离开后重开，节点/位置/筛选保留且不自动联网」（本 spec:134），以及第 5/6 条「点击加入知识库才进入原有导入流程…成功后节点状态更新；关于本篇提问跳转并预填草稿」（本 spec:136-137）。

### 缺陷 A：地图节点「在知识库中查看」只切页面、不定位到该论文

**用户原文**：「End-to-End Spectro-Temporal Graph Attention Networks for Speaker Verification Anti-Spoofing and Speech Deepfake Detection 这篇文章我已经点击加入知识库了，然后点击在知识库里查看会进行跳转，但不会跳转定位到这篇文章，知识页面变成知识库。」

**只读复现与证据（2026-11-05，当前部署版本）**：

- `GET /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/graph`：该论文为 node `065389f0f0b64acda6c5a043cc9b6269`，`document_id = 1b967ed8638e46569d36e3f6565c51eb`，`download_status = indexed`。
- `GET /api/kb/papers`：对应条目 `document_id = 1b967ed8638e46569d36e3f6565c51eb`、`paper_id = null`、`status = indexed`、标题完全一致 → **入库成功，文档确实在知识库**。
- `frontend/literature-maps.js:6521-6529`：详情按钮把 `node.document_id` 传给 `openKnowledgeBaseDocument()`；`:6742-6749` 调用 `window.jumpToKnowledgeBase(documentId)`（`app.js` 为普通 script，函数挂在 window 上）。
- `frontend/app.js:6339-6340`：KB 列表项为 `if (documentId) item.dataset.documentId = documentId; if (paper.paper_id) item.dataset.paperId = paper.paper_id;`。本例 `paper_id` 为 null，该 `<li>` **只有 `data-document-id`，没有 `data-paper-id`**。
- `frontend/app.js:5106-5113`：`jumpToKnowledgeBase(paperId)` 仅用 `[data-paper-id]` 按 `=== String(paperId)` 查找；传入的是 `document_id`，必然匹配不到，于是不执行 `scrollIntoView` / `focus`，只执行 `showView('kb')`（导航项文案「▤ 知识库」，`frontend/index.html:100`）。与用户观察到的「知识页面变成知识库」一致。
- `paperState.pendingKbPaperId` 在 `app.js:5107` 赋值后全仓无任何读取（仅 `:4061` 声明、`:5107` 赋值；`docs/sdd/specs/020-misc-bug-fixes.md:63` 记载历史决策「`jumpToKnowledgeBase` / `pendingKbPaperId` 函数本身保留不动」）→ 定位属半实现。前端已有规范化 helper `kbDocumentId(paper)`（`app.js:6211-6217`，优先 `document_id`）但未用于跳转。
- 同一契约缺陷波及 `frontend/research-tasks.js:1691`「打开原文切片」，该处同样传 `document_id`。

**根因**：跨模块跳转的标识符契约不一致（地图／深度研究传 `document_id`，KB 跳转只认 `paper_id`），且 `paper_id` 可为 null；`pendingKbPaperId` 从未被消费。

**拟修法与边界**：

- `jumpToKnowledgeBase` 改为优先按 `data-document-id`、`data-paper-id` 兼容匹配（可复用 `kbDocumentId()` 统一键）；命中后滚动到视口中央、focus 并给可见高亮／状态提示；未命中时明确提示「未在当前列表找到该文档」并给可操作下一步，不静默只切页。
- 消费或删除 `pendingKbPaperId`：在 `loadKbPapers()` 渲染完成后重试定位，避免列表异步未就绪时错过。
- 明确不做：不改 `/api/kb/*` 后端契约、不改导入／索引流程、不改 `paper_id` 生成规则、不改地图节点数据结构、不改知识库列表分页与搜索行为。

### 缺陷 B：地图整理／移动后切走再回来丢失位置与视口

**用户原文**：「在点击地图，那个地图我已经整理过间距，但跳转回去又变初始的展示模式，我希望对地图的操作是会保存的，不要移了位置之后下次查看又是原来的位置」。

**只读复现与证据（2026-11-05，当前部署版本）**：

- 后端**确实保存了视图**：`GET .../graph` 的 `map.view_settings.viewport = {scale: 2.8, x: -664.03, y: -785.24}`，32 个活动节点各有唯一 `position`（`positions_unique: 32/32`）。问题在保存时机与重新进入时的覆盖，不是后端不持久化。
- `frontend/app.js:5319-5321`：`showView()` 每次切换都调 `window.LiteratureMaps.setActive(nextView === 'literature-maps')`；切到知识库即 `setActive(false)`。
- `frontend/literature-maps.js:6938`：`setActive(false)` 分支直接 `window.clearTimeout(state.saveTimer)`，取消 `scheduleViewSave()` 的 500ms 防抖（`:5154-5157`），**未 flush** 待保存的 `positionsDirty / viewDirty`。
- `frontend/literature-maps.js:5161` 与 `:5194`：`saveView()` 在 `!state.active` 时直接返回 false；即使 PATCH 已发出，响应回来时因 `state.active=false` 也不落地。
- `frontend/literature-maps.js:6919-6925`：切回时 `setActive(true)` → `loadMaps().then(... selectMap(state.selectedMapId))`；而 `selectMap` 在 `:2300-2329` 清空 `state.positions` 并置 `positionsDirty=false / viewDirty=false`，再由 `applySavedView` / `loadMapGraph` 从后端读回**未保存的旧值**，本地改动被覆盖 → 用户看到「又变原来的位置」。
- 另有放大该现象的既有逻辑：`:2388-2405` 的 `initialFitPending` 在 `savedScale <= 0.36` 或 `(x=0, y=0, scale=1)` 时为真，`:2446` 随即 `fitView(false)` 重算视口；而 `:1509-1512`「重置视图」按钮恰好写入 `(0,0,1)`，因此用户显式保存过的视图会被当成「未初始化」自动 fit，表现为「初始的展示模式」。

**根因**：离开视图时丢弃未 flush 的保存 + 重新进入时用旧服务端值覆盖本地状态；叠加 `initialFitPending` 把显式保存的默认视口误判为未初始化。

**拟修法与边界**：

- `setActive(false)` 前对 dirty 状态执行一次性 flush（立即 `saveView()`，允许这次保存跨视图切换完成并落地），不再 `clearTimeout` 丢弃；切回时若本地仍有 dirty，不在 `selectMap` 中清空。
- 区分「从未保存过视图」与「用户显式保存的默认视口」：`initialFitPending` 改由显式标记（如 `view_initialized`）或 revision 判定，不再以 `(0,0,1)` / 最小缩放猜测；用户手动重置视图后重开仍保持重置结果。
- 明确不做：不改 `PATCH /api/literature-maps/{id}/view` 契约与 409 冲突策略、不改节点拖拽与「整理间距」交互、不改后端 `view_settings` 结构、不引入 localStorage 草稿、不改其他视图切换逻辑。

### 验证方式（确认后执行）

1. 前端定向（node vm）：A —— 用 `document_id` 命中 `data-document-id`、`paper_id` 兼容、两者皆无时给提示、列表异步渲染后仍能定位；B —— `setActive(false)` 触发 flush、`saveView` 不被 `!active` 吞掉、切回不覆盖 dirty、显式保存的 `(0,0,1)` 不触发 fit。
2. 静态检查：`node --check`、前端版本断言（`app.js?v=68→69`、`literature-maps.js?v=40→41` 与 `frontend/index.html` 同步）；若触及后端再跑 ruff／后端定向 pytest。
3. 当前部署版本真实服务 E2E（写操作仅在确认后执行）：地图节点点「在知识库中查看」→ KB 视图该条目滚动／高亮且 `data-document-id` 与节点一致；拖动或整理间距 → 切到知识库 → 切回 → 比对 `GET .../graph` 的 `position` / `view_settings.viewport` 与保存前一致，记录 revision、请求、响应、实体 ID、最终状态与产物路径。
4. 人工验收材料：逐步点击、点击后提示、等待条件（列表加载完成、保存完成）、下一步、失败恢复（409 / 保存失败时的提示与重试）与产物查看路径。
5. 分端执行：若确认为纯前端改动，按单端分派 `frontend-dev` → `frontend-reviewer` / `frontend-tester`，**不跑后端 pytest**；如确认需后端配合则拆成两端两次分派。跨端验收由 `tester` 汇总、架构师签字后再部署验证。

### 用户确认记录（2026-11-05）

用户逐条答复：「卡片用只显当前篇数。」「`部分完成` 徽标要不要一并修（默认不纳入，避免扩大范围）？修了」「A. 跳转不定位…这个问题修了」「B. 位置『回到初始』…这个问题修了」。按「修了 = 一并修掉」理解，认定为对上述三段修订的**明确确认**，等同「按这个执行」；三段状态由 `待确认` 转 `已确认`。用户未逐条回答的三个默认项按本文先前默认值执行（KB 跳转仅滚动+高亮、不自动展开详情；接受离开即保存；`initialFitPending` 一并改造）。

## 2026-11-05 用户确认与冻结范围

本轮只做以下 4 项，任何超出项须先回到 spec 重新确认：

1. **卡片篇数**：`GET /api/literature-maps` 每项新增 `node_count`（口径 `removed_at IS NULL`）；卡片只显示 `${node_count} 篇`，**不显示「目标 20」等辅助信息**；`node_count` 缺失／非数时回落 `requested_count`（兼容旧后端与测试 fixture）。
2. **状态徽标（用户新增要求）**：卡片不再把历史建图作业的 `partial` 直接渲染为「部分完成」。当 `status === 'partial'` 且该地图已有活动节点时，徽标显示「可用」，并以 `title` / `aria-label` 保留「初始建图部分完成，已保留可用节点；不影响已保存节点与后续扩展」说明；`generating` / `failed` / `stopped` 保持原样。**不改后端 `status` 值、不改持久化、不清理历史作业状态**，仅前端渲染层映射。
3. **缺陷 A（跳转定位）**：`jumpToKnowledgeBase` 优先按 `data-document-id`、`data-paper-id` 兼容匹配；命中后滚动到视口中央、focus 并加可见高亮；未命中给明确提示。采用默认方案「仅滚动 + 高亮列表项」，**不自动展开／打开文档详情**；消费 `pendingKbPaperId`（`loadKbPapers` 渲染完成后重试定位）。`research-tasks.js` 同入口受益，不改其代码。
4. **缺陷 B（视图保存）**：接受「离开视图时立即保存」的时机变化；`setActive(false)` 前 flush dirty，`saveView` 允许这一次跨视图切换完成并落地；切回时不覆盖本地 dirty；`initialFitPending` 改显式标记，不再以 `(0,0,1)` / 最小缩放猜测。

**明确不做**：不改 `PATCH /view` 契约与 409 冲突策略、不改后端 `status` 语义、不改导入／索引流程与 `/api/kb/*`、不改 Task11 预览／批次／分析逻辑、不改节点拖拽与「整理间距」交互、不引入 localStorage 草稿、不改知识库列表分页／搜索、不改其他视图切换逻辑。

### 执行配置（本轮增量）

| 角色 | 选用模型 | 上下文上限 | 职责 |
|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent） | 200k | 冻结范围、编排、落地校验、验收签字 |
| 文档更新 `doc-updater` | 不适用（本轮为缺陷修订，无产品使用步骤变更） | — | — |
| 评审／合并 `architect` | Deepseek-V4.1-Flash（读 `.codebuddy/agents/architect.md`） | 32k | 增量需求／技术评审、验收签字 |
| 后端开发 `backend-dev` | Deepseek-V4.1-Flash（读 agent 文件） | 32k | 列表接口 `node_count` + 后端定向测试 |
| 前端开发 `frontend-dev` | Deepseek-V4.1-Flash（读 agent 文件） | 32k | 卡片／徽标／跳转／视图保存 + 前端定向测试 |
| 测试 `tester` | Deepseek-V4.1-Flash（读 agent 文件） | 32k | 跨端验收总控 |

> 分端评审 `backend-reviewer` / `frontend-reviewer`、单端回归 `backend-tester` / `frontend-tester` 同档位按单端原则分派；纯前端回归不跑后端 pytest。

### 任务拆分（每任务 ≤2 个文件）

| 任务 | 文件 | 分派 |
|---|---|---|
| BE-1 | `backend/app/api/routes_literature_maps.py`、`backend/app/literature_maps/infrastructure/store.py` | `backend-dev` |
| BE-2 | 后端定向测试（1 个 `tests/literature_maps/` 文件） | `backend-dev` |
| FE-1 | `frontend/literature-maps.js`、`frontend/index.html` | `frontend-dev` |
| FE-2 | `frontend/app.js` | `frontend-dev` |
| FE-3 | 前端定向测试（`tests/frontend/`） | `frontend-dev` |
| FE-4（评审 T-7 补登记） | `frontend/literature-maps.css`、`frontend/styles.css` | `frontend-dev` |
| BE-3（后端复审 P1-1 补登记） | `backend/app/literature_maps/application/service.py` | `backend-dev` |

补登记说明（2026-11-06）：① 增量技术评审 T-7 裁决 `styles.css` / `literature-maps.css` 的高亮与徽标样式是缺陷 A、缺陷 2 的**必要组成**，非范围扩张；② 后端复审裁决 `service.py:2584-2587` 的 `_export_view_settings` 透传 `view_initialized` 属**必要配套**——该白名单只在导出 JSON 一条通路生效，PATCH `/view` 与 GET `/graph` 走 `to_dict()` 原样输出；保留它是为避免导出与 API 口径分叉，须登记并补导出测试，后端已补 2 条导出用例（`240 passed`）。两项由主会话按评审意见纯文档补登记，无业务代码改动。

验收材料、评审结论、状态与台账由主会话汇总落盘。

## 2026-11-06 收口记录（三项 UX 缺陷修订）

状态：**已完成**。三段修订均于 2026-11-06 通过验收并完成当前部署版本运行时验证；主 spec 状态维持「已完成」，本轮未新建编号。

- 验收评审：`docs/sdd/reviews/043-ux-defects-acceptance-review.md`（PASS，准备度 10/10，P0=0 / P1=0）。
- 架构师签字／合并裁决：`docs/sdd/reviews/043-ux-defects-merge-decision.md`（同意收口；增量评审为并行补做、不追认实现前拦截）。
- 真实 E2E：`docs/sdd/reviews/043-ux-defects-live-e2e.md` —— 卡片「可用 32 篇」；跳转目标 `li` 高亮 + focus + 视口内；zoom-out 后 60ms 内切走仍落库（`revision 288`、`viewport.scale 2.3333`、`view_initialized=true`），切回视口保持；`/api/health 200`。
- 分端复审与回归：`docs/sdd/reviews/043-ux-defects-{backend,frontend}-{review,regression}.md`；后端 `240 passed`、前端 `396 passed / 0 failed`、node vm `24 PASS / 0 FAIL`，ruff 4 条告警与 HEAD 基线一致。
- 复盘：`docs/sdd/retro/2026-11-06-043-ux-defects-retro.md`（两轮 P1、两个 E2E 独有发现、流程偏差、7 条残余 P2）。
- 最终静态资源版本：`app.js?v=70`、`literature-maps.js?v=42`、`literature-maps.css?v=27`、`styles.css?v=68`。
- 边界复核：未改后端 `status` 值/语义、未改 `PATCH /view` 请求体与 409 策略、未改 `/api/kb/*`、未动 Task11 批次逻辑、未改 `research-tasks.js`、未引入 localStorage 草稿。

## 2026-11-06 节点外观面板紧凑布局（已作废存档）

**状态：已作废（2026-11-06 用户「按照A」裁决，问题 7② 默认值）。** 用户裁定「这个要跟下面的分组逻辑一起再次设计」后暂缓；随着「节点分组画布左下角入口改造」按 A 确认，节点详情调色板 `section.literature-map-node-color-section` 整体移除，本段「紧凑化」对象不再存在，故整体作废，不实施、不升版本号、不部署。原「暂缓」记录与下方实测证据保留仅供追溯，不作为实施依据。

> **用户裁定（2026-11-06）**：针对本段「方案 2（可选叠加）：默认折叠成一行 `<details>`，有颜色预览时自动展开，默认只占 ~30px（-88%）；按钮文案、颜色预设、应用/取消/跟随分组逻辑、其它面板一律不动」，用户批复「**这个要跟下面的分组逻辑一起再次设计**」。因此本段**不进入本批次实施**，保持冻结；待「节点分组画布左下角入口改造」方向确认后，与分组样式逻辑一并重新设计（届时节点级调色板可能被整体移除，本段亦随之作废）。本批次仅实施「顶部操作按钮可读性与尺寸」与 Spec012 索引缺陷修订。

> **联动提示（2026-11-06 用户最新方向澄清）**：用户后续明确「论文节点就不再单独设置可以调整它样式的功能了，它的样式跟着它的分组走」。若该方向确认，节点详情里的 `section.literature-map-node-color-section`（`renderNodeColorControls()`，`frontend/literature-maps.js:6655-6660`）将被**整体移除**，本段「紧凑化」的对象不再存在，本段应随之作废（无需再压缩一个已删除的面板）。是否作废请在下一段「待确认问题 7」中一并裁定；裁定前本段仍保持 `待确认`。

### 实测证据（真实 Chromium，当前部署版本）

用户截图 `Screenshot 2026-11-06 at 02.42.52.png`：右侧详情面板「节点外观」区块，含 12 个预设色点 + 最近使用色点（共 16 个、3 行）、「自定义 HEX」标签与输入框、大块留白、「应用到 1 篇 / 取消预览」与整行「恢复跟随分组」。

浏览器实测（目标地图 `0baabeae…`，选中一个节点，桌面视口；此态 `getRecentColors()` 为空，是**最小占用**）：

| 元素 | 尺寸 |
|---|---|
| `.literature-map-detail` | 248 × 497 |
| `.literature-map-node-color-section` | 220 × **241**（占详情面板约 48%） |
| `.literature-map-color-palette` | 220 × 207（`padding:8px`、grid `gap:7px`） |
| `.literature-map-color-swatches` | 202 × 49（12 预设、2 行；色点 22px、`gap:5px`） |
| `.literature-map-color-recents` | 202 × **0**（空，仍占一个 7px gap） |
| `.literature-map-color-hex-label` | 202 × **43**（标签 9px + 4px gap + 26px 输入框，上下两行） |
| `.literature-map-color-error` | 202 × **12**（空，仍因 `min-height:12px` 占位 + 7px gap） |
| `.literature-map-color-actions` | 202 × 25 |
| `.literature-map-node-color-follow-group` | 202 × 25（独立一行） |

用户截图态最近颜色非空（`RECENT_COLOR_LIMIT=8`，实测 12 预设 + 4 最近 = 3 行），实际占用比上表更大。

来源：`frontend/literature-maps.js:46-48`（12 预设 / 最近上限 8）、`:712-786` `createColorPalette('node')`、`:6655-6659` `renderNodeColorControls()`；`frontend/literature-maps.css:307-320`（色板 grid/gap/padding、hex label `display:grid`、error `min-height:12px`）、`:325-327`（移动端色点 25px）。

### 目标

在不减少功能、不缩小点击目标、不改变按钮文案与颜色契约的前提下，把节点外观区块高度降低约 40%（241px → ~145–160px，最近颜色非空时收益更大）；若选择折叠方案，默认高度再降至约 30px。

### 数据模型与接口

**不涉及**：不改后端、不改 API、不改 `papers.json` / `view_settings`、不改颜色预设与 `data-color` / class 契约、不改颜色草稿／应用／取消／跟随分组的业务逻辑。

### 拟改范围（推荐方案 1：仅紧凑化，不引入折叠）

CSS（**仅作用于 `.literature-map-node-color-section` 作用域**，不影响分组色板 `target=group` 与多选色板 `target=selection`）：

1. `.literature-map-color-hex-label` 由 `display:grid; gap:4px` 改为 `display:flex; align-items:center; gap:6px`，标签文本 `white-space:nowrap`，输入框 `flex:1; min-width:0; padding:4px 6px` → 43px → 约 26px。
2. `.literature-map-color-recents:empty`、`.literature-map-color-error:empty` 设 `display:none`，error 同时 `min-height:0` → 去掉 12px 占位与两个 7px gap；有错误／有最近颜色时仍正常显示。
3. palette `padding:8px→6px`、`gap:7px→5px`；`.literature-map-color-swatches/.recents` `gap:5px→4px`；**色点尺寸保持 22px（移动端仍 25px）**，不缩小点击目标。
4. `.literature-map-node-color-section` `padding-top:11px→8px`、`gap:6px→4px`。
5. 按钮行：把 `followGroup` 与 `actions` 合并到同一 flex 行（1 处最小 JS：`:785` 的 `palette.append(followGroup)` 改为 `actions.append(followGroup)`）；三个按钮仍可 `flex-wrap`，窄屏自动换行且不溢出 220px。

预计 241px → 约 145–160px（-34% ~ -40%）。

**备选方案 2（可选叠加）**：把「节点外观」改为 `<details>/<summary>` 折叠，默认收起、存在 `colorDraft` 时自动展开，与现有 `.literature-map-node-style-disclosure` 视觉一致；默认占用约 30px（-88%），代价是改颜色多一次点击。

### 边界与明确不做

- 不改颜色预设数量／色值、不删 HEX 输入、不删「取消预览」「恢复跟随分组」「应用到 N 篇」按钮、不改文案与禁用逻辑。
- 不改 `target=group` / `target=selection` 色板布局（作用域限定），不改移动端抽屉布局、不改详情面板其它区块。
- 不缩小色点点击区域（桌面 22px / 移动端 25px 保持不变）。
- 不改 `PATCH /view` 与 409 策略、不改 Task11 逻辑、不改后端。
- 确认前不升版本号、不部署。

### 验证方式（确认后执行）

1. 前端定向：DOM 契约（class / `data-color` / 按钮文案 / 作用域不影响其它色板）、HEX 非法值错误态仍显示、空 recents/error 隐藏、有最近颜色时正常显示、按钮行不溢出 220px。
2. 真实浏览器前后对比：`.literature-map-node-color-section` 高度、色板行数、按钮是否溢出、色点可点区域；覆盖桌面（≥1180px）、1180–760px、移动端（≤760px 抽屉）三种宽度。
3. 回归：`node --check`、`.venv/bin/python -m pytest tests/frontend -q`（396 passed 基线）、相关 node vm 用例；升 `literature-maps.css?v=27→28`，若改 JS 另升 `literature-maps.js?v=42→43` 并同步全部版本断言。
4. 人工验收：选中节点 → （方案 2 时展开）→ 点色点预览 → 输入非法 HEX 看错误提示 → 应用／取消／恢复跟随分组 → 切走再回来状态正确；附失败恢复与产物路径。
5. 分端执行：纯前端改动只分派 `frontend-dev` → `frontend-reviewer` / `frontend-tester`，**不跑后端 pytest**；主会话汇总并部署验证。

### 待确认事项

请确认：① 采用**方案 1（仅紧凑化，约 -40%）**还是叠加**方案 2（默认折叠，默认 -88%，多一次点击）**（默认：方案 1）；② 是否允许把「恢复跟随分组」并入同一按钮行（默认：是）；③ 保持色点尺寸不变、不缩小点击目标（默认：是）。用户明确确认后本段转 `已确认` 方可开始实现。

## 2026-11-06 文献地图顶部操作按钮可读性与尺寸（待确认）

**状态：已完成（2026-11-06 验收通过、真实浏览器验证通过、架构师签字同意收口）。** 用户新提的第二项 UI 优化需求。按本节默认方案实施：次级按钮统一提高对比 + 放大、移动端允许换行占两行且优先保证 ≥44px 触摸目标、不把「新建地图」提为主色实心按钮、不动全局 `.secondary-button`。

> **批次调整（2026-11-06）**：上段「节点外观面板紧凑布局」经用户裁定**暂缓**，需与分组逻辑一起再次设计，因此本项**不再与之合并实施**，单独成批次；但仍是纯前端 CSS 改动，与 Spec012 索引缺陷修订共用同一轮前端分派与版本号升级（`literature-maps.css?v=27→28`）。

### 实测证据（真实 Chromium，当前部署版本）

用户截图 `Screenshot 2026-11-06 at 02.43.49.png`：标题栏右侧 4 个按钮「刷新状态 / 新建地图 / 继续搜索 / 刷新预览」，文字浅灰、按钮矮小、与背景几乎融为一体。

浏览器实测（`#literature-maps-view` 顶部 `.literature-map-header-actions.literature-map-job-actions`）：

| 项 | 实测值 |
|---|---|
| 按钮容器 | 338 × 28 |
| 每个按钮 | **58 × 28**（4 个同尺寸） |
| `font-size` | **10px** |
| 文字色 | `rgb(139,142,150)` = `#8b8e96`（`var(--muted)`） |
| 背景 | `rgb(245,245,247)` = `#f5f5f7`（`var(--paper)`） |
| 文字/背景对比度 | **3.01 : 1**（低于 WCAG AA 正文 4.5:1） |
| padding | `7px 9px` |
| 边框色 | `rgb(139,142,150)` |
| 触摸目标 | 28px（远低于 44px，也低于项目其它视图的 34px 下限） |

来源：`frontend/literature-maps.js:975-994` 四个 `secondary-button` 与容器；`frontend/styles.css` 基础规则 `.secondary-button { border-radius:7px; padding:9px 12px; background:var(--paper); color:var(--muted); font-size:12px }`；`frontend/literature-maps.css:11`（容器 flex / gap 8）、`:170-171`（`.literature-map-job-actions button { padding:7px 9px; font-size:10px }` **把字号从 12px 压回 10px**）。

注：`继续搜索`、`刷新预览` 在 JS 中初始 `hidden=true`，但实测当前状态两者均 `hidden=false`，截图亦为 4 个按钮，故按 4 个按钮布局验收。

### 目标

在**不改按钮文案、不改 id、不改点击行为**的前提下：字号 10px → 12px、高度 28px → ≥36px（移动端 ≥44px）、文字对比度 3.01:1 → ≥4.5:1（目标 ≥8:1），并给出清晰的 hover / focus-visible 状态。

### 数据模型与接口

**不涉及**：不改后端、不改 API、不改 DOM 结构 / id / class 契约、不改按钮显隐逻辑与事件绑定。

### 拟改范围（CSS 作用域限定）

只在 `#literature-maps-view .literature-map-job-actions button`（及 `.literature-map-header-actions`）作用域内覆盖，**不改全局 `.secondary-button`**（该 class 被会话、项目、论文、技能等大量视图复用）：

1. `font-size:12px`、`font-weight:600`、`padding:9px 14px`、`min-height:36px`、`white-space:nowrap`。
2. `color:#4a4560`（白底 9.09:1、`#f7f5ff` 8.42:1）、`background:#fff`、`border:1px solid #d8d2ff`、`border-radius:8px`。
3. `:hover` 背景 `#f0edff` + 边框 `var(--accent)`；`:focus-visible` 加 `box-shadow:0 0 0 3px var(--accent-soft)`；`:disabled` 保持既有灰态。
4. `@media (max-width:760px)`：按钮 `min-height:44px`、允许换行，确保 4 个按钮不溢出抽屉宽度；容器 `gap:8px→6px`。
5. 可选（默认不做）：把「新建地图」提升为主色实心按钮做主次区分，需改 class / DOM，留待用户选择。

预期：按钮 58×28 → 约 82×36（桌面），对比度 3.01:1 → ≥8:1。

### 边界与明确不做

- 不改 4 个按钮文案、`id`、`hidden` 显隐逻辑、事件绑定与全局 `.secondary-button` 样式。
- 不改顶部标题／副标题、不改地图列表／图谱／详情面板、不侵入上段「节点外观」的优化范围。
- 不新增图标、不改按钮顺序、不引入新组件或依赖。
- 不改后端、不改 Task11 逻辑、不改 `PATCH /view` 与 409 策略。
- 确认前不升版本号、不部署。

### 验证方式（确认后执行）

1. 前端定向：4 个按钮 id / 文案 / 显隐状态不变；作用域外的 `.secondary-button` 样式不受影响（回归断言）；hover / focus-visible / disabled 三态。
2. 真实浏览器前后对比：每个按钮 w/h、`font-size`、`color`/`background` 对比度（≥4.5:1）、焦点环可见；覆盖桌面（≥1180px）、1180–760px、移动端（≤760px 抽屉）三档宽度，确认无横向溢出、无文字截断。
3. 回归：`node --check`、`.venv/bin/python -m pytest tests/frontend -q`（396 passed 基线）、相关 node vm 用例；`literature-maps.css?v=27→28`，同步全部版本断言。
4. 人工验收：硬刷新后核对 4 个按钮清晰可见、可点、键盘 Tab 有焦点环；点「刷新状态」「新建地图」功能正常；移动端抽屉内按钮不挤不溢出；附失败恢复与产物路径。
5. 分端执行：与 Spec012 前端失败态修订**合并为同一次 `frontend-dev` 分派**（同属 `frontend/**`，共用一次版本号升级与同一轮回归），随后 `frontend-reviewer` / `frontend-tester` 单端评审回归；该前端任务不含任何后端改动。

### 用户确认与冻结范围（2026-11-06）

用户批复「这个做」，按默认方案冻结：① 次级按钮统一提高对比 + 放大（不把「新建地图」提为主色实心按钮）；② 移动端允许换行占两行，优先保证 ≥44px 触摸目标；③ **不与「节点外观面板紧凑布局」同批实施**（该项经用户裁定暂缓、需与分组逻辑一起再设计）。冻结范围仅 `frontend/literature-maps.css` 作用域限定覆盖 + `frontend/index.html` 版本号，不改按钮文案 / id / 显隐逻辑 / 事件绑定，不动全局 `.secondary-button`。

## 2026-11-06 地图标签与卡片设置菜单（已由用户方向澄清取代，作废存档）

> **⚠️ 2026-11-06 用户方向澄清：本段整体撤销，不再作为待实施范围。**
> 用户原话：「我明白你有做地图节点分组的功能，**这个功能是要保留的**」。需求对象是**现有的地图内论文节点分组**（`literature_map_groups` / 节点 `group_id` / `/groups` API）的 UI 改造，**不是**新建「地图级标签」分类系统。
> 因此本段拟建的 `literature_map_tags` / `literature_map_tag_bindings`、6 个端点、`GET /api/literature-maps` 的 `tags` 派生字段、列表标签筛选、卡片右下角 ⋯ 菜单、「分组」改叫「标签」、以及末尾「补充：卡片显示所属标签」子节**一并撤销**，不再实施，其中 8 个待确认问题不再回答。
> 取代方案见「2026-11-06 节点分组画布左下角入口改造（**已确认**）」段。以下原文保留，仅作需求演进留痕。

> **✅ 方向冲突已裁决（2026-11-06 用户回复「按照A」）**：上一轮批量确认中，用户对本段原先 3 个问题回复「**都按照你的默认**」（地图级标签 / 两套并存且节点分组 UI 改叫「标签」/ 一张地图可多选标签），并对「卡片显示所属标签」回复「**按照你的默认设计**」；这与用户**亲自澄清**的方向（节点分组功能保留、入口移到画布左下角 icon、点样式高亮分组节点、节点样式跟随分组、移除节点单独调样式）直接冲突。主会话按 SDD 暂停并给出 A/B/C 三选项，用户裁决 **A**：
> - **以用户最新一次亲自澄清为准**：本段**继续作废**，不恢复地图级标签系统、不建 `literature_map_tags` / `literature_map_tag_bindings`、不加 6 个端点、不加列表标签筛选、不加卡片 ⋯ 菜单与标签徽标、不做「分组」改名。
> - 实施「节点分组画布左下角入口改造」段（8 个默认值已逐条冻结，见该段「用户确认与冻结范围」）。
> - 本轮「都按照你的默认 / 按照你的默认设计」仅视为对历史清单的**批量批复**，不再单独执行；不采用 B、不采用 C，范围不扩大。
> 本段终态 `已取代（作废存档）`，无业务代码、无数据、无版本号、无部署改动。

**状态：已取代（作废存档）。** 原为 `待确认`；2026-11-06 用户澄清方向后整体撤销，需求演进见下一段。以下为该段产出时的原始记录（当时累计 4 项待确认：Spec012 索引卡死 + Spec043 节点外观紧凑化 / 顶部按钮可读性 / 本项），保留仅供追溯，不作为实施依据。

> 编号说明：本项暂挂 Spec043 待确认修订；若用户确认方向后判定为独立子系统，再按建档流程新建 `045-…` spec 并同步 `docs/sdd/plans/045/`。`044` 已被 `architecture-boundary-guards` 在途分支占用（存在 `chore(spec-044)` 提交），不可复用。

### 需求原文要点

1. 「人工分组」面板放在地图列表**下方**太奇怪，要放到**上方**。
2. 目前列表只有「按状态筛选」，希望**加上按标签筛选**；新增的标签都要显示在这个列表中。
3. 给**地图**设置标签的入口移到地图卡片：卡片**右下角加三个点（⋯）图标**，点开设置菜单，其中一项是「设置标签」。
4. 「设置标签」分两个操作：① 加入已有标签；② 新建标签（复用现有「名称 + 颜色 + 创建」表单设计）。
5. 术语改名：**「分组」改叫「标签」**。

### 现状与关键事实（只读核实）

- 面板顺序（`frontend/literature-maps.js:1035-1085`）：`listFilters`（搜索框 + `listStatus` 状态下拉）→ `mapList` → `listEmpty` → **`groupsPanel`（人工分组）** → `createPanel`。确实在列表下方。
- 筛选逻辑（`:1641-1648` `filteredMaps()`）：只有 `state.listQuery` 与 `state.listStatus` 两个条件；状态下拉选项为 全部状态 / 生成中 / 可用 / 部分完成 / 失败 / 已停止。
- **现有「人工分组」是地图内论文节点的分组，不是地图分类**：`GET /api/literature-maps/{map_id}/groups`、`PUT /api/literature-maps/{map_id}/nodes/{node_id}/group`；表 `literature_map_groups(group_id, map_id, name, color)`（`backend/app/literature_maps/infrastructure/store.py:136-140`），节点表有 `group_id` 列（`:164`）。因此**不能直接拿它筛选地图列表**。
- 卡片 `renderMapList()`（`:1833-1858`）每项是一个 `<button class="literature-map-list-item" data-map-id>`，内含标题 / 主题 / meta；CSS `display:grid`（`literature-maps.css:28`）。**`button` 内不能再嵌 `button`**，加 ⋯ 菜单必须调整卡片 DOM 结构（DOM 契约变化，现有 `[data-map-id]` 断言与点击行为需回归）。
- 「分组」UI 文案在 `literature-maps.js` 共 23 处（面板标题、placeholder、aria-label、重命名 prompt、状态提示、节点详情选择器、导出图例等）。

### 关键理解（默认方案，待用户确认）

- **两套概念并存，不迁移**：现有节点分组的**后端表 / API / 节点 `group_id` 全部保持不变**，仅 UI 文案把「分组」改称「标签」；另新增**地图级标签**用于地图分类与列表筛选。这样不破坏已有地图的分组颜色与节点归属。
- 列表上方的面板改为「标签」区：展示全部标签 + 作为筛选器（与状态筛选并存、可组合）。
- 新建标签表单复用现有 `groupForm`（名称 + `type=color` + 创建按钮），放在卡片 ⋯ 菜单的「新建标签」分支里；列表上方不再放创建表单（避免两处入口）。

### 数据模型（拟，新增，不改既有表）

| 实体 | 字段 | 类型 | 约束 |
|---|---|---|---|
| `literature_map_tags` | `tag_id` | TEXT | PK |
| | `owner_id` | TEXT | 必填，按 owner 隔离 |
| | `name` | TEXT | 必填，去空白后非空，长度 ≤ `GROUP_NAME_MAX_LENGTH`，同一 owner 下唯一（大小写不敏感） |
| | `color` | TEXT | `#RRGGBB`，默认 `#8d80e6` |
| | `created_at` / `updated_at` | TEXT | RFC3339 |
| `literature_map_tag_bindings` | `map_id` | TEXT | FK `literature_maps(map_id)`，软删地图不计 |
| | `tag_id` | TEXT | FK `literature_map_tags(tag_id)` |
| | | | `UNIQUE(map_id, tag_id)`，重复绑定幂等 |
| `GET /api/literature-maps` 响应项 | `tags` | array | 只读派生 `[{tag_id, name, color}]`，旧字段全部保留 |

**并发隔离（必须）**：标签绑定走独立表，**不得递增 `literature_maps.revision`**，否则会与 `PATCH /api/literature-maps/{id}/view` 的 409 乐观锁互相踩踏。标签自身用 `expected_revision` 或独立版本号做冲突控制。

### 端点 / 接口（拟）

| 动作 | 输入 | 成功返回 | 失败（状态码） |
|---|---|---|---|
| `GET /api/literature-maps/tags` | owner 上下文 | `200 {tags:[…]}` | 401 |
| `POST /api/literature-maps/tags` | `{name, color}` | `201 {tag_id,name,color}` | 400 名称/颜色非法、409 重名 |
| `PATCH /api/literature-maps/tags/{tag_id}` | `{name?, color?}` | `200 {…}` | 404 / 409 / 400 |
| `DELETE /api/literature-maps/tags/{tag_id}` | — | `200 {deleted, unbound_maps}` | 404；解绑所有地图 |
| `PUT /api/literature-maps/{map_id}/tags` | `{tag_ids:[…]}` | `200 {tags:[…]}` | 404 / 409 / 422 含不存在或越权 tag_id |
| `GET /api/literature-maps` | owner | 每项含 `tags` | — |
| 现有 `/groups`、`/nodes/{node_id}/group` | 不变 | — | — |

### 边界（每条对应一条测试）

- 空标签列表、无标签地图、标签名为空/超长/仅空白、重名（同 owner 冲突、跨 owner 允许）、颜色非法。
- 绑定不存在/跨 owner 的 `tag_id` 一律 422，不产生越权可见性；重复绑定幂等；一次最多绑定数量上限（建议 20）。
- 删除标签后所有地图自动解绑、筛选结果立即更新；已软删地图不出现在筛选结果。
- 卡片 ⋯ 点击**不得**触发选图（`selectMap`）；菜单打开/关闭的键盘（Enter/Esc/焦点）、点击外部关闭；移动端抽屉内不溢出。
- 标签筛选与状态筛选、搜索框三者可组合；取消标签筛选恢复全部。
- 标签操作不改变 `literature_maps.revision`，不触发视图保存 409；节点分组功能（颜色/重命名/删除/归入）零回归。
- XSS：标签名只用 `textContent` / `setAttribute`，禁止 `innerHTML`。

### 明确不做

- 不改 `literature_map_groups` 表、`/groups` API、节点 `group_id` 与节点分组的任何行为；**不把节点分组数据迁移成标签**。
- 不做标签层级/嵌套、标签合并、拖拽排序、批量给多张地图打标签、标签导入导出。
- 不改地图创建/删除/图谱/详情/Task11 逻辑，不改后端 `status` 语义，不改 `PATCH /view` 与 409 策略。
- 不改现有「按状态筛选」下拉（保留），不改搜索框。
- 不新增前端框架或第三方依赖；不改其它视图。
- 不把「分组」改名扩展到后端字段名/URL（避免破坏性变更），仅 UI 文案与新增接口用「标签」。

### 产品使用步骤（初稿，确认后由 doc-updater 补齐可执行验收案例）

1. 打开「⌘ 文献地图」，列表**上方**看到「标签」区（与状态筛选并列），列出全部已有标签。
2. 在某张地图卡片**右下角点 ⋯** → 菜单展开 → 选「设置标签」。
3. 分支 ①「加入已有标签」：勾选/取消已有标签 → 保存 → 卡片显示标签徽标。
4. 分支 ②「新建标签」：复用「名称 + 颜色 + 创建」表单 → 创建后自动把该地图加入新标签。
5. 在列表上方点某标签 → 列表只显示带该标签的地图；可与状态筛选/搜索组合；再点一次取消筛选。
6. 验收场景：空态、重名、删除标签后解绑、跨地图不串标签、卡片 ⋯ 不误触选图、键盘可操作、移动端不溢出。

### 验证方式（确认后执行）

1. 后端定向：标签 CRUD 边界（重名/越权/空值/颜色）、绑定幂等与上限、删除解绑、owner 隔离、**不改变 `revision`**、`GET /api/literature-maps` 的 `tags` 派生且旧字段保留。
2. 前端定向：卡片 DOM 契约（`data-map-id` 保留、⋯ 不触发选图）、菜单开关与键盘、标签筛选三条件组合、23 处文案改名、无 XSS、无 `innerHTML`。
3. 真实服务 E2E：新建标签 → 给地图打标签 → `GET /api/literature-maps` 返回 `tags` → 浏览器点标签筛选 → 数量与预期一致；落盘请求、响应、实体 ID、最终状态、产物路径。
4. 三档宽度（≥1180 / 1180–760 / ≤760 抽屉）真实浏览器检查；回归 `node --check`、`.venv/bin/python -m pytest tests/frontend -q`（396 passed 基线）与后端 `tests/literature_maps`。
5. 分端执行：后端 `backend-dev` → `backend-reviewer` / `backend-tester`；前端 `frontend-dev` → `frontend-reviewer` / `frontend-tester`；**跨端拆两次分派**。验收由 `tester` 汇总、架构师签字后部署验证。
6. 人工验收材料：逐步点击、点击后提示、等待条件、失败恢复（重名/409/网络失败）、产物路径。

### 待确认问题（请一并回答）

1. **标签是给「地图」还是「论文节点」？** 默认按原文理解为**地图级标签**（用于筛选地图列表）；现有节点分组保留不迁移。若你其实想把节点分组整体改名/替换，请说明。
2. **一套还是两套？** 默认「地图标签」与「论文节点分组」并存，UI 统一叫「标签」；若希望合并成一套，需另定迁移方案（范围显著扩大）。
3. **菜单里「设置标签」是单选还是多选？** 默认多选（一张地图可有多个标签）；标签筛选默认单选、可取消。
4. **列表上方是否仍保留「新建标签」表单？** 默认不保留，只在卡片 ⋯ 菜单里新建（避免两处入口）；若你希望上方也能直接新建，请说明。
5. **术语改名范围**：默认只改 UI 文案（`分组`→`标签`），后端 `/groups` 路径与 `group_id` 字段名不动；若要求连 API/字段一起改名，需评估迁移成本。
6. 本项与前 3 项待确认是否一次性确认、按依赖顺序实施（默认：是；本项含后端改动，单独成批次）。

### 补充（2026-11-06，用户追加）：卡片显示所属标签

用户原话：「这个标签添加上的话要在地图卡片中显示它属于的分组」。按本段术语约定，此处「分组」即**地图标签**。本条是对本段需求的补充，**状态仍 `待确认`**，上文的 6 个待确认问题仍待回答。

**实测约束（真实 Chromium）**：`.literature-map-list-item` 当前 **192 × 72**，`display:grid; gap:4px; padding:9px 10px`；`meta` 行 **170 × 19**（`display:flex; gap:7px`），已含「可用」徽标 30×19 与「32 篇」25×13，仅余约 108px。右下角还要放 ⋯ 菜单，因此**不能把多个标签徽标直接塞进现有 meta 行**。CSS 见 `frontend/literature-maps.css:28-34`。

**默认设计**：

1. 卡片新增独立一行 `.literature-map-list-tags`（`flex-wrap:wrap; gap:4px`），位于 meta 行下方、⋯ 按钮左上侧；每个标签渲染为「色点 + 名称」小徽标（9px、`padding:2px 6px`、`border-radius:999px`），色点取 `tag.color`，文字用 `textContent` 固定深色（不拿标签色当文字色，保证对比度）。
2. 每张卡片最多显示 **3 个**标签，超出显示 `+N`（`title` / `aria-label` 列出全部标签名）；**无标签时不渲染该行**，不占垂直空间。
3. ⋯ 菜单按钮固定在卡片右下角，与标签行不重叠；标签徽标**默认不可点**（筛选统一走列表上方标签区），避免与选图点击冲突。
4. 卡片高度预计 72px → 约 92px（有标签时）；移动端抽屉内标签行可换行，不横向溢出。
5. 数据来源即 `GET /api/literature-maps` 每项新增的 `tags: [{tag_id,name,color}]`（见上文数据模型）；设置 / 删除标签成功后 `renderMapList()` 立即重绘，卡片徽标同步更新。

**对上文条目的细化**：

- **边界**新增：空标签不渲染、超长标签名截断并保留 `title` 全文、最多 3 个 + `+N`、删除标签后卡片立即移除该徽标、标签名 XSS（`textContent` / `setAttribute`，禁止 `innerHTML`）、⋯ 按钮不与徽标重叠、键盘焦点顺序、三档宽度不溢出。
- **验证方式**新增：前端定向断言「有 N 个标签渲染 N 个徽标 / >3 个显示 `+N` / 空数组不渲染 / 删除后消失」；真实浏览器核对卡片高度、徽标不与 ⋯ 重叠、文字对比度；人工验收补「给地图打标签后回到列表查看卡片徽标」。
- **产品使用步骤**第 3 步后补：「卡片上立即出现对应标签徽标；多个标签显示前 3 个 + `+N`；删除标签后徽标消失」。

**新增待确认问题**：

7. 卡片徽标最多显示几个（默认 3 个、超出 `+N`）？是否希望**点击卡片上的标签徽标直接筛选**（默认不可点，统一在上方标签区筛选；若要做需把卡片从 `<button>` 改成容器并 `stopPropagation`，范围略增）？
8. 徽标用「色点 + 名称」还是只显示色点 + tooltip（更省空间）？默认「色点 + 名称」。

用户明确确认后本段转 `已确认`，并按需要新建 `045` spec 与 `plans/045/` 建档，方可开始实现。

---

## 2026-11-06 节点分组画布左下角入口改造（已确认）

**状态：已完成（2026-11-06 用户「按照A」裁决 → 8 个默认值冻结 → Gate 2 双评审通过 → 实现与分端回归通过 → 真实 API/浏览器 E2E 与部署验证通过 → 验收评审通过、架构师签字同意收口）。** 用户最新一次方向澄清，取代上一段「地图标签与卡片设置菜单」（已作废存档）。本项**保留现有地图内论文节点分组功能**，只改造其入口、高亮交互与节点样式归属；**不新建地图级标签系统、不新增数据模型与公开接口**。范围冻结阶段仅文档，未改业务代码、未改数据、未升版本号、未部署、未重启服务。

> **留痕说明**：下方「关键理解」「待确认问题」「明确不做」各段保留原始提案措辞（含「默认」「是否也见问题 N」「请确认」字样），**一律以上文「用户确认与冻结范围」的 8 条裁定与「Gate 2 强制约束清单」C1–C9 为准**，不再另行确认；原始问题仅作需求演进留痕。

> 编号：继续挂 Spec043 待确认修订，不新建编号（属既有节点分组功能的 UI/行为收敛）。`044` 已被 `architecture-boundary-guards` 在途分支占用，不可复用；若用户后续要求把「分组样式」扩展成独立样式子系统，再评估建档 `045`。

### 需求原文与拆解

用户原话：「我明白你有做地图节点分组的功能，这个功能是要保留的。但我的想法是分组放在地图的左下角，用一个icon展示。点开icon可以展示有哪些分组和它们的颜色（样式），点击对应的样式会高亮该分组的所有节点（文章），除了这些颜色之外，还会展示设置新组的一个icon，里面可以设置它们的样式。同时已经有的节点也可以再次设置样式。论文节点就不再单独设置可以调整它样式的功能了，它的样式跟着它的分组走。」

| # | 要点 | 落点 |
|---|---|---|
| 1 | **节点分组功能保留** | `literature_map_groups` 表、节点 `group_id`、`/groups` API、`PUT /nodes/{id}/group` 全部不动 |
| 2 | 分组入口移到**地图（画布）左下角**，用一个 icon 展示 | 画布内新增常驻按钮；原列表下方管理面板移除 |
| 3 | 点开 icon 展示**有哪些分组及其颜色（样式）** | 浮层列 `state.groups`，色块 + 名称 |
| 4 | 点击对应样式 → **高亮该分组所有节点/文章** | 新增纯前端视图态高亮，不改后端 |
| 5 | 除颜色外还展示**「设置新组」icon**，里面可设置样式 | 复用 `groupForm`（名称 + 颜色 + 创建） |
| 6 | **已有的节点/分组也可以再次设置样式** | **已裁定 A+B**（见冻结表 #1）：节点可切换分组、已有分组可在浮层再次改色；节点不可单独调色 |
| 7 | **论文节点不再单独提供调整样式的功能，样式跟随分组** | 移除节点详情调色板与多选颜色面板，颜色只取分组色 |

### 现状与关键事实（只读核实，绝对路径 + 行号）

**分组读写**

- `frontend/literature-maps.js`：`renderGroups()` 1947–1982 → 容器 `#literature-map-groups`(1057–1059)、`#literature-map-group-list`(1080–1081)、空态 1082；行内含色块 `.literature-map-group-swatch.literature-map-group-color-trigger`(1955)、重命名(1968)、删除(1974)；创建表单 `#literature-map-group-form` / `-name` / `-color` / `-create`(1062–1079)。数据来自 `loadGroups()` 1994–2008，由 `selectMap()` 触发。
- `renderGroupLegend()` 1924–1945 → `refs.groupLegend` 挂在 `div.literature-map-legend`(1269)，是**画布外的面板底部图例条**（`frontend/literature-maps.css:87-90, 230-232`），不在画布内、不悬浮。
- 节点归入分组：`renderNodeGroupSelector(node)` 6631–6653 → `assignNodeGroup()` 6662–6700 → `PUT /nodes/{node_id}/group`。
- 分组改色：`applyGroupColor()` 2242–2270 → `PATCH /groups/{group_id}`；色板 `createColorPalette('group', id)` 712–802。
- 后端：`routes_literature_maps.py:401-462`、`service.py:818-864`、`store.py:788-900`（删除组 896 级联把节点 `group_id` 置 NULL）。

**画布左下角挂点**

- `div.literature-map-canvas`（JS 1246、CSS 74）**已 `position: relative`**，是天然定位上下文；其内目前只有 `#literature-map-svg` 与 `.literature-map-canvas-empty`（CSS 76–77 `position:absolute; inset:0; pointer-events:none`）。
- 缩放按钮在头部 `canvasHead > .literature-map-tools`（CSS 66–68），非 absolute；`/frontend/literature-maps.css` 全文**没有任何 `bottom:` / `left:` 的画布内定位规则**。
- 结论：可在画布内新增 `position:absolute; left/bottom` 的 icon 按钮（与 empty 同级，显式 `pointer-events:auto`），不与缩放控件、底部图例条重叠。

**节点级样式入口（用户要求移除）**

- `renderNodeColorControls()` 6655–6660 → `section.literature-map-node-color-section`（CSS 318–320）+ 「恢复跟随分组」775–786。
- 多选颜色面板 `selectionPalette` 1242–1244、`renderMultiSelectControls()` 1860–1876、`toggleMultiSelectMode()` 1878–1906。
- `createColorPalette()` 712–802 一函数三目标（`node` / `group` / `selection`）；全局「节点样式」disclosure `buildNodeStyleDisclosure()` 1333–1371（视图级 `fill_mode` / `fill_opacity`，非单节点）。
- 颜色优先级 `nodeDisplayColor()` 657–668：草稿 > 已保存 `node.color_override` > `currentGroupColor()`(647–655) > `DEFAULT_NODE_COLOR`；`renderGraph()` 4958–4966 写 `data-node-color` / `data-color-override` / `data-group-color`。
- 后端 `color_override` 链路：`routes_literature_maps.py:465-478`（`PATCH /node-styles`）、`service.py:866-892`、`store.py:733-783` + 迁移 353–357、`models.py:114/147`；导出 `sanitizeJsonExportBlob()` 5594–5631、`service._export_node()` 2749–2769、`_export_view_settings()` 2550–2583、`EXPORT_SCHEMA_VERSION='literature-map-export-v2'`（JS 51 / service 910）。

### 关键理解（已按 A 裁决冻结，2026-11-06）

1. **不新建数据模型、不新增端点**：复用 `GET/POST/PATCH/DELETE /api/literature-maps/{map_id}/groups` 与 `PUT /api/literature-maps/{map_id}/nodes/{node_id}/group`；分组仍是 `name + color`。
2. **左下角 icon + 浮层**：画布内常驻 `<button class="literature-map-groups-fab" aria-label="分组" aria-expanded="false">`；点击展开 `.literature-map-groups-popover`（左下锚定、向上展开），含：分组行（色块 + 名称 + 可选节点数）、`＋ 新建组` icon（展开 `#literature-map-group-form` 复用表单）、已有分组的改色/重命名/删除入口、「未分组」项与「清除高亮」。Esc / 点击外部 / 再点 icon 关闭，`aria-expanded` 同步。
3. **原列表下方 `#literature-map-groups` 管理面板移除**（用户最初抱怨「放在地图列表下方太奇怪」的根因）；画布外底部 `renderGroupLegend()` 图例条**默认保留**（只读、不承担管理）。是否也并入浮层见问题 6。
4. **点击分组样式 → 高亮该组所有节点**：新增纯前端视图态 `state.groupHighlightId`（`null` / `group_id` / `'__ungrouped__'`），`renderGraph()` 给命中组 `<g>` 写 `data-group-highlight="on"`、其余写 `off`，CSS 淡化非命中节点与边（如 `opacity:.18`）+ 命中节点描边强调。色块本身是 `<button>`，`aria-pressed` 反映当前态；再点同一组 / 点「清除高亮」/ 切换地图 → 清除。**不写库、不递增 `revision`、不进导出、不影响选中态与多选集合**。
5. **节点样式跟随分组**：移除节点详情调色板、多选颜色面板与「恢复跟随分组」；`nodeDisplayColor()` 简化为只取 `currentGroupColor(node.group_id)`。节点仍可通过详情里的 `#literature-map-node-group` 下拉**切换所属分组**，样式随新分组变化。
6. **后端兼容保留（默认）**：`color_override` 列、`PATCH /node-styles`、导出 `color_override` / `node_style` 字段**不删除**，只是前端不再写入且渲染忽略历史值；避免 schema 迁移与旧 `literature-map-export-v2` 导出 JSON 不兼容。是否连根删除见问题 3。
7. **全局「节点样式」disclosure 默认保留**：它是视图级 `fill_mode` / `fill_opacity`，不是「单个论文节点」的样式；是否一并移除见问题 4。

### 边界（每条对应一条测试；2026-11-06 评审补断言锚点）

- 左下角 icon 在画布缩放/拖动/空态、三档宽度（1440 / 1024 / 375）下不错位、不遮挡缩放控件、不被 SVG 覆盖；`pointer-events:auto`；移动端抽屉内不溢出。**可断言锚点**：FAB 与 `.literature-map-tools` 的 `getBoundingClientRect()` 无交叠；三档视口下 FAB 矩形完整包含在 `.literature-map-canvas` 矩形内；375 视口断言 `document.documentElement.scrollWidth <= innerWidth`。
- 浮层：无分组时显示空态 + 新建入口；分组多时滚动（`MAX_GROUPS=200`）；键盘 Enter/Esc/焦点顺序、点击外部关闭；`aria-expanded` / `aria-pressed` 正确；不与底部图例条重复管理入口。
- 高亮：只高亮目标分组节点（未分组不被误高亮）、再次点击/清除/换图恢复；**同图刷新不清高亮**；**不改变** `data-group-id`、不写库、不触发视图保存、不递增 `revision`、不改变导出 JSON 内容；与多选模式、节点选中态互不干扰。**不写库可断言锚点**：`window.__requestLog` 无新增 `POST/PATCH/PUT`。
- **并存规则（R-P0-4 闭合）**：分组高亮与既有扩展高亮 `.is-expansion-highlighted`（`literature-maps.css:236` 的橙色 `!important` 描边）同时命中同一节点时，**扩展高亮优先**，分组高亮只作用于其余节点；退出扩展面板后分组高亮态不变。CSS:236 规则保持不变。
- 新建/编辑分组样式：名称/颜色校验沿用 `validateGroupForm()`(804–814)；**重名提示走后端错误 + `errorAction()`，不得在前端自建重名规则**；非法色提示沿用前端校验；成功后该组所有节点按新色立即重绘、**浮层色块同步刷新**、高亮态保持；删除组沿用既有级联解绑（节点回落未分组/默认色）。
- 节点详情**不再出现** `.literature-map-node-color-section` 与「恢复跟随分组」；多选工具栏不再出现颜色调色板；`renderNodeGroupSelector()` 仍可切换分组且颜色随之变化。**反向护栏（R-P0-3 闭合）**：节点详情的分组选择器 `#literature-map-node-group` 是**唯一**可改变单节点颜色的入口；全站不存在任何直接写 `node.color_override` 的 UI 路径 —— 验收用 `grep -c "updateGraphColorOverrides\|applyNodeColor" frontend/literature-maps.js` 为 0 或证明不可达。
- 颜色优先级：库中残留历史 `color_override` 时渲染仍只用分组色；**本仓无 JSON 导入入口，边界改为「导出 JSON 仍含 `color_override` 字段（v2 schema 不变），下游消费者不因字段存在而报错」**（`sanitizeJsonExportBlob()` 5613–5616 白名单本就含该字段，前端不参与计算）。
- **图例条只读（R-P1-5 闭合）**：`renderGroupLegend()` 保持只读，不承接点击高亮；**左下角浮层是唯一高亮入口**。
- 零回归：节点分组的颜色/重命名/删除/归入、视图保存与 409 策略、`PATCH /view` 请求体、导出 JSON/PNG 分组图例。
- XSS：分组名只用 `textContent` / `setAttribute`（含 `title` 与 `aria-label` 插值），**禁止**字符串拼接进 `innerHTML` / `insertAdjacentHTML`；沿用 `test_frontend_map_groups_exports.py:38` 的反断言 `assert 'innerHTML' not in MODULE`。

### 明确不做

- 不新建地图级标签系统、不加地图列表标签筛选、不加卡片右下角 ⋯ 菜单、不把「分组」改名「标签」、卡片不显示分组徽标（上一段整体撤销）。
- 不新增前端框架或第三方依赖；不改其它视图；不改 `literature_map_groups` 表结构与 `/groups` 契约（除非问题 2 确认扩样式字段）。
- 默认不删后端 `color_override` / `PATCH /node-styles` / 导出字段，不升 `EXPORT_SCHEMA_VERSION`。
- 不改 `PATCH /view` 与 409 策略、不改节点位置/视图保存逻辑（`saveView()` / `view_initialized`）；高亮不持久化、不进导出。
- 本轮不动 Spec012 索引缺陷与「顶部操作按钮可读性与尺寸」（除非问题 8 确认同批处理）。

### 产品使用步骤（2026-11-06 按 A 裁决确认；验收映射由主会话回填，不另派 doc-updater）

1. 打开「⌘ 文献地图」并选中一张地图，图谱**左下角**看到分组 icon；列表下方不再有「人工分组」面板。
2. 点分组 icon → 浮层展开，列出全部分组及其色块/名称，另有「＋ 新建组」与「未分组」。
3. 点某分组色块 → 画布中该分组所有节点高亮、其余节点淡化；顶部/浮层显示「清除高亮」，再点一次或点清除恢复。
4. 点「＋ 新建组」→ 复用「名称 + 颜色 + 创建」表单设置样式 → 创建后浮层出现新组。
5. 选中任一已有分组可再次改色/改名；在节点详情用「将此论文归入」切换分组 → 节点颜色随新分组立即变化。
6. 选中一个节点：详情里**没有**「节点外观」调色板与「恢复跟随分组」；开启多选也不再出现颜色调色板。
7. 验收场景：空态、重名、非法色、删除组后节点回落、跨地图不串分组、高亮不写库、键盘可操作、移动端不溢出。

**步骤 → 验收点映射（R-P1-2 闭合）**：步骤 1 → 验证 1 的 FAB DOM 契约 + `#literature-map-groups` 不存在断言；步骤 2 → 验证 1 的浮层开关 / `aria-expanded` / 三档宽度；步骤 3 → 验证 1 + 验证 3 的 `data-group-highlight` on/off；步骤 4 → 验证 1 的 `validateGroupForm()` 复用 + 验证 3 的 `POST /groups` body；步骤 5 → 验证 1 + 验证 3 的 `PATCH /groups`、`PUT /nodes/{id}/group`；步骤 6 → 验证 1 的移除断言（选择器级）；步骤 7 → 验证 1 + 验证 2 + 验证 4。

### 验证方式（确认后执行）

1. 前端定向：左下角 DOM 契约（画布内 `position:absolute`、`pointer-events`）、浮层开关/键盘/`aria-*`、高亮节点集合与清除、切换地图清除、颜色只取分组色（含历史 `color_override` 忽略）、节点调色板移除断言、无 `innerHTML`；`node --check`、`.venv/bin/python -m pytest tests/frontend -q`、版本断言同步。**验收数字（R-P0-2 闭合）**：不得沿用历史「396 passed」；由 `frontend-dev` 实跑记录「改前实测值」，改动后 `tests/frontend` 全量应为 **N passed**，N 由首次全量实跑后回填本段；已知基线用例仍需单独标注 deselect 理由，不放宽阈值、不固化 skip。
2. 后端定向：默认零改动，仅跑 `tests/literature_maps` 回归确认 `/groups`、`PUT /nodes/{id}/group`、`GET /export` 零回归（复现命令 `cd backend && source ../.venv/bin/activate && python -m pytest tests/literature_maps -q`），**报告须标注为「回归核对（零后端改动前提下）」**，本轮不新增后端用例。
3. 真实服务 E2E（Playwright + 当前部署版本）：打开有分组的地图 → 点左下角 icon → 浮层列出分组与颜色 → 点某组色块 → 断言该组节点 `data-group-highlight="on"`、其余 `off` → 新建组并设颜色 → 通过节点详情下拉把节点归入新组 → 断言节点色随分组变化 → 清除高亮 → 断言恢复；落盘请求、响应、实体 ID、最终状态与产物路径。
4. 三档宽度真实浏览器检查左下角不遮挡/不溢出；导出 JSON/PNG 核对分组色块与节点色一致且不含高亮态。
5. 分端执行：改动若纯前端，只派 `frontend-dev` → `frontend-reviewer` / `frontend-tester`（**不跑后端 pytest**）；若确认要动后端，拆成后端一次、前端一次。验收由 `tester` 汇总、架构师签字后部署验证。
6. 人工验收材料：逐步点击、点击后提示、等待条件、失败恢复（重名/409/网络失败）、产物路径；服务启动与 `/api/health` 验证后告知可访问地址与实际端口。

### 待确认问题（请一并回答）

1. **最关键歧义**：「同时已经有的节点也可以再次设置样式」与「论文节点就不再单独设置…样式跟着分组走」如何统一？默认解读为 **A+B**：A＝节点可**切换所属分组**（样式随新组变），B＝**已有分组可在浮层里再次编辑颜色/样式**（该组所有节点联动）；节点**不允许**单独调色。若你其实仍想在节点上直接改色，请明确（与末句冲突，需以哪句为准）。
2. **「样式」的范围**：默认仅颜色（复用 `literature_map_groups.color`）。若要给分组增加填充/描边/透明度等，需扩表结构 + `GroupPatchRequest` + 导出 `groups[].style` + 评估 `EXPORT_SCHEMA_VERSION`，属范围扩大，请单独确认。
3. **后端 `color_override` / `PATCH /node-styles` 链路**：默认只移除前端入口、后端保留兼容（历史数据与旧导出 JSON 仍可用），不做 schema 删除；是否要连后端列/API/导出字段一起删（风险最高，需升导出 schema 或做导入兼容）？
4. **全局「节点样式」disclosure**（`fill_mode` / `fill_opacity`，视图级）是否也随「节点不再单独设置样式」一起移除？默认**保留**（它不是单节点设置）；若移除会连带 `node_style` 持久化、导出与 409 链路。
5. **高亮语义**：默认「淡化其它节点 + 命中组描边强调」的临时视图态，不持久化/不进导出；再点同一组取消（默认）、关闭浮层**不**清除（便于观察，默认）、切换地图清除。是否接受？
6. **原管理面板与图例条**：默认「列表下方 `#literature-map-groups` 移除、画布外底部 `renderGroupLegend()` 图例条保留」；是否希望图例条也并入左下角浮层（两处信息合一）？
7. **既有待确认项如何裁定**：①「地图标签与卡片设置菜单」及其「卡片显示所属标签」补充 —— 默认**作废撤销**，请确认；②「节点外观面板紧凑布局」—— 默认随节点级调色板移除而**作废**（无需再压缩已删除的面板），请确认；③「顶部操作按钮可读性与尺寸」—— 默认**保留**待实施。
8. **批次安排**：默认本项独立成批次，与 Spec012 索引卡死缺陷、「顶部按钮可读性」分别确认、按依赖顺序实施；是否希望一次性确认、一次性实施（共用一次版本号升级）？

### 用户确认与冻结范围（2026-11-06，A 裁决）

用户回复「**按照A**」，裁决为：① **以用户最新一次亲自澄清为准**；② 实施本节「节点分组画布左下角入口改造」；③ 「地图标签与卡片设置菜单」及其「卡片显示所属标签」补充**继续作废**，不恢复、不实施；④ 本轮「按默认」视为对历史清单的批量批复。据此，上列 8 个问题**全部按默认值冻结**，逐条裁定如下（任何偏离须先回到 spec 重新确认）：

| # | 裁定（默认值） |
|---|---|
| 1 | 采用 **A+B**：节点可在详情里**切换所属分组**（样式随新组变）；**已有分组可在左下角浮层再次编辑颜色/名称**（该组所有节点联动）；节点**不允许**单独调色。 |
| 2 | 「样式」**仅指颜色**，复用 `literature_map_groups.color`；不扩表、不改 `GroupPatchRequest`、不改导出 schema。 |
| 3 | 后端 `color_override` / `PATCH /node-styles` / 导出 `color_override`·`node_style` 字段**保留兼容**，仅前端不再写入且渲染忽略历史值；不做 schema 删除。 |
| 4 | 全局「节点样式」disclosure（`fill_mode` / `fill_opacity`，视图级）**保留**。 |
| 5 | 高亮为「淡化其它节点 + 命中组描边强调」的**临时视图态**；不持久化、不进导出；再点同一组取消、关闭浮层不清除、切换地图清除。 |
| 6 | 列表下方 `#literature-map-groups` 管理面板**移除**；画布外底部 `renderGroupLegend()` 图例条**保留**（只读、不承担管理），不并入浮层。 |
| 7 | ①「地图标签与卡片设置菜单」及「卡片显示所属标签」**作废撤销**；②「节点外观面板紧凑布局」随节点级调色板移除而**作废**；③「顶部操作按钮可读性与尺寸」**保留**（已于 2026-11-06 完成，本批次不动）。 |
| 8 | 本项**独立成批次**实施；Spec012 索引缺陷与顶部按钮批次均已收口，不再与本项合并、不共用版本号升级。 |

**冻结的文件边界**：`frontend/literature-maps.js`、`frontend/literature-maps.css`、`frontend/index.html`（版本号）、`tests/frontend/` 定向测试；**零后端改动**（`backend/**` 不在本批次）。增量评审通过前不改业务代码。

### 执行配置（本轮增量）

| 角色 | 选用模型 | 上下文上限 | 职责 |
|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | A 裁决冻结范围、编排、落地校验、验收签字 |
| 文档更新 `doc-updater` | 不适用（产品使用步骤初稿已在本段给出，无需另补） | — | — |
| 评审／合并 `architect` | Deepseek-V4.1-Flash（读 `.codebuddy/agents/architect.md`） | 32k | 增量需求／技术评审、验收签字、合并裁决 |
| 后端开发 `backend-dev` | 不适用（零后端改动） | — | — |
| 前端开发 `frontend-dev` | Deepseek-V4.1-Flash（读 agent 文件） | 32k | 左下角入口／浮层／高亮／节点样式收敛 + 前端定向测试 |
| 测试 `tester` | Deepseek-V4.1-Flash（读 agent 文件） | 32k | 跨端验收总控 |

> 分端评审 `frontend-reviewer`、单端回归 `frontend-tester` 按单端原则分派；**纯前端改动不跑后端 pytest**。验收阶段按「零回归」边界另跑一次 `tests/literature_maps` 核对 `/groups` 契约未受影响（属回归核对，非后端改动）。

### 任务拆分（每任务 ≤2 个文件；2026-11-06 Gate 2 评审后重排，共 9 个真实文件）

| 任务 | 文件 | 分派 |
|---|---|---|
| FE-1 | `frontend/literature-maps.js`、`frontend/literature-maps.css` | `frontend-dev` |
| FE-2 | `frontend/index.html`、`tests/frontend/fixtures/literature_map_component.html` | `frontend-dev` |
| FE-3 | `tests/frontend/test_frontend_map_groups_exports.py`、`tests/frontend/test_frontend_map_palette.py` | `frontend-dev` |
| FE-4 | `tests/frontend/test_frontend_literature_map_expansion.py`、`tests/frontend/test_frontend_map_mobile_contract.py` | `frontend-dev` |
| FE-5 | `tests/frontend/test_frontend_literature_map_contract.py`、`tests/frontend/test_frontend_map_analysis_contract.py` | `frontend-dev` |
| FE-6 | `tests/frontend/test_frontend_map_header_actions_readability.py`、新增 1 个定向测试文件（文件名不含 spec/task 编号） | `frontend-dev` |

> FE-1 与 FE-2 的 `literature-maps.js` 无重叠，可并行；FE-3 ~ FE-6 均依赖 FE-1 的最终 DOM 契约，按序执行。夹具 `tests/frontend/fixtures/literature_map_component.html`（1123 行）是浏览器用例唯一宿主，`:8` css / `:1120` js 版本号必须与 `index.html:9,805` 同步。

**FE-1 落地后实测补充（2026-11-06，评审改动面二次低估）**：`pytest tests/frontend -q`（deselect 已知基线）实测 `20 failed / 388 passed / 1 deselected`，暴露 Gate 2 评审未列出的 3 个文件：
- `tests/frontend/test_frontend_map_palette.py`（442 行 / 16 用例，其中 16 个失败）—— 依赖 `data-target="node"|"selection"` 色板、`PATCH /node-styles`、`__nodeStyleBodies`；
- `tests/frontend/test_frontend_selection_color_palette_ux.py`（103 行 / 2 用例，2 个失败）—— 多选颜色面板行为；
- `tests/frontend/test_frontend_selection_palette_dismiss_on_apply.js`（419 行 node:vm，用 `extract('renderMultiSelectControls')` 等从源码抽真实函数，函数体已收敛）。

任务拆分据此**追加 FE-7**（`test_frontend_map_palette.py` + `test_frontend_selection_color_palette_ux.py`）、**FE-8**（`test_frontend_selection_palette_dismiss_on_apply.js` + 新增 1 个反向契约定向测试文件），并把 FE-6 的「新增 1 个定向测试文件」调整为 FE-8。

**测试处置硬原则（不得绕过失败）**：① **禁止删除测试文件、禁止用 skip/xfail 掩盖**；② 断言「节点单独调色 / 多选调色板」行为的用例，改写为**反向契约断言**（节点调色板不存在、多选色板不存在、无 `PATCH /node-styles` 请求、`grep -c "applyNodeColor\|updateGraphColorOverrides" frontend/literature-maps.js === 0`、节点色只取分组色）；③ 断言**仍保留能力**的用例（分组改色 / recent colors / lost-response 复核 / 409 冲突 / JSON 导出保留 `color_override` / 视图级 `fill_mode`）**迁移到新入口**——先点 `#literature-map-groups-fab` 展开 `#literature-map-groups-popover` 再操作，不得删用例；④ 改前 `20 failed / 388 passed` 作为基线，改后 `tests/frontend` 全量（deselect 已知基线）必须 `0 failed` 且通过数不低于 388 + 新增定向用例数；⑤ 用例总数不得净减少（反向断言仍算用例）。

### 实现期缺陷与架构裁决（2026-11-06，已确认范围内追加，不退回待确认）

FE-1 + FE-2~FE-8 首轮落地后实测 `12 failed / 407 passed / 1 deselected`，剩余 12 个失败全部收敛到 FE-1 业务代码的 3 个真实缺陷：

| 编号 | 缺陷 | 证据 |
|---|---|---|
| D-1 | **色块只绑 `toggleGroupHighlight()`，分组色板永不显示** → 裁定 1 的「已有分组可再次设置样式」能力整体失效 | `renderGroups()` 中 `swatch.addEventListener('click', () => toggleGroupHighlight(...))`；`palette.hidden = !colorDraftMatches('group', group_id)` 恒 true |
| D-2 | `Object.assign(refs, {...})` 漏 `groupNameInput` / `groupColorInput` / `groupCreateButton` → `createGroup()` 会抛 TypeError | `createGroup()` 读 `refs.groupNameInput.value`；refs 注册行无这三个键 |
| D-3 | `.literature-map-groups-popover` 缺 `touch-action: pan-y` → 375 视口 CDP 触摸拖动 `scrollTop` 恒 0 | 同文件 `#literature-map-list`(301) / `.literature-map-create-panel`(305) / `#literature-map-detail`(306) 均已显式声明；浮层漏写 |

**架构裁决（解决「色块 = 高亮 vs 色块 = 改色」分叉）**：**不接受**把色块点击改为「打开色板」——那会推翻冻结裁定 5「点击分组样式 → 高亮该组所有节点」，且使 FE-8 的高亮断言失效。采用**双入口**：
- `.literature-map-group-color-trigger`（色块）**保持高亮语义**不变，继续 `toggleGroupHighlight()` + `aria-pressed`；「未分组」行同样保持高亮。
- 每个已命名分组行**新增显式「改色」按钮** `button.literature-map-group-color-open[data-group-id]`，点击 `setColorDraft(currentGroupColor(group_id), group_id)` 打开该行 `createColorPalette(group_id)`；再次点击 / 点「取消预览」收起。`renderGroups()` 仍是唯一渲染入口，`palette.hidden` 由 `colorDraftMatches()` 驱动。
- 迁移用例 `_open_group_palette()` 改点 `.literature-map-group-color-open`；FE-8 的色块高亮断言保持不动。

**版本号裁决**：`?v=43`（js）/ `?v=29`（css）是本批次首次升级且**尚未部署**，用户浏览器无该版本缓存，故批内续修不再次升版本；部署后仍以 `43/29` 为首次生效版本。若最终部署前又发生内容改动，仍需复核此结论。
>
> **版本号契约（T-P1-6 闭合，写死）**：`literature-maps.js?v=42→43`、`literature-maps.css?v=28→29`；同步 `frontend/index.html:9,805`、夹具 `:8,:1120`，以及 6 个测试文件的硬编码断言 —— `test_frontend_literature_map_contract.py:28-29`、`test_frontend_literature_map_expansion.py:28-29`、`test_frontend_map_analysis_contract.py:34-35`、`test_frontend_map_groups_exports.py:18-19,43-44`、`test_frontend_map_header_actions_readability.py:26,276,303`、`test_frontend_map_mobile_contract.py:94-98`。历史兼容 marker 注释不动。

### Gate 2 强制约束清单（2026-11-06 评审意见沉淀，逐条可验证）

> 来源：`docs/sdd/reviews/043-group-fab-requirement-review.md`（需求 13 条）、`docs/sdd/reviews/043-group-fab-tech-review.md`（技术 20 条）。以下合并去重为 9 组，**P0 全部在此闭合**，实现与验收逐条对照。

**C1 高亮实现硬护栏（T-P0-2 / T-P1-1 / R-P0-4）**
- `state.groupHighlightId` 只允许三个读写点：浮层交互、`resetMapSelectionState()`（2374–2460）、`renderGraph()`（4946–4979）；**禁止**写入 `state.colorDraft`（否则 `hasUnappliedVisualDraft()` 5633 会拦住导出）、禁止触发 `saveView()` / `request()`。
- 高亮标记写在 `<g>`（`data-group-id` 附近 4954）或独立 class；**不得**改 `circle` 的内联 `stroke` / `fill`（4962 已被 `nodeStyle` 占用）。
- 换图清高亮（`previousMapId !== mapId` 分支 2381–2386）、同图刷新不清；与裁定 5「切换地图清除」一致。
- 与扩展高亮并存时扩展高亮优先（CSS:236 的 `!important` 保持不变）。

**C2 颜色链路收敛（T-P0-3 / T-P0-4 / T-P0-5）**
- `nodeDisplayColor()` 改为 `currentGroupColor(node?.group_id)`，**必须保留** `currentGroupColor()` 的 `colorDraft.target==='group'` 分支（647–653），否则分组色板实时预览失效。
- `createColorPalette()` 收敛为 **group-only 单目标**：清理签名、`palette.dataset.target`、763 文案、766–769 `applyNodeColor` 分支、775–786 `followGroup` 分支；`applyNodeColor()` / `updateGraphColorOverrides()` 变无调用者后**必须删除**，不留死代码。
- `refs.selectionPalette`（1242–1244、1319）与 `renderMultiSelectControls()`（1868–1875）同批清理，`querySelector` 不得指向已删节点。
- 浮层改色 / 重命名 / 删除成功后，`applyGroupColor()`（2255–2258）、`cancelColorDraft()`（704–710）、`renameGroup()`、`deleteGroup()` 的回调必须**同时刷新浮层**（建议把浮层渲染并入 `renderGroups()`，保持单一入口）。

**C3 FAB 与浮层布局（T-P1-2 / T-P1-3 / T-P1-4）**
- FAB：`position:absolute`、显式 `pointer-events:auto`、append 在 `.literature-map-canvas-empty`（1267）之后、尺寸 ≤44px、带 `aria-label` / `aria-expanded` / `aria-controls`。
- 浮层：`position:absolute`（**不用** `position:fixed`，避免与抽屉 `z-index:1070` / backdrop `1060` 冲突，CSS:299,313）；`max-height` + `overflow:auto` + `overscroll-behavior:contain`；向上展开用 `bottom` 锚定，**不得**依赖负 `top`（画布 `overflow:hidden`，CSS:74）。
- 375 视口下画布可能仅 ~180px 高（CSS:289），浮层高度自适应且可滚动；Esc / 点击外部监听在 `state.active=false` 时必须解除，避免与其它视图快捷键打架。

**C4 表单复用择一写死（T-P2-4 / T-P1-7）**
- 采用 **(a) 搬 DOM**：把 `#literature-map-group-form` 从原面板搬到浮层容器，`refs.groupForm` 指针不变、`createGroup()` 零改动；`renderGroups()` 重写为「只渲染浮层行」。**禁止**另造第二套表单。
- 重名 / 非法色文案走 `errorAction()` + 后端错误，不得在前端自建重名校验（`validateGroupForm()` 804–814 现状不含查重）。

**C5 XSS 与可访问性（R-P2-3 / T-P2-3）**
- 浮层渲染分组名沿用 `createElement()`（`textContent`，191–196）与 `setAttribute('title' / 'aria-label', ...)`（220–224）；禁止 `innerHTML` / `insertAdjacentHTML`。
- 可断言锚点：FAB `aria-expanded`、浮层稳定 id `#literature-map-groups-popover` + `hidden`、色块 `aria-pressed`；Esc 断言「先开→`true`→点外部→`false`」，避免 Playwright mousedown 序导致 flaky。

**C6 文件与版本号（R-P0-1 / T-P0-1 / T-P1-6）**：见上方任务拆分 6 格与版本号契约，不再另列。

**C7 验收测试（R-P0-2 / T-P0-2 / T-P1-5）**
- 新增用例文件名禁止含 spec/task 编号；测试基线数字由 dev 实跑后回填，不得沿用历史「396」。
- 高亮「不写库」断言 `window.__requestLog` 无新增 `POST/PATCH/PUT`；导出 JSON 断言无 `groupHighlight` 字段。
- 验收阶段 `tests/literature_maps` 须标注为**回归核对（零后端改动前提下）**并附 `.venv` 激活命令。
- 已知基线 `test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` 不得放宽阈值、不得固化 skip。

**C8 图例条与语义收口（R-P0-3 / R-P1-5 / T-2.3）**：见「边界」段的图例条只读、单节点颜色唯一入口、导出 JSON 保留 `color_override` 三条。

**C9 批次（R-E13）**：独立成批次、不共用版本号升级，与裁定 8 一致，无需调整。

### 实现与定向验证结果（2026-11-06，主会话读回校验）

- **任务拆分 FE-1 ~ FE-8 全部完成**，共 10 个文件：`frontend/literature-maps.js` / `.css` / `index.html`、夹具、6 个既有测试文件、1 个 node:vm 测试、1 个新增定向测试 `tests/frontend/test_frontend_map_group_fab.py`（9 用例）。零后端改动。
- **最终前端全量**：`.venv/bin/python -m pytest tests/frontend -q --deselect tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` → **exit 0，`419 passed, 1 deselected, 0 failed in 131.73s`**（改前基线 `20 failed / 388 passed`；反向断言与迁移用例均保留，用例总数净增）。
- `node --check frontend/literature-maps.js` exit 0；`node --check tests/frontend/test_frontend_selection_palette_dismiss_on_apply.js` exit 0 且真实执行输出 `ok`；`grep -c "applyNodeColor\|updateGraphColorOverrides" frontend/literature-maps.js` = 0；`innerHTML` = 0 命中。
- **版本号契约**：`literature-maps.js?v=42→43`、`literature-maps.css?v=28→29`，`index.html:9,805` / 夹具 `:8,:1120` / 6 个测试断言全部同步；`app.js?v=71` / `styles.css?v=69` 未动。
- **实现期缺陷闭合**：D-1（色块=高亮、新增 `.literature-map-group-color-open`=改色双入口）、D-2（refs 三键，FE-1 已含）、D-3（浮层 `touch-action: pan-y`）；另修 409 同图重读期间 `renderGroups()` 误收浮层（改用 `!state.selectedMapId` 判定），保留「409 后草稿与浮层可直接重试」既有契约。
- **阻塞项**：仅 1 项 —— 已知性能基线 `test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` 本机稳定超阈，干净 HEAD 同样失败，fixture 自包含、不加载本批次资源；仅命令行 deselect，未放宽阈值、未固化 skip，单独立项跟踪。
- **分派异常留痕**：实现共 6 次 `frontend-dev` 分派，其中 2 次遇账号级 429，按门禁规则重试后临时换档（任务结束已还原 `.codebuddy/agents/frontend-dev.md` 的 `model` 字段），1 次回传被截断但文件已落盘、由主会话读回确认；分端评审/回归另有 2 次 429，同样临时换档并已还原 `frontend-reviewer.md` / `frontend-tester.md`。所有「说改了」的产出均经主会话 `Read`/diff/`node --check`/真实 pytest 复核。
- **后端零回归核对**：`.venv/bin/python -m pytest tests/literature_maps -q` → exit 0，`240 passed`（性质为**回归核对（零后端改动前提下）**，非后端改动验证；`/groups`、`PUT /nodes/{id}/group`、`GET /export` 契约未受影响）。
- **分端评审 / 回归结论**：`docs/sdd/reviews/043-group-fab-frontend-review.md` —— **通过**（P0=0 / P1=0 / P2=0，四项必守逐条 PASS）；`docs/sdd/reviews/043-group-fab-frontend-regression.md` —— **READY**（10 条命令逐条记录退出码，`419 passed / 1 deselected / 0 failed`）。两份报告头部元数据由主会话代行纯文档校正并留痕，未改结论与数字。

### 部署与运行时验证（2026-11-06，真实服务）

- **服务**：`http://127.0.0.1:8000/`，`/api/health` = 200；服务已在运行且直接提供最终静态资源 `literature-maps.js?v=43` / `literature-maps.css?v=29`（零后端改动，无需重启）。
- **真实浏览器 E2E 产物**（`playwright` + 当前部署版本）：
  - `docs/sdd/plans/043/artifacts/2026-11-06-group-fab-live-e2e.json`（步骤 01–26、真实请求/响应、实体 ID、最终状态）；
  - `...-live-e2e.png`（浮层展开）、`...-highlight.png`（未分组高亮）、`...-created-highlight.png`（新建组高亮）。
- **关键实测**：目标地图 `0baabeae7268429c9f7e4de8098ae1d0`（32 节点 / 1 分组）；FAB `40×40` @ `(520.6,740)`，`position:absolute`、`pointer-events:auto`、完整位于画布内；浮层列出 `aaa` `#F06595` 与「未分组」；点「未分组」色块 `on=32 / off=0`、`aria-pressed=true`、「清除高亮」可见；清除后 `on=0 / off=0`；Esc 后 `hidden=true` / `aria-expanded=false`；三档宽度 1440 / 1024 / 375 均 `inside=true`、`h_overflow=false`；导出 JSON `schema_version=literature-map-export-v2`，含 `color_override` 字段、**不含高亮态**；高亮态下 JSON 85,535 B / PNG 70,336 B 均下载成功；高亮过程中**无任何新增 POST/PATCH/PUT**（唯一 POST 是选图时的 `analysis-queue/ensure` 202，与高亮无关）。
- **真实 API 端到端成功案例**（当前部署版本，全部 200）：
  `POST /groups` `{"name":"E2E验收分组-1106C","color":"#2e7d5b","expected_revision":321}` → 实体 `group_id=f5a79999233e40eba2a373a267536cee`；
  `PUT /nodes/21041260a5394f42891b020128fa60fa/group` `{"group_id":"f5a799..."}` → 节点 `fill` 由 `#8d80e6` 变 `#2e7d5b`；
  点新组色块 → `on=1 / off=31`、目标节点 `data-group-highlight=on`；
  导出 JSON `groups_count=2`、`has_highlight_state=false`、`has_color_override_field=true`；
  `PATCH /view`（归组后既有自动保存）→ `PUT .../group {"group_id":null}` → `DELETE /groups/f5a799...` 清理。
  **最终状态**：`GET /groups` 仅剩 `aaa` 1 组、`revision=326`、32 节点 `group_id` 全部为 `None`（E2E 数据已完全恢复，无残留）。

### 人工验收可复现步骤（交给用户前准备度自查）

1. 浏览器打开 `http://127.0.0.1:8000/`，点左侧「⌘ 文献地图」→ **等待**地图列表出现（7 张卡）。
2. 点「API E2E: Graph Attention Networks r2」卡片 → **等待**画布出现 32 个节点；右下角之外、画布**左下角**应出现 40×40 分组 icon；列表下方**不再有**「人工分组」面板。
3. 点左下角 icon → **等待**浮层展开（标题「分组」，列出 `aaa` 粉红色块 +「未分组」白块 +「＋ 新建组」）。
4. 点某分组色块 → **提示**：该组节点描边强调、其余淡化，头部出现「清除高亮」；再点同一色块或「清除高亮」→ **提示**：全部恢复默认。按 Esc 或点浮层外部 → 浮层收起但高亮保留。
5. 点「＋ 新建组」→ 填名称与颜色 → 点「创建」→ **等待**浮层出现新组；点新组行「改色」→ 选色 → 点「应用」→ **提示**：该组所有节点立即变色。
6. 先收起浮层（Esc），点任意节点 → **等待**右侧详情出现「将此论文归入」下拉；选新建组 → **提示**：该节点颜色立即变为该组颜色；详情里**应无**「节点外观」调色板。
7. 开启多选 → **提示**：工具栏不再出现颜色调色板。点「导出 JSON」/「导出 PNG」→ **等待**浏览器下载完成；导出内容不含高亮态。
8. 切换到另一张地图 → **提示**：高亮自动清除、浮层收起，分组列表不串图。
9. **失败恢复**：重名时浮层显示后端错误提示、原值保留可重试；改色遇 409「地图版本已变化」时浮层与草稿**保持展开**，点「应用」即可重试；网络失败提示可重试且不覆盖他人修改。若浮层遮住节点，按 Esc 收起后再点。
10. **产物查看**：`docs/sdd/plans/043/artifacts/2026-11-06-group-fab-live-e2e.json` 与同目录 3 张 PNG；评审报告在 `docs/sdd/reviews/043-group-fab-*.md`。

### 评审记录（本轮增量）

- 需求评审：`docs/sdd/reviews/043-group-fab-requirement-review.md` —— **通过（附 13 条强制约束）**，2026-11-06 `architect` 子代理出具；P0 4 / P1 5 / P2 3，P0 已在「Gate 2 强制约束清单」闭合。
- 技术评审：`docs/sdd/reviews/043-group-fab-tech-review.md` —— **通过（附 20 条强制约束）**，2026-11-06 `architect` 子代理出具；P0 5 / P1 7 / P2 4，P0 已闭合；核心判断「零后端改动成立」。
- 前端评审：`docs/sdd/reviews/043-group-fab-frontend-review.md` —— **通过**，2026-11-06 `frontend-reviewer` 子代理出具；P0=0 / P1=0 / P2=0，四项必守逐条 PASS。
- 单端回归：`docs/sdd/reviews/043-group-fab-frontend-regression.md` —— **READY**，2026-11-06 `frontend-tester` 子代理出具；10 条命令逐条记录退出码。
- 验收评审：`docs/sdd/reviews/043-group-fab-acceptance-review.md` —— **通过**，2026-11-06 `tester` 子代理出具；十项交付准备度 10 PASS / 0 FAIL、P0=0 / P1=0；架构师签字栏已填「同意验收通过，签字收口」。
- 合并裁决：`docs/sdd/reviews/043-group-fab-merge-decision.md` —— **同意合并**，2026-11-06 `architect` 子代理出具；DoD 10/10 PASS。

> 上述 4 份分端/验收/裁决报告因本地档位回传截断，头部元数据与个别事实表述由主会话（架构师）**代行纯文档校正并各留校正记录**；结论、P 项数量、E2E 数字、业务代码与测试均未改动。代行留痕三处：各报告头部/校正记录、本评审记录、下方变更日志。

### 变更日志（本轮增量）

- 2026-11-06 ｜ 架构师（自身，主会话代行纯文档）｜ 按用户「按照A」裁决把本段由 `待确认` 转 `已确认`，逐条冻结 8 个默认值，作废地图标签段与紧凑布局段，补执行配置／任务拆分／评审记录；**无业务代码改动**。
- 2026-11-06 ｜ 主会话（架构师）｜ `spec-status-changelog.md` 追加状态流转记录。
- 2026-11-06 ｜ `architect` 子代理（Deepseek-V4.1-Flash）｜ Gate 2 需求／技术评审双「通过附意见」，落盘两份评审报告（日志 `.codebuddy/agent-logs/spec-043/task-12/architect/20261106-121332.md`）。
- 2026-11-06 ｜ 主会话（架构师，代行纯文档）｜ 回填 33 条评审意见为「Gate 2 强制约束清单」C1–C9，重排任务拆分为 6 格 / 9 文件，写死版本号契约，闭合 9 个 P0；**无业务代码改动**。
- 2026-11-06 ｜ `frontend-dev` 子代理（6 次分派，含 2 次 429 换档）｜ FE-1~FE-8 全部实现：左下角 FAB / 浮层 / 高亮 / 改色双入口 / 移除节点级与多选调色板 / 版本号 `43/29` / 测试迁移与反向断言；闭合实现期缺陷 D-1~D-3 与 409 浮层保留。主会话逐次读回 diff 校验。
- 2026-11-06 ｜ 主会话（架构师）｜ 部署与运行时验证：`/api/health` 200、`js?v=43`/`css?v=29` 生效；真实浏览器 E2E 26 步 + 真实 API 成功案例（实体 `f5a79999233e40eba2a373a267536cee`，最终 `revision=326` 已清理恢复）落盘到 `docs/sdd/plans/043/artifacts/`。
- 2026-11-06 ｜ `frontend-reviewer` / `frontend-tester` / `tester` / `architect` 子代理｜ 前端评审通过、单端回归 READY、验收评审 10 PASS、架构师签字 + 同意合并裁决全部落盘。
- 2026-11-06 ｜ 主会话（架构师，代行纯文档）｜ 校正 4 份报告的头部元数据、约束编号、裁定/步骤编号与改动清单等事实表述；**三处留痕**：各报告头部与校正记录、上方评审记录、本变更日志；**未改任何结论、数字、业务代码或测试**。
- 2026-11-06 ｜ 主会话（架构师）｜ 本段状态由 `实施中` 转 `已完成`，`spec-status-changelog.md` 追加收口记录；`docs/sdd/retro/2026-11-06-043-group-fab-retro.md` 落盘复盘。

---

## 2026-11-06 次级按钮视觉可用性修订（待确认）

**状态：待确认。** 用户原话：`所有灰色按钮改下样式，看着像是不支持的功能`，附截图（分组浮层内两行「重命名」「删除」按钮，浅灰底 + 中灰字，观感等同禁用态）。按 Bug 处理规则追加到 Spec043（同一功能范围：分组浮层），不新建编号；**生成后停止执行，不改业务代码、不跑测试、不部署，等待用户明确确认**。

### 复现证据（2026-11-06，只读核对）

- 全局基类 `frontend/styles.css:23`：`.secondary-button { border-radius:7px; padding:9px 12px; background: var(--paper); color: var(--muted); font-size:12px; }`，其中 `--paper:#f5f5f7`、`--muted:#8b8e96`。**无 border、无 hover、无 focus-visible、无字重**，文字/背景对比度约 **3.0:1**（低于 WCAG AA 4.5:1）。
- 禁用态与可用态几乎同色：`:disabled` 只在少数作用域定义 `opacity/cursor`（如 `styles.css:1895`、`literature-maps.css:198`），全局基类未区分，因此用户把**可用**按钮误读为「不支持」。
- 分组行进一步压缩：`frontend/literature-maps.css:251` 把 `.literature-map-group-row button` 压到 `padding:6px 7px; font-size:9px`；浮层头 `:431` 为 `5px 7px / 9px`。
- 按钮确实是可用功能：`frontend/literature-maps.js:2058` 重命名、`:2064` 删除、`:2039` 改色均绑定事件；其中「改色」已有紫描边（`literature-maps.css:360`），反差更凸显其余按钮的「灰」。
- 已有同项目先例：`frontend/literature-maps.css:174-198` 顶部操作按钮已用**作用域限定**覆盖为白底 + `#4a4560` 文字（9.09:1）+ 边框 + hover/focus-visible/disabled 三态，且明确「不碰全局 `.secondary-button`」。沿用同一设计语言，避免两套视觉。

### 一句话目标

让「可用但看起来被禁用」的次级按钮在视觉上明确可点：白底 + 描边 + 高对比深色文字、hover 与键盘焦点反馈、与 `:disabled` 明确区分；**不改任何按钮的 id / class / 文案 / 显隐 / 事件绑定 / DOM 结构**。

### 待用户裁决（3 项，默认值可一键确认）

1. **范围（关键，必须裁决）**：
   - **A（默认推荐）**：`#literature-maps-view` 内全部 `.secondary-button` —— 分组浮层（改色 / 重命名 / 删除 / 清除高亮 / 创建分组 / 取消预览）、导出 JSON·PNG、多选模式、地图列表、预览面板等约 30 处；顶部条已有覆盖，需保证不被新规则反向破坏。**全局基类不动**。
   - **B（最小）**：仅分组浮层 `.literature-maps-groups-popover` 内按钮（截图所指），改动面最小，但同页其它灰按钮仍不一致。
   - **C（全站）**：改全局 `.secondary-button`，影响会话 / 项目 / 论文 / 技能等所有视图；影响面大，若选 C 则**另立新 spec** 并单独做全站回归。
2. **配色**：默认沿用顶部按钮既有色板 —— 白底 `#fff`、文字 `#4a4560`（约 9:1）、`1px solid #d8d2ff`、圆角 `8px`、字重 `600`；hover 底色 `#f0edff` + 边框 `var(--accent)`；`:focus-visible` 用 `0 0 0 3px var(--accent-soft)`；`:disabled` 保留灰底灰字 + `cursor:not-allowed`，与可用态明确区分。**「删除」默认不用红字**（`.danger-button` 红 `#b13a3a` 易被误读为错误状态）；若要求危险动作特殊标识请明示。
3. **字号与触摸目标**：分组行现 `9px` 过小，默认提到 `11px`、`min-height:28px`（`≤760px` 仍 28px，与既有媒体查询一致）；不改浮层 `max-height` 与网格列宽，若 375 档变挤则用现有 `white-space:nowrap` + `overflow:auto` 兜底，**不改 DOM 与栅格列定义**。

### 数据模型 / 端点 / 公开接口

**无变化。** 纯 CSS 作用域覆盖 + 定向测试 + 静态资源版本号；`backend/**` 零改动，不新增字段、端点、事件或存储。

### 边界（每条对应一条验收）

1. 非禁用态文字/背景对比度 ≥ 4.5:1；hover、`:focus-visible`、`:disabled` 三态取值互不相同且可区分。
2. 全局 `.secondary-button` 基础规则**逐字不变**（该 class 被会话 / 项目 / 论文 / 技能等视图复用）。
3. 按钮 id / class / 文案 / 显隐 / 事件绑定零改动；`renderGroups()` 与 `createColorPalette()` 零改动。
4. `.literature-map-group-color-open` 已有紫描边不得被新规则覆盖成灰色。
5. 上批次已交付的顶部按钮不被回归：仍 `12px / min-height:36px / 9.09:1`，`≤760px` 为 `44px`。
6. 1440 / 1024 / 375 三档宽度下浮层无横向溢出、行内按钮不换行错位。
7. 高亮、新建组、改色、重命名、删除、409 草稿重试等交互链路不回归。
8. 缓存版本：`literature-maps.css?v=29 → 30`，同步 `frontend/index.html:9`、夹具 `:8` 与 6 个测试文件的硬编码断言；`literature-maps.js?v=43`、`app.js?v=71`、`styles.css?v=69` **不动**；历史兼容 marker 注释不动。
9. XSS / DOM 契约不变（本次不新增 DOM 渲染，无 `innerHTML`）。
10. 测试诚实性：不删除用例、不新增 skip/xfail、不放宽断言或超时。

### 明确不做

- 不改全局 `.secondary-button`（除非用户明确选 C，则另立 spec 并做全站回归）；
- 不改按钮文案、id、class、显隐、事件、DOM 结构、栅格列定义；
- 不动 `frontend/literature-maps.js`、不升 JS 版本号；不动 `backend/**`、数据模型、公开接口、分组高亮逻辑；
- 不引入图标、动效库、新组件、设计系统重构；不重做上批次已交付的顶部按钮样式；
- 不放宽已知性能基线 `test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` 阈值、不固化 skip。

### 产品使用步骤（确认后作为人工验收输入）

1. 打开 `http://127.0.0.1:8000/` → 点「文献地图」→ 打开一张有分组的地图，**等待**画布出现节点。
2. 点画布左下角分组 icon → **等待**浮层展开；**观察**：「改色 / 重命名 / 删除 / 清除高亮 / ＋新建组 / 创建分组 / 取消预览」为白底 + 细描边 + 深色文字，明显可点，不再是灰块。
3. 悬停任一按钮 → **提示**：边框变紫、底色变浅紫；键盘 Tab → **提示**：出现 3px 焦点环。
4. 点「重命名」→ `window.prompt` 正常弹出；点「删除」→ 正常提交并刷新分组行；点「改色」→ 色板正常展开。
5. 切到 375px 宽 → **等待**布局稳定，按钮不溢出、触摸目标 ≥ 28px；原有分组交互全部可用。
6. **失败恢复**：改色遇 409「地图版本已变化」时浮层与草稿保持展开，点「应用」即可重试；真正禁用态（如无未分组节点）仍是灰底 + `cursor:not-allowed`，与可用态一眼可分。
7. **产物查看**：`docs/sdd/plans/043/artifacts/` 下的三档宽度截图与浏览器实测对比度数据。

### 验证方式（确认后执行）

- **定向**：新增 `tests/frontend/test_frontend_secondary_button_affordance.py`（按能力命名、不含 spec/task 编号），复用 `test_frontend_map_header_actions_readability.py` 的选择器与 `@media` 块解析工具，静态断言上述 10 条边界；真实 Chromium 实测三档宽度的 `getComputedStyle` 与对比度。
- **回归**：`.venv/bin/python -m pytest tests/frontend -q --deselect <已知基线>` 目标 `0 failed`（现基线 `419 passed / 1 deselected`，新增用例后通过数相应增加）；`node --check frontend/literature-maps.js` / `app.js`；`.venv/bin/python scripts/check_test_layout.py`。**纯 CSS 改动，不跑后端 pytest**。
- **部署验证**：服务已在运行，验证 `/api/health` 200、`/assets/literature-maps.css?v=30` 200、首页 200；真实浏览器截图落盘到 `docs/sdd/plans/043/artifacts/`。
- **真实成功案例**：本批次无新增 API；沿用同功能范围已落盘的 `2026-11-06-group-fab-live-e2e.json`（实体 `f5a79999233e40eba2a373a267536cee`、`revision=326`），收口前另跑一次当前部署版本的主路径（打开 → 浮层 → 重命名 → 删除 → 导出），落盘请求/响应/最终状态。
- **门禁**：需求/技术评审 → 前端单次实现分派 → `frontend-reviewer` + `frontend-tester` → `tester` 验收 → 架构师签字 → 台账 / 变更日志 / 复盘 / 本地 commit。

### 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本段、范围裁决、落地校验、验收签字 |
| 文档更新 `doc-updater` | 不适用（产品使用步骤已在本段给出） | — | — | — |
| 评审／合并 `architect` | 按 `.codebuddy/agents/architect.md` 的 `model` 字段 | 32k | `Task(architect)` | 增量需求／技术评审、签字、合并裁决 |
| 后端开发 `backend-dev` | 不适用（零后端改动） | — | — | — |
| 前端开发 `frontend-dev` | 按 `.codebuddy/agents/frontend-dev.md` 的 `model` 字段 | 32k | `Task(frontend-dev)` | CSS 作用域覆盖、版本号同步、定向测试 |
| 测试 `tester` | 按 `.codebuddy/agents/tester.md` 的 `model` 字段 | 32k | `Task(tester)` | 跨端验收总控 |

> 分端评审 `frontend-reviewer`、单端回归 `frontend-tester` 按单端原则分派；纯前端 CSS 改动**不跑后端 pytest**。若用户选范围 C，本执行配置作废并另立 spec。

### 任务拆分（确认后再拆）

| # | 交付 | 边界 |
|---|---|---|
| FE-1 | CSS 作用域覆盖（含三态、字号/触摸目标、375 档兜底） | 只改 `frontend/literature-maps.css` |
| FE-2 | 版本号 `css?v=29→30` + `index.html` + 夹具 + 6 个测试断言 | 历史 marker 不动、JS 版本不动 |
| FE-3 | 新增定向测试 + 三档宽度真实浏览器实测 | 不删用例、不放宽断言 |
| QA | 分端评审 / 单端回归 / 验收签字 / 台账 / 复盘 / 本地 commit | 零后端改动 |

---

## 2026-11-06 地图标签代码清理（待确认）

**状态：待确认。** 用户原话：`好像你地图的标签功能你去掉了，目前也不现实。不过暂时也用不上这个功能，你可以把相关代码也删了`。本段只读核实后**不擅自删除任何代码**——「地图标签」存在术语歧义，需用户裁决范围。

### 只读核实结论：作废的「地图标签系统」从未落地，业务代码里没有可删的实现

- spec `:616-754`「地图标签与卡片设置菜单」段终态为 `已取代（作废存档）`，`:627` 明确记录 **「无业务代码、无数据、无版本号、无部署改动」**；`:620` 列出的 `literature_map_tags` / `literature_map_tag_bindings` / 6 个端点 / `GET /api/literature-maps` 的 `tags` 派生字段 / 列表标签筛选 / 卡片右下角 ⋯ 菜单 / 「分组」改叫「标签」/ 卡片显示所属标签，**全部是当时的提案，未实施**。
- 后端：`backend/app/api/routes_literature_maps.py` 无任何 `tags` 端点；`backend/app/literature_maps/infrastructure/store.py` 无两张 tag 表；`backend/app/literature_maps/application/service.py` 无 tag 方法。全库 `tags` 命中均为无关项（Ollama `/api/tags`、OpenAPI `tags=[...]`、trace `tags`、`#research-view` 的研究标签样式）。
- 前端：`frontend/literature-maps.js` 无 `literature_map_tags` / `mapLabel` / `cardSetting` / `list-tags` / `tag-badge` / ⋯ 菜单；`:3051-3085` 的局部 `const tags = []` 是**筛选条件说明**（`year-out-of-range`、`year-unverified`、来源/会议提示），与地图标签无关。中文「标签」仅 2 处：`:1173` 的 `'标签'` label 与 `:1176` 的 `'标签显示模式'` aria-label，均属 `labelModeSelect`。`frontend/literature-maps.css` 无「标签」中文、无 `list-tags` / `card-menu` 类；`frontend/index.html` 的两个 ⋯ 按钮属于项目树 / 会话列表，非地图卡片。
- **界面上仍可见的「标签」**：工具栏 `标签 [全部 ▾]` 下拉（`labelModeSelect`，`:1174-1184`、事件 `:1569-1571`、状态 `:144/:2557/:3389/:5396`）是**节点标签显示模式**（隐藏 / 全部 / 自适应），属于在用功能，不是已作废的地图级标签系统。截图左下角紫色小 icon 是**节点分组**入口（用户此前明确「这个功能是要保留的」，刚收口的 Spec043 批次）。

### 待用户裁决（关键：三个解读差别极大）

| 选项 | 删除对象 | 影响 |
|---|---|---|
| **A（默认推荐）** | **仅删除文档**：把 spec `:616-754` 作废存档段压缩为一行留痕（或整段移除），并清理台账/评审中对该段的悬空引用 | 零业务代码改动、零测试、零版本号、零部署；**保留**节点分组功能与「标签显示模式」下拉 |
| **B** | 额外删除 `labelModeSelect`「标签显示模式」下拉及其前端状态 | 涉及 `state.labelMode` / `normalizeLabelMode` / 视图保存载荷 `label_mode`（`:3389`、`:5396`）；**跨端且触及后端视图字段兼容**，范围显著扩大，需单独评估 |
| **C** | 删除整个「节点分组」功能（`literature_map_groups` / `/groups` / 左下角 FAB / 浮层 / 高亮 / 归入） | **与用户此前「这个功能是要保留的」直接冲突**，且会推翻刚收口的 Spec043 批次；除非用户明确重写需求，否则**不做** |

> 推测：用户可能把「分组入口从列表下方移到左下角小 icon」理解成标签功能被去掉，或未注意到该 icon。请用户明确指认是哪一个（可回复「A」「只删文档」「把标签下拉也删了」「分组也不要了」）。

### 明确不做（若按默认 A）

- 不删 `labelModeSelect`、不改 `state.labelMode`、不动后端 `label_mode` 字段与视图保存载荷；
- 不删 `literature_map_groups` / `/groups` API / `group_id` / 左下角 FAB / 浮层 / 高亮 / 归入，不改导出 schema；
- 不改任何 `frontend/**`、`backend/**`、测试、夹具、版本号；不动 `data/**`；
- 不重开已收口的 Spec043 分组批次，不改其验收结论。

### 边界 / 验证（默认 A）

1. 删除后 spec 内所有引用路径仍存在（无悬空 `docs/sdd/...` 引用）；
2. `spec-status-changelog.md` 中不出现指向已删段落的行号作为唯一依据；历史归档报告中的旧路径按项目约定**不随改名重写**；
3. 「已作废存档」的结论不丢失（压缩为一行留痕，保留方向澄清与 A 裁决事实）；
4. 无关功能零回归：只改文档，不需跑 pytest、不需升版本号、不需部署；
5. 若用户选 B/C，本段边界作废，须回到 spec 重新确认并另立执行配置。

---

## 2026-11-06 论文详情面板高度对齐（待确认）

**状态：待确认。** 用户附截图原话：`论文详情右下角是空的，还是跟左中板块对齐吧，高度改成一致的`。

### 复现证据（真实 Chromium `1440×900`，只读实测）

| 元素 | y | h | bottom | 计算样式 |
|---|---|---|---|---|
| `.literature-map-grid` | 228 | **707** | 935 | `align-items: stretch` |
| `.literature-map-list-panel`（左） | 228 | **707** | 935 | `min-height: 700px` |
| `.literature-map-canvas-panel`（中） | 228 | **707** | 935 | `min-height: 700px`，含展开的 `.literature-map-analysis-queue` 78px |
| `.literature-map-detail-panel`（右） | 228 | **700** | **928** | `min-height: 700px` + **`max-height: min(700px, calc(100vh - 160px))`** |

- 根因：`frontend/literature-maps.css:19-20` 单独给详情面板设了 `max-height: min(700px, calc(100vh - 160px))`，把右列**钳死在 700px**；左/中列无上限、随内容（尤其「摘要分析队列」/ 预览面板展开）自然增高，grid 行高被它们撑到 707px 以上。`align-items: stretch` 本可让右列跟随，但被 `max-height` 阻断，于是右下角留白。
- 截图里右详情面板明显短于左中板块，即为该上限在不同视口 / 队列状态下放大后的表现。
- 内部滚动已就绪：`.literature-map-detail` 为 `display:grid; flex:1 1 auto; min-height:0; overflow:auto`（`:92`），右列变高后长内容可自行滚动，不会把面板撑破。
- 移动端（`@media (max-width:760px)`）详情面板是**底部抽屉**，另有 `height: min(34dvh,320px); max-height: min(34dvh,320px)`（约 `:296-298`），与桌面基态是两套规则，**必须保留**。

### 目标与默认方案

让桌面态右详情面板高度跟随 grid 行高，与左 / 中列**底部齐平**，消除右下留白；不改 DOM、事件、显隐、内容。默认做法是**移除桌面基态的 `max-height` 钳制**（改为 `max-height: none` / 或让 `height:100%` 生效），保留 `min-height` 与内部 `overflow:auto`；`≤760px` 抽屉规则不动。

### 待用户裁决

1. **对齐口径**（默认：右列严格跟随 grid 行高 = 与中列同底，随队列面板展开/收起动态变化）；若要求「固定与左列 700px 一致、不随队列变高」，需另设固定高度，会让中列反而溢出，默认不采用。
2. **详情未打开时**（默认：面板 `hidden` 时 `display:none !important`，不产生空白列；不为对齐而渲染空壳）。
3. 是否同时调整左列 `min-height`（默认：不动，左列已 stretch 正常）。

### 明确不做

- 不改 DOM 结构、id / class、事件绑定、显隐逻辑、`renderNodeDetail()`；不动 `frontend/literature-maps.js`、不升 JS 版本号；
- 不动 `backend/**`、数据模型、接口、导出内容；不动移动端抽屉形态与三档宽度断点；
- 不引入新组件、不动顶部按钮 / 分组浮层 / 图例条；不放宽已知性能基线用例。

### 边界（每条对应一条验收）

1. 桌面 1440 / 1024 两档：右详情面板 `bottom` 与中列 `bottom` 相等（误差 ≤ 1px）；
2. 「摘要分析队列」展开与收起两种状态下均对齐；
3. 详情内容超长时内部 `overflow:auto` 滚动可用，不把面板撑破、不出现双滚动条；
4. `≤760px` 抽屉仍为 `min(34dvh,320px)`、从底部滑入、三档宽度无横向溢出；
5. 点节点打开详情、关闭详情、Esc、切图后高亮清除等交互零回归；
6. 版本号：若与「次级按钮视觉可用性修订」同批次实施，共用一次 `literature-maps.css?v=29 → 30`；同步 `frontend/index.html:9`、夹具 `:8` 与 6 个测试断言；`js?v=43` / `app.js?v=71` / `styles.css?v=69` 不动；历史 marker 注释不动；
7. 测试诚实性：不删用例、不 skip/xfail、不放宽断言。

### 验证方式（确认后执行）

- 真实 Chromium 实测三档宽度 + 队列展开/收起两组，落盘 `getBoundingClientRect()` 三列高度 / bottom 与 `getComputedStyle` 的 `max-height`；
- 定向静态断言（选择器作用域、`max-height` 取值、`≤760px` 规则未被覆盖）；
- 回归 `.venv/bin/python -m pytest tests/frontend -q --deselect <已知基线>` 目标 `0 failed`（现基线 `419 passed / 1 deselected`）、`node --check`、`.venv/bin/python scripts/check_test_layout.py`；纯 CSS 改动不跑后端 pytest；
- 部署验证 `/api/health` 200、`css?v=30` 200、截图落盘 `docs/sdd/plans/043/artifacts/`。

---

## 本批次待确认项汇总（七项；产出时快照，裁决以文末「2026-11-06 用户裁决与本批次冻结范围」段为准）

| # | 项目 | 需用户确认 | 默认值 |
|---|---|---|---|
| 1 | 次级按钮视觉可用性（`:1044` 段） | 范围 A / B / C；配色；字号 | A（地图视图内）、沿用顶部按钮色板、`9→11px` |
| 2 | 地图标签代码清理（`:1136` 段） | 删文档 / 删标签下拉 / 删分组功能 | **A：只删 spec 作废存档文档**，业务代码不动 |
| 3 | 详情面板高度对齐（`:1174` 段） | 对齐口径 | 右列跟随 grid 行高、与中列同底 |
| 4 | **「可用」筛选结果为空 Bug**（`:1247` 段） | 修复方向 A / B / C；「部分完成」是否仍含可用地图 | **A：筛选匹配徽标的可用集合**（`ready` 或 `partial` 且有节点），「部分完成」仍按原始 status |
| 5 | **「跳过 2」无原因 Bug**（`:1336` 段） | 信息粒度 A / B / C；补救入口；标题来源 | **A：后端投影补 `skipped_items` + 前端列明论文与中文原因**，只提示不加按钮 |
| 6 | **「主题相似」勾选无感**（`:1431` 段） | 修复方向 A / B / C / D（D=删除图层） | **A：加说明 + 提升虚线可见度 + 切换状态提示**，不删图层 |
| 7 | **单篇全文 RAG 被误判为深度研究 Bug**（`:1515` 段） | 修复方向 A+B / C / D；单篇会话是否允许显式深度研究；sticky 清理 | **A+B：会话 binding 短路 Intake + 分类器加单篇负向特征**，纯后端、零前端改动 |

> 七项若一起确认，建议**合并为一个跨端批次**：第 1 / 3 / 6 项改 `literature-maps.css`（`css?v=29→30`），第 4 / 5 / 6 项改 `literature-maps.js`（`js?v=43→44`），第 5 项改后端队列投影、第 7 项改后端会话入口与分类器；按前后端分派原则**拆成后端一次、前端一次**两次分派，共用一次分端回归、一次部署验证、一次本地 commit。第 2 项若选 A 则纯文档、不增加代码改动。
>
> **优先级**：第 4 / 5 项是功能性缺陷、第 7 项是**主路径意图路由错误**（用户明确指定为全文分析 Bug 处理），三者建议优先；第 6 项是可用性/可解释性缺陷（功能本身有效）；第 1 / 3 项为样式修订。第 7 项按用户指示**不新建 spec 编号**，挂在本 Spec043。
>
> **在用户明确确认前，不改任何业务代码、不跑测试、不升版本号、不部署。**

---

## 2026-11-06 「可用」状态筛选结果为空（Bug 修订，待确认）

**状态：待确认。** 用户附截图原话：`这个可用的筛选有问题啊，明明是有可用的地图，筛选完就不见了？` 截图显示「我的地图 `0/7`」、状态下拉选中「可用」、列表空白。按 Bug 处理规则追加到 Spec043（同一功能范围：地图列表状态筛选），不新建编号；**本轮只做只读复现，不改业务代码、不跑测试、不部署**。

### 最小复现（真实服务，2026-11-06）

1. `GET /api/literature-maps` → `schema_version=literature-map-v1`，共 **7** 张地图，`status` 分布 **`partial: 7`**（`ready: 0`）。其中 **5 张 `node_count > 0`**（32 / 21 / 20 / 20 / 20），2 张 `node_count = 0`。
2. 打开文献地图 → 卡片徽标显示「**可用**」的正是这 5 张（见下）；展开状态下拉选「可用」→ 计数变 `0/7`、列表空白、与用户截图一致。
3. 期望：选「可用」应列出这 **5** 张；实际：**0** 张。

### 根因（展示语义与筛选语义各用一套定义）

- **卡片徽标** `mapCardStatusBadge()`（`frontend/literature-maps.js:1811-1825`）：当 `status === 'partial'` 且 `node_count > 0` 时，把徽标文案改成 `mapStatusLabel('ready')` = 「可用」，并加 `data-availability="usable"` / `title` / `aria-label`。这是此前为修「partial 看起来像地图坏了」而做的**局部映射**，注释明确写着「只对卡片做局部映射：全局状态文案表与列表筛选下拉保持原样」。
- **筛选谓词** `filteredMaps()`（`:1633-1639`）：`const matchesStatus = state.listStatus === 'all' || map?.status === state.listStatus;` —— **严格按后端原始 `status` 匹配**，不认徽标的「可用」映射。
- **下拉选项**（`:1009`）：`['ready', '可用']`，即「可用」= `ready`。
- 后端 `status` 计算（`backend/app/literature_maps/application/service.py:235-255`）：`ready` 仅在初始建图全成功时写入；只要有任何失败单元就写 `partial`（有节点）/`failed`（无节点）。历史 7 张地图全为 `partial`，`ready` 为 0，于是「可用」筛选必然空。
- **现有测试把不一致固化了**：`tests/frontend/test_frontend_map_card_count_and_availability_badge.js` 第 8 组断言 `MODULE.includes("['partial', '部分完成']")` 与「下拉不随卡片徽标局部映射改变」，即当前契约**明确要求**筛选仍按原始 `status`。修复时必须**更新该断言为新契约**，而不是删除用例。

### 待用户裁决（修复方向 3 选 1）

| 选项 | 做法 | 影响 |
|---|---|---|
| **A（默认推荐）** | 让「可用」筛选匹配**徽标所显示的可用集合**：`status === 'ready' \|\| (status === 'partial' && node_count > 0)`；新增一个共用判定函数供徽标与筛选谓词复用，消除两套定义 | 纯前端 `literature-maps.js` 改动；与用户直觉一致；`partial` 且无节点的 2 张仍只出现在「部分完成」；需同步更新 node:vm 断言与 `js?v=43→44` |
| **B** | 撤销卡片「可用」局部映射，`partial` 一律显示「部分完成」，筛选不变 | 会让此前用户投诉的「看着像坏了」观感回归，且「可用」筛选仍永远为空（本地无 `ready` 地图），**不解决用户诉求** |
| **C** | 后端把有活动节点的 `partial` 归一/迁移为 `ready` | 触及 status 语义、历史数据迁移、作业恢复与 409 契约，范围显著扩大，需另立 spec 并做后端回归 |

> 另需用户确认：选 A 时，「部分完成」筛选项是否**仍包含**这 5 张（默认：**是**，保持按原始 `status` 过滤，即同一张地图可同时出现在「可用」与「部分完成」两个筛选结果中），还是改为「可用」优先互斥（默认不采用，会改变既有筛选语义）。

### 目标

消除「卡片显示可用、筛选却查不到」的语义割裂：用户选「可用」时，列表应列出所有卡片显示为「可用」的地图，计数 `5/7`（以当前真实数据为准），且不改变任何地图的后端 `status`、作业语义或选图行为。

### 数据模型 / 端点 / 公开接口

**无变化。** 默认 A 为纯前端筛选谓词改动；不新增字段、端点、事件、存储，不写库、不改 `revision`。

### 边界（每条对应一条验收）

1. `status='ready'`（任意 `node_count`）→ 命中「可用」；
2. `status='partial'` 且 `node_count > 0` → 命中「可用」，且徽标仍显示「可用」带 `data-availability="usable"`；
3. `status='partial'` 且 `node_count` 为 `0` / 缺失 / 非法 / 负数 → **不**命中「可用」，徽标仍「部分完成」；
4. `generating` / `failed` / `stopped` / `queued` 等其它 status → 不受影响；
5. 「部分完成」筛选按原始 `status='partial'` 仍列出全部 7 张（含被「可用」命中的 5 张），「全部状态」为 7 张，三者计数自洽；
6. 状态筛选与搜索框 `listQuery` 可组合（标题/主题命中后再按状态过滤）；
7. 筛选结果为空时 `listEmpty` 提示正常显示、计数 `0/N` 正确；切换回「全部状态」恢复全部；
8. 徽标与筛选项共用同一判定函数，禁止出现第三套「可用」定义；`mapStatusLabel('ready')` 全局文案表、下拉选项文案、后端 `status` 字面量不变；
9. 选图、切图、轮询刷新 `state.maps` 后筛选结果稳定；不触发额外网络请求、不写库；
10. XSS / DOM 契约不变（`node_count` 只做数值比较，无 `innerHTML`）；测试诚实性：不删用例、不 skip/xfail、不放宽断言。

### 明确不做

- 不改后端 `status` 计算、不做数据迁移、不改 `/api/literature-maps` 响应结构（除非用户选 C，另立 spec）；
- 不撤销卡片「可用」徽标映射（除非用户选 B）；不改徽标 `title` / `aria-label` 说明文案；
- 不改下拉选项的 value / 文案、不改 `mapStatusLabel` 全局表、不改选图/详情/分组/高亮/导出逻辑；
- 不引入新组件或第三方依赖；不放宽已知性能基线用例阈值、不固化 skip。

### 产品使用步骤（确认后作为人工验收输入）

1. 打开 `http://127.0.0.1:8000/` → 点「文献地图」，**等待**「我的地图」显示 `7/7`。
2. 观察 5 张卡片徽标为绿色「可用」（悬停可见完整说明），2 张为「部分完成」。
3. 状态下拉选「可用」→ **等待**列表刷新；**提示**：计数变 `5/7`，列出上述 5 张，不再空白。
4. 再搜索框输入关键词 → **提示**：在「可用」结果内二次过滤，计数同步。
5. 切回「全部状态」→ **提示**：恢复 `7/7`；选「部分完成」→ **提示**：7 张都在（含 5 张可用）。
6. 点任一结果卡片 → **等待**画布正常打开，状态筛选保持、不误触其它交互。
7. **失败恢复**：若网络刷新后 `node_count` 暂缺，卡片回落「部分完成」且不进入「可用」结果，刷新页面可恢复；产物查看 `docs/sdd/plans/043/artifacts/` 下的筛选前后截图与计数。

### 验证方式（确认后执行）

- **定向**：更新 `tests/frontend/test_frontend_map_card_count_and_availability_badge.js`（node:vm，真实抽取 `filteredMaps` / `mapCardStatusBadge`），新增参数化用例覆盖边界 1–6、8；**改写第 8 组断言**为「徽标与筛选共用同一可用性判定」而非删除用例；新增静态契约断言共用函数存在且两处调用。
- **真实浏览器**：当前部署版本打开地图列表，分别选「可用 / 部分完成 / 全部状态」，落盘计数与可见卡片 `data-map-id` 列表到 `docs/sdd/plans/043/artifacts/`。
- **回归**：`.venv/bin/python -m pytest tests/frontend -q --deselect <已知基线>` 目标 `0 failed`（现基线 `419 passed / 1 deselected`）；`node --check frontend/literature-maps.js`；`.venv/bin/python scripts/check_test_layout.py`；纯前端改动**不跑后端 pytest**。
- **版本**：`literature-maps.js?v=43 → 44`，同步 `frontend/index.html:805`、夹具 `:1126` 与 6 个测试文件硬编码断言；`css`/`app.js`/`styles.css` 版本按其它已确认项决定；历史 marker 注释不动。
- **部署**：`/api/health` 200、`js?v=44` 200、首页 200；真实浏览器筛选主路径截图落盘。

### 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 复现定位、修订本段、落地校验、验收签字 |
| 文档更新 `doc-updater` | 不适用（产品使用步骤已在本段给出） | — | — | — |
| 评审／合并 `architect` | 按 `.codebuddy/agents/architect.md` 的 `model` 字段 | 32k | `Task(architect)` | 增量需求／技术评审、合并裁决 |
| 后端开发 `backend-dev` | 不适用（默认 A 零后端改动） | — | — | — |
| 前端开发 `frontend-dev` | 按 `.codebuddy/agents/frontend-dev.md` 的 `model` 字段 | 32k | `Task(frontend-dev)` | 筛选谓词修复、共用判定函数、测试与版本号 |
| 测试 `tester` | 按 `.codebuddy/agents/tester.md` 的 `model` 字段 | 32k | `Task(tester)` | 跨端验收总控 |

> 分端评审 `frontend-reviewer`、单端回归 `frontend-tester` 按单端原则分派；纯前端改动不跑后端 pytest。若用户选 C，本执行配置作废并另立 spec。

---

## 2026-11-06 摘要分析队列「跳过 2」无原因（Bug 修订，待确认）

**状态：待确认。** 用户附截图原话：`这里为什么要跳过2个？也没给出原因。` 截图显示「摘要分析队列 / 状态：已完成 / 完成 30/32 · 排队 0 · 运行 0 · 失败 0 · **跳过 2**」，只有数字、无原因、无论文身份、无补救入口。按 Bug 处理规则追加到 Spec043（同一功能范围：摘要分析队列），不新建编号；**本轮只做只读复现，不改业务代码、不跑测试、不部署**。

### 最小复现与真实数据（2026-11-06，只读）

1. `GET /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/analysis-queue` → `state: completed`、`counts: {total:32, completed:30, queued:0, running:0, failed:0, skipped:2}`、`failed_items: []`。响应顶层字段：`schema_version / map_id / queue_job_id / state / pause_reason / counts / current / failed_items` —— **没有跳过项明细，也没有 skip_reason 聚合**。
2. 只读查询 `data/literature_maps/literature_maps.sqlite3` 的 `literature_map_jobs`（`operation='analysis_queue'`，`cursor_json.items`）确认 2 个跳过项：
   - `node_id=2e45cfdbec4d4c48b41fe8091e0fe742`：`{"status":"skipped","skip_reason":"MAP_ABSTRACT_UNAVAILABLE","retryable":false}`
   - `node_id=c6e208e158a1418a8b529d96b5592777`：同上
   - 即**两篇论文缺少摘要，无法生成摘要级分析**，且标记为不可重试。同库另有 3 张地图同样有 1–2 个 `MAP_ABSTRACT_UNAVAILABLE` 跳过项，属普遍情形而非个例。
3. 前端 `renderAnalysisQueue()`（`frontend/literature-maps.js:5993-6047`）只渲染 `counts` 那一行文字（`:6016`），以及 `pause_reason` / `current` / 动作按钮 / `failed_items`（`:6045`）；**没有任何跳过项渲染分支**。

### 根因（原因存在，但链路上被丢了两层）

- **写入层**：`backend/app/literature_maps/infrastructure/store.py:1603-1609` 在 `ensure` 时对 `abstract_available=false` 的候选写入 `status="skipped"` + `skip_reason="MAP_ABSTRACT_UNAVAILABLE"` + `retryable=false`，原因是**有**的。
- **投影层**：`_queue_projection_tx()`（`:1875-1919`）遍历 items 时只收集 `current` 与 `failed_items`（`status in {failed, stopped}`），**完全跳过 `status == "skipped"` 的项**；返回的 dict 里也没有 `skipped_items` 字段。`_queue_counts_tx()`（`:1651-1668`）只把 skipped 累加成计数。
- **API 层**：`GET /{map_id}/analysis-queue`（`backend/app/api/routes_literature_maps.py:521-527`）用 `_envelope(**queue)` 原样透传，没有额外派生。
- **展示层**：前端只有数字，没有明细 DOM。但**中文原因映射已存在**：`safeAnalysisReason()`（`frontend/literature-maps.js:6226-6242`）已把 `MAP_ABSTRACT_UNAVAILABLE` 译为「缺少摘要，不能生成摘要级分析；请先获取摘要。」；另有 `queueItemLabel()`（`:5985-5991`）可复用论文名，以及 `analysisStatusLabel` 中 `skipped_no_abstract: '无摘要，已跳过'`（`:3019`）、`PARTIAL_MAP_CARD_NOTICE` 等既有文案。
- **结论**：这是**可观测性缺陷**，不是分析失败；不需要重跑队列、不需要补摘要、不需要改 status 或计数语义。

### 目标

让用户在「摘要分析队列」面板直接看到：跳过几项、**各是哪篇论文**、**为什么跳过**、**能否补救**；不改动队列状态机、计数、重试语义与后端 status。

### 待用户裁决（3 项）

1. **信息粒度**（默认 A）：
   - **A（默认）**：后端投影新增 `skipped_items: [{node_id, title?, skip_reason, retryable}]`，前端在计数行下方新增一行「跳过原因」+ 最多 5 条明细（论文名 + 中文原因），超出显示 `+N`。**跨端小改动**（后端只读投影 + 前端渲染）。
   - **B（最小，纯前端）**：不改后端，只在前端把 `counts.skipped` 后追加静态说明「跳过项因缺少摘要，无法生成摘要级分析；请先获取摘要」——但**无法指出是哪 2 篇**，且原因写死、遇到别的 `skip_reason` 会失真。
   - **C（仅聚合）**：后端只返回 `skip_reasons: {"MAP_ABSTRACT_UNAVAILABLE": 2}` 聚合计数，前端显示「跳过 2：缺少摘要 2」，不列论文名。改动比 A 小，但用户仍不知道是哪两篇。
2. **补救入口**（默认：**只提示、不加按钮**）：`retryable=false`，默认不提供「重试」按钮，只给可操作文案「请先获取摘要」（与既有 `safeAnalysisReason` 一致）；若希望提供「去获取摘要」跳转 / 重试入口，属范围扩大，需单独确认。
3. **论文标题来源**（默认：由后端 `skipped_items` 带出 `title`，从 `literature_map_nodes` 只读查；节点已移出时回落为 `node_id` 前 8 位 +「（已移出）」）。前端不额外发请求。

### 数据模型 / 端点 / 公开接口

- **`GET /api/literature-maps/{map_id}/analysis-queue` 响应新增可选字段 `skipped_items`**（默认 A / C 时）；`schema_version` 不变（**只增字段、不改既有字段语义**），`counts`、`state`、`failed_items` 全部保持原样，旧客户端忽略新字段即可。
- 不新增端点、不新增表/列、不改 `cursor_json` 结构、不改 `revision`、不写库（投影只读）；`POST /ensure` / `pause` / `resume` / `retry` 返回结构如需保持一致，可同样带上 `skipped_items`（默认：**是**，避免不同端点表现不一致）。
- 若用户选 B，则**零后端改动**。

### 边界（每条对应一条验收）

1. 无跳过项时 `skipped_items=[]`，前端**不渲染**原因行（不出现空白占位），旧行为完全保持；
2. 有 1 / 2 / N 个跳过项时，计数与明细条数自洽；超过 5 条显示 `+N` 且 `title` / `aria-label` 可查看全部原因；
3. `skip_reason` 已知（`MAP_ABSTRACT_UNAVAILABLE` 等）→ 显示中文原因；未知 / 缺失 / 异常值 → 回落「原因待核实」+ 原始码经 `safeAnalysisReason` 转义，**不把原始字符串当 HTML、不 `innerHTML`**；
4. 原因文案复用 `safeAnalysisReason()`，禁止新增第二套原因表；`retryable=false` 不出现重试按钮；
5. `title` 缺失 / 节点已移出时按默认值回落，不抛异常、不显示 `undefined` / `null`；
6. `pause` / `resume` / `retry` / `ensure` 各端点返回结构一致（含 `skipped_items`），不触发 409 / 不改变 `revision`；
7. owner 隔离：只读投影必须沿用现有 `_assert_map_exists_readonly` / owner 过滤，不跨 owner 泄露 node_id / title；
8. 队列 active / paused / completed / partial 各状态下原因行都可见且不遮挡动作按钮；移动端 `≤760px` 不横向溢出；
9. 其它功能零回归：选图、节点详情、分组浮层、导出、状态筛选不与队列面板互相影响；
10. 测试诚实性：不删用例、不 skip/xfail、不放宽断言；现有 `tests/frontend/test_frontend_map_analysis_queue.py` 的 `完成 1/4`、`失败 1` 等断言保持。

### 明确不做

- 不重跑分析、不自动补摘要、不改 `status='skipped'` 项、不把 `retryable` 改成 true、不改计数语义；
- 不改 `cursor_json` 结构、不新增表/列、不改 `schema_version`、不写库、不改 `revision`、不引入新端点；
- 不新增「获取摘要」按钮或跳转（除非用户在裁决 2 明确要求）；
- 不动 `backend/**` 其它模块、不动 `frontend/literature-maps.css`（除非布局需要一名选择器，届时纳入同批次 CSS）、不改导出内容；
- 不放宽已知性能基线用例阈值、不固化 skip。

### 产品使用步骤（确认后作为人工验收输入）

1. 打开 `http://127.0.0.1:8000/` → 点「文献地图」→ 打开 `API E2E graph attention networks r2`，**等待**「摘要分析队列」面板出现。
2. **观察**：计数行仍为「完成 30/32 · … · 跳过 2」，其下新增「跳过 2 项：缺少摘要，不能生成摘要级分析；请先获取摘要。」并列明 2 篇论文标题。
3. 悬停 / 键盘聚焦明细 → **提示**：`title` / `aria-label` 显示完整原因与 node_id；`retryable=false` 故**没有**重试按钮。
4. 切到另一张有 1 个跳过项的地图 → **等待**队列刷新，原因行显示 1 项、计数自洽。
5. 切到无跳过项的地图 → **提示**：不显示原因行，面板布局与改动前一致。
6. **失败恢复**：若队列接口返回未知 `skip_reason`，显示「原因待核实」而不是空白或原始码堆叠；刷新页面可重新读取。
7. **产物查看**：`docs/sdd/plans/043/artifacts/` 下的真实 API 响应 JSON（含 `skipped_items`）与队列面板截图。

### 验证方式（确认后执行）

- **后端定向**：`tests/literature_maps/` 新增投影测试，覆盖边界 1–3、6–7（无跳过 / 1 项 / 多项 / 未知原因 / owner 隔离 / 各端点结构一致）；用真实 `analysis_queue` 游标 fixture，不 mock 内部函数替代真实投影。
- **前端定向**：`tests/frontend/` 新增或扩充队列契约测试，断言渲染分支、回落文案、无 `innerHTML`、移动端不溢出；复用 fixture 的 `?queue` 分支并补 skipped 数据。
- **真实 API 成功案例**：当前部署版本 `GET /api/literature-maps/{map_id}/analysis-queue` 返回含 2 个 `skipped_items` 且 `skip_reason=MAP_ABSTRACT_UNAVAILABLE`，落盘请求、响应、实体 ID（`node_id`）、最终状态（`state=completed`、`counts` 不变）与产物路径。
- **回归**：`.venv/bin/python -m pytest tests/literature_maps -q`（现基线 `240 passed`）、`tests/frontend -q --deselect <已知基线>`（现基线 `419 passed / 1 deselected`）；`node --check`、`ruff`（若按项目配置启用）、`scripts/check_test_layout.py`。此项**跨端**，需按「前后端分派原则」拆成两次分派。
- **版本**：若选 A / C 需改 `literature-maps.js` 渲染 → `js?v=43→44`；同步 `frontend/index.html:805`、夹具 `:1126` 与 6 个测试断言；若同时实施第 1 / 3 / 4 项，共用一次版本号升级与一次部署验证。后端改动**无需重启服务**（服务已加载代码？部署验证时需确认，若需重启按 `deploy/README.md` 执行并验证 `/api/health` 200）。
- **门禁**：需求/技术评审 → 后端一次分派 + 前端一次分派 → `backend-reviewer`/`backend-tester` 与 `frontend-reviewer`/`frontend-tester` → `tester` 跨端验收 → 架构师签字 → 台账 / 变更日志 / 复盘 / 本地 commit。

### 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 复现定位、修订本段、落地校验、验收签字 |
| 文档更新 `doc-updater` | 不适用（产品使用步骤已在本段给出） | — | — | — |
| 评审／合并 `architect` | 按 `.codebuddy/agents/architect.md` 的 `model` 字段 | 32k | `Task(architect)` | 增量需求／技术评审、合并裁决 |
| 后端开发 `backend-dev` | 按 `.codebuddy/agents/backend-dev.md` 的 `model` 字段 | 32k | `Task(backend-dev)` | 队列投影新增 `skipped_items` + 后端定向测试 |
| 前端开发 `frontend-dev` | 按 `.codebuddy/agents/frontend-dev.md` 的 `model` 字段 | 32k | `Task(frontend-dev)` | 原因行渲染、回落文案、版本号与前端测试 |
| 测试 `tester` | 按 `.codebuddy/agents/tester.md` 的 `model` 字段 | 32k | `Task(tester)` | 跨端验收总控 |

> **跨端改动按前后端分派原则拆成两次分派**（后端一次、前端一次），不得派一个通吃 agent；回归同理，分端各跑各的。若用户选 B（纯前端），本执行配置的后端行改为「不适用（零后端改动）」且不跑后端 pytest。

---

## 2026-11-06 「主题相似」勾选框无感（待确认）

**状态：待确认。** 用户附截图问：`这个主题相似有什么作用，我点击了没反应。` 截图为已勾选的「☑ 主题相似」复选框。按 Bug 处理规则追加到 Spec043（同一功能范围：文献地图图层工具栏），不新建编号；**本轮只做只读复现，不改业务代码、不跑测试（除只读 fixture 复现）、不部署**。

### 只读复现：功能其实是**有效**的，问题在「看不出变化」+「没有作用说明」

1. **控件身份**：这不是按钮，是**图层显示开关**。`LAYER_NAMES = ['citation', 'similarity']`（`frontend/literature-maps.js:53`）；`:1163-1172` 创建两个 checkbox（`data-layer`），文案「引用关系」/「主题相似」，默认 `checked=true`；`state.layers` 初值 `{citation:true, similarity:true}`（`:145`）。
2. **change 链路完整**：`:1561-1567` 监听 `change` → 写 `state.layers[kind]` → `state.viewDirty=true` → `renderGraph()` → `scheduleViewSave()`；`renderGraph()` 在 `:4919` 按 `state.layers[edge.kind]` 过滤边；视图设置持久化到 `layers`（`:3388`、`:5395`），重进地图时 `normalizeMap()` 恢复（`:2556-2560`）。
3. **本地 fixture 实测（`?palette`，不访问服务、不写库）**：初始 `simEdges=1 / citEdges=1` → 取消「主题相似」后 `simEdges=0 / citEdges=1`、勾选变 false、产生 1 条 view 保存 → 重新勾选恢复 `simEdges=1`。**即点击确实生效**。
4. **真实服务 `0baabeae…` 的图**：32 节点 / 29 条边，其中 `citation=24`、**`similarity=5`**；similarity 边是 `#b7a9db` 浅紫虚线 `5 4`、`stroke-width:1.15`、**`opacity:.56`**（`frontend/literature-maps.css:78-80`），在 24 条实线中极不显眼；5 条里还有 **2 条与 citation 边端点对完全重叠**（`065389f0…↔a4917994…`、`21041260…↔28d6f906…`），后绘制的虚线覆盖或被实线视觉吞没。因此去掉 5 条淡虚线，用户几乎看不出差别。
5. **作用说明缺失**：控件只有 4 个字，无 `title` / `aria-describedby` / tooltip；画布底部图例只有一句「虚线：主题相似（无向）」（`:1261`），未说明它是**按标题+摘要向量余弦相似度自动连边**（`backend/app/literature_maps/application/similarity.py:39-72`，`top_k=3`、阈值 `SIMILARITY_THRESHOLD`；真实边 `basis=title_abstract`、`score≈0.76–0.83`），也未说明勾选框只控制**显示/隐藏**、不影响计算与存储。

### 目标

让用户一眼明白「主题相似」是什么、勾选/取消会改变什么，并在切换时得到明确反馈；**不改变图层过滤、边生成、视图保存的既有语义**。

### 待用户裁决（3 项）

1. **修复方向**（默认 A）：
   - **A（默认，纯前端小改动）**：① 给两个图层勾选框加 `title` / `aria-label` 说明（主题相似 = 按标题与摘要的语义相似度自动连的虚线；勾选仅控制显示，不影响已计算的边）；② 提升 similarity 边可见度（如 `stroke` 加深、`stroke-width` 略增、`opacity` 从 `.56` 提到约 `.8`，仅作用于 `.similarity`，不动 `.citation`）；③ 切换时给一行轻量状态提示（如「主题相似：已隐藏 5 条相似边」/「已显示 5 条」），与现有 `#literature-map-status` 一致。
   - **B（最小，仅说明）**：只加 tooltip / 说明文字，不动样式与提示——改动最小，但「点了没反应」的观感仍在。
   - **C（重新设计）**：把勾选框改成带计数徽标的图层按钮 / 加图例交互筛选 / 换边样式体系——范围扩大，需另定视觉与回归范围。
   - **D（保留疑问）**：若用户其实想**去掉主题相似图层**（类似上一项「标签用不上」），需明确说明；默认**不删**（它是已实现的图谱能力，且有 5 条真实边）。
2. **状态提示位置**（默认：复用 `#literature-map-status`，不新增 DOM 容器；提示 2–3 秒或由下一次状态覆盖，不引入定时器堆叠）。
3. **相似度边的可见度取值**（默认：由前端评审按对比度实测定，约束为不遮挡节点、不与 citation 实线混淆、三档宽度可辨）。

### 数据模型 / 端点 / 公开接口

**无变化。** 纯前端 CSS + JS 文案/提示；不新增端点、字段、事件、存储，不改 `layers` 的视图保存载荷结构，不改 `revision` 语义。

### 边界（每条对应一条验收）

1. 取消「主题相似」→ 画布 `.literature-map-edge.similarity` 数量归 0，「引用关系」边数量不变；重新勾选 → 恢复原数量（真实服务应为 5）；
2. 取消「引用关系」→ citation 边归 0、similarity 边不变；两个开关互不干扰、可同时关闭；
3. 切换后 `scheduleViewSave()` 仍只发一次视图保存，`layers` 载荷结构不变，重进地图后开关状态与隐藏状态一致（不出现「勾选是开的但边不显示」）；
4. 图层状态与分组高亮、节点样式、多选、标签显示模式并存时互不破坏；
5. 无 similarity 边的地图：勾选框仍可切换，提示为「0 条」，不抛异常、不显示 `undefined`；
6. 说明文案走 `title` / `setAttribute` / `textContent`，**禁止 `innerHTML`**；`aria-label` 不丢失原有可访问性；
7. 三档宽度 1440 / 1024 / 375 工具栏不溢出、勾选目标 ≥ 28px（≤760px）；
8. similarity 边加深后仍为虚线、仍与 citation 实线/箭头可区分，导出 PNG / SVG 样式同步（`:5682` 有导出专用 CSS）；
9. 其它功能零回归：选图、详情、分组浮层、状态筛选、摘要分析队列；
10. 测试诚实性：不删用例、不 skip/xfail、不放宽断言；已知性能基线用例不放宽阈值、不固化 skip。

### 明确不做

- 不改相似度算法、阈值、`top_k`、向量来源、边生成时机，不重算已有边、不写库；
- 不改 `layers` 的字段名 / 载荷结构 / 端点，不改 `renderGraph()` 的边过滤谓词语义；
- 不删除主题相似图层或 similarity 边（除非用户明确选 D 并另行确认）；
- 不引入新组件、第三方库、动画；不改导出 JSON 结构；
- 不与本批次第 1 项「次级按钮样式」混用全局 `.secondary-button` 改动（本项只涉及 `.literature-map-layer-toggle` 与 `.similarity` 边）。

### 产品使用步骤（确认后作为人工验收输入）

1. 打开 `http://127.0.0.1:8000/` → 点「文献地图」→ 打开 `API E2E graph attention networks r2`，**等待**画布出现 32 节点。
2. 悬停「主题相似」勾选框 → **提示**：出现说明「按标题与摘要语义相似度自动连的虚线；仅控制显示，不影响已计算的边」。
3. 点击取消勾选 → **等待**画布重绘；**提示**：状态行显示「主题相似：已隐藏 5 条相似边」，画布上浅紫虚线消失、实线箭头仍在。
4. 重新勾选 → **提示**：虚线恢复、状态行更新为已显示 5 条。
5. 切到另一张地图再切回 → **等待**重进完成，**提示**：开关与边的显隐状态与离开前一致。
6. **失败恢复**：若某张地图没有相似边，切换后提示「0 条」且画布不报错；导出 PNG 后核对虚线样式与画布一致。
7. **产物查看**：`docs/sdd/plans/043/artifacts/` 下的切换前后截图与计数。

### 验证方式（确认后执行）

- **定向**：本地 fixture（`?palette` 现有 `edge-sim` 边）参数化断言开关与边数、提示文案、可访问性属性、无 `innerHTML`；新增静态契约断言 CSS 中 `.similarity` 的 `stroke`/`opacity` 取值与导出 CSS 同步。
- **真实浏览器**：当前部署版本切换「主题相似」/「引用关系」，落盘切换前后边数、`getComputedStyle` 对比度、三档宽度截图。
- **回归**：`.venv/bin/python -m pytest tests/frontend -q --deselect <已知基线>` 目标 `0 failed`（现基线 `419 passed / 1 deselected`）；`node --check`、`scripts/check_test_layout.py`；纯前端改动**不跑后端 pytest**。
- **版本**：`literature-maps.js?v=43→44` 与 `literature-maps.css?v=29→30`（若与第 1 / 3 / 4 / 5 项同批次，共用一次升级）；同步 `frontend/index.html:9,805`、夹具 `:8,:1126` 与 6 个测试断言；历史 marker 注释不动。
- **部署**：`/api/health` 200、静态资源版本 200、真实浏览器主路径截图落盘。

### 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 复现定位、修订本段、落地校验、验收签字 |
| 文档更新 `doc-updater` | 不适用（产品使用步骤已在本段给出） | — | — | — |
| 评审／合并 `architect` | 按 `.codebuddy/agents/architect.md` 的 `model` 字段 | 32k | `Task(architect)` | 增量需求／技术评审、合并裁决 |
| 后端开发 `backend-dev` | 不适用（零后端改动） | — | — | — |
| 前端开发 `frontend-dev` | 按 `.codebuddy/agents/frontend-dev.md` 的 `model` 字段 | 32k | `Task(frontend-dev)` | 说明文案、边可见度、状态提示、版本号与测试 |
| 测试 `tester` | 按 `.codebuddy/agents/tester.md` 的 `model` 字段 | 32k | `Task(tester)` | 跨端验收总控 |

> 分端评审 `frontend-reviewer`、单端回归 `frontend-tester` 按单端原则分派；纯前端改动不跑后端 pytest。若用户选 D（删除图层），本执行配置作废并回到 spec 重新确认范围。

---

## 2026-11-06 单篇全文 RAG 提问被误判为深度研究（Bug 修订，待确认）

**状态：待确认。** 用户附截图原话：`这个基于全文分析打开了深度研究，意图识别错了，我只要研究这一篇文章。你研究一下目前的意图识别模块有没有对此进行区分。这里我是希望通过RAG的方式分析这篇文章。这属于全文分析的bug处理，不用新加spec`。

> **归属（按用户指示）**：不新建 spec 编号，按 Bug 处理规则追加到本 Spec043 —— 「关于本篇提问」/ 全文分析入口属本 spec 已确认范围（`:95-96`、`Task05`；`conversationDraft()` 见 `frontend/literature-maps.js:6891-6904`）。根因代码跨到会话链路与 research intake（历史上与 Spec034 / 029-031 相关），仅在下文标注引用，**不另立 spec、不改历史 spec 状态**。

### 直接回答「目前的意图识别模块有没有对此进行区分」

**没有。** 系统里存在 3 套分类器 + 1 个服务端单篇会话绑定，但**没有任何一处把「只分析这一篇论文（RAG）」与「开放式深度研究」区分开**：

| 组件 | 职责 | 对这条消息的结果 | 是否区分单篇 RAG |
|---|---|---|---|
| `backend/app/skills/intent.py::detect_skill()`（Spec023 Task06） | 只判断用户是否**点名调用某个 Skill**（规则词边界 + LLM 3 选 1） | `SkillDecision(status='none')` | 否，且不负责研究意图；深度研究不是靠点名 Skill 触发的 |
| `backend/app/research/application/intake.py::ResearchIntakeCoordinator.classify()`（`:182-193`） | 判断是否「深度研究 / 研究报告」，返回 `explicit` / `ambiguous` / `ordinary` | **`explicit`** | 否，纯文本正则，不看会话上下文 |
| `backend/app/research/application/intake.py::classify_intake_intent()`（`:123-`） | Intake **已激活后**区分「在回答 intake 提问」vs「提问/命令」，fail-open 归 `answer` | `answer` | 否，只作用于 Intake 内部路由，**不阻止 Intake 被激活** |
| `literature_map_conversation_bindings`（`backend/app/literature_maps/domain/analysis.py:53`） | 服务端不可变绑定：`map_id` / `node_id` / `evidence_level` / `source_version` / `context` | 该会话确实有 binding | **有信息但没用上**：只在 `routes_conversations.py:1282-1320` 用于**收窄 RAG 检索范围**，完全没参与 `:2155` 的意图判定 |

### 只读复现（2026-11-06）

1. **消息来源**：全文页签点「关于本篇提问」→ `createNodeConversation()`（`frontend/literature-maps.js:6922-6955`）带 `evidence_level='full'` 创建/复用单篇会话 → `conversationDraft()` 预填可编辑草稿：`请帮我解读这篇论文。/ 标题：Graph Attention Networks / 作者：… / 年份：2017 / 请重点回答：研究问题、方法、主要结论和局限。/ 证据等级：全文索引片段依据`。截图里用户又追加了「重点告诉我它的创新，和详细告诉我它的方法，**使用RAG的模式**」，然后手动发送。
2. **误判点**（真实调用分类器，只读）：
   - `ResearchIntakeCoordinator.classify(完整消息)` → **`explicit`**；
   - 命中的是正则 `(?:帮我|请|请帮我).{0,12}(?:研究|分析).{2,}`，实际匹配片段为 **`请重点回答：研究问题、方法、主要结论和局限。`**（「请…研究」被当成「请做研究」）；
   - 同一文本 `classify_intake_intent()` → `answer`，`detect_skill()` → `none`；
   - 消息里「使用RAG的模式」「这篇论文」「证据等级：全文索引片段依据」**都不是任何负向特征**，写了也没用。
3. **触发链**：`backend/app/api/routes_conversations.py:2155` 对**每条**消息无条件 `classification = ResearchIntakeCoordinator.classify(content)` → `:2157` `get_provider("research_intake_coordinator").handle_message(conversation_id, owner_id, message_id, content)`，该签名（`:302`）**没有 conversation 上下文参数** → `handle_message()`（`:302-`）在 `active is None and classification == 'explicit'` 时 `activate_skill()` 激活 **`deep-research-orchestration`** → 创建 ResearchSession / Intake（`DEFAULT_FIELDS`: `citations=inline`、`depth=balanced`、`language=zh`、`output=markdown`、`sources=[usenix]`）→ 用户截图里「研究 Intake 收集中 / Skill: deep-research-orchestration / 引用方式 inline / 置信度 100% / 系统默认 / 无需确认」，并追问 `topic` / `objective` / `time_range`（`BLOCKING_FIELDS`）。
4. **放大因素**：`_resolve_sticky_skill()`（`routes_conversations.py:1149-`）会把 `deep-research-orchestration` 在会话内**粘住**，后续轮次仍受影响；而本该走的单篇 RAG 检索（`hybrid_search` + 文档 allowlist，`:1381-1399`）在 Intake 短路后根本没执行。
5. **回归缺口**：`tests/research/test_research_intake_intent_routing.py` 只覆盖「收齐即停」与 Intake 内部问答路由，用例全是「帮我做深度研究，研究侧信道攻击」等**显式研究**文本；`tests/` 全库无 `map_conversation_binding` × 意图判定的跨边界用例。

### 目标

「关于本篇提问」打开的单篇论文会话，无论用户在草稿里怎么写「研究 / 分析 / RAG」，都**只走普通对话 + 已收窄到这一篇的 RAG 检索**，绝不启动深度研究 Intake；普通会话里真正的深度研究请求行为不变。

### 待用户裁决（3 项）

1. **修复方向**（默认 A+B 组合）：
   - **A（结构化，推荐主修）**：在 `routes_conversations.py` 消息入口，用已有的 `_read_map_conversation_binding()`（`:117-126`）读取绑定；**当会话存在有效单篇论文 binding 时，跳过 `research_intake_coordinator` 的激活**（等价于 `intake = IntakeResult(status='ordinary')` / `classification='ordinary'`），让消息进入既有普通 RAG 链路。绑定读取失败仍按现有 fail-closed 逻辑（`:1295-1306`）处理，不静默放宽。
   - **B（文本兜底，推荐一并做）**：给 `ResearchIntakeCoordinator.classify()` 增加**负向特征**：命中「这篇论文 / 这一篇 / 基于全文 / 证据等级 / 全文索引片段 / 使用RAG / 关于本篇」等单篇解读标记时归 `ordinary`（或至少不判 `explicit`），覆盖用户把草稿粘贴到普通会话的情形；同时收紧过宽的 `(?:帮我|请).{0,12}(?:研究|分析)` 正则，避免「研究问题」「研究目标」这类名词被当作动词。
   - **C（前端）**：仅在 `conversationDraft()` 里加「仅分析这一篇，不要启动深度研究」提示语 —— 属提示词层面，脆弱，默认**不单独采用**（可作为 A/B 的辅助文案）。
   - **D（接口）**：给会话/消息增加显式 `mode=paper_rag` 字段并按 mode 路由 —— 最干净但涉及请求契约与数据模型，范围扩大，默认不做。
2. **是否允许用户在单篇会话里显式要求深度研究**（默认：**不允许**，单篇会话恒定走 RAG；若要做需给明确的产品入口，例如「以这篇为起点做深度研究」按钮，另行确认）。
3. **Sticky skill 清理**（默认：若用户此前会话已被粘上 `deep-research-orchestration`，修复后进入单篇会话时不复用该 sticky 状态；不主动批量清理历史会话数据）。

### 数据模型 / 端点 / 公开接口

默认 A+B **无新增字段、无新增端点、无表结构变更、不改 `schema_version`、不写库**；只复用已有的 `literature_map_conversation_bindings` 读取与 `ResearchIntakeCoordinator.classify()` 内部规则。若用户选 D，则本段数据模型作废并回到 spec 重新确认。

### 边界（每条对应一条验收）

1. 单篇论文会话 + 上述完整草稿（含「研究问题」「使用RAG的模式」）→ **不**产生 `research_intake` 非 ordinary 结果、不激活 `deep-research-orchestration`、不创建 ResearchSession / Intake；走 `rag_retrieval` 且检索范围仍限于该论文文档；
2. 普通会话 + 「帮我做深度研究，研究侧信道攻击」→ 行为**完全不变**（`explicit` → Intake 激活），现有 `tests/research/test_research_intake_intent_routing.py` 全通过；
3. 普通会话 + 「请帮我解读这篇论文 / 基于全文分析 / 使用RAG」→ 归 `ordinary`，不进 Intake（B 的兜底覆盖）；
4. 普通会话 + 「帮我分析一下这个领域的研究现状」等**开放式**请求 → 仍可判 `explicit`，不得被负向规则过度抑制；
5. 单篇会话的 `evidence_level='abstract'` 与 `'full'` 都不触发 Intake；`binding` 读取失败时沿用 `MAP_CONVERSATION_CONTEXT_UNAVAILABLE` fail-closed，不降级为项目级检索、不泄露其它论文；
6. 单篇会话里用户手动输入「深度研究」仍按裁决 2 的默认（不启动）；普通会话不受影响；
7. 已有 sticky `deep-research-orchestration` 的普通会话，行为不变；单篇会话不复用该状态；
8. 消息内容、草稿文案、`conversationDraft()`、`createNodeConversation()`、`evidence_level` 请求体、`POST /nodes/{id}/conversation(s)` 契约**零改动**（若选 C 才改草稿文案）；
9. 不引入新的 LLM 意图调用、不增加额外网络请求或延迟；分类器仍为纯规则、确定性、可单测；
10. 测试诚实性：不删用例、不 skip/xfail、不放宽断言；不改动已知性能基线用例。

### 明确不做

- 不改深度研究 Intake 的 `BLOCKING_FIELDS` / `DEFAULT_FIELDS` / 字段抽取 / 会话状态机 / `activate_skill()` 授权逻辑；
- 不改 `backend/app/skills/intent.py`（Skill 点名识别与本 Bug 无关）、不改 `classify_intake_intent()`（它服务于 Intake 内部路由）；
- 不改 RAG 检索链路、`hybrid_search` / allowlist / `visible_documents` / 证据等级门禁；
- 不改前端「关于本篇提问」入口、草稿可编辑性、「不自动发送」既有约定；不新增按钮或模式切换 UI；
- 不新增表/列/端点/字段、不改 `schema_version`、不做历史数据迁移或批量清理；
- 不动 Spec034 / 029-031 的状态与结论，不新建 spec 编号；不放宽已知性能基线用例。

### 产品使用步骤（确认后作为人工验收输入）

1. 打开 `http://127.0.0.1:8000/` → 文献地图 → `API E2E graph attention networks r2` → 点 `Graph Attention Networks` 节点 → 切到「全文分析」页签。
2. 点「关于本篇提问」→ **等待**跳转到单篇会话，输入框预填解读草稿，可继续追加「使用RAG的模式」等文字；**不自动发送**。
3. 点发送 → **等待**回答生成；**提示**：处理步骤里出现「知识库检索」并给出本论文片段引用，**不出现**「研究 Intake 收集中」/ `deep-research-orchestration` / 主题/目标/时间范围追问。
4. 检查回答确实只引用这一篇论文的全文片段，不出现跨项目检索或外部目录搜索。
5. 新开一个普通会话输入「帮我做深度研究，研究侧信道攻击」→ **提示**：仍正常进入深度研究 Intake，行为与改动前一致。
6. **失败恢复**：若绑定读取失败，显示既有 `MAP_CONVERSATION_CONTEXT_UNAVAILABLE` 可重试提示，不静默降级、不误进 Intake；刷新后重试可恢复。
7. **产物查看**：`docs/sdd/plans/043/artifacts/` 下的真实请求/响应、处理步骤序列（SSE 事件）与两张截图（修复前 Intake / 修复后 RAG 回答）。

### 验证方式（确认后执行）

- **后端定向**：新增 `tests/conversations/` 或 `tests/research/` 下的跨边界回归用例（按能力命名、不含 spec/task 编号），覆盖边界 1–7、9；用真实 `_read_map_conversation_binding` + 真实 `ResearchIntakeCoordinator`（可用现有 fixture 风格），**不 mock 掉被修复的判定函数冒充通过**；现有 `tests/research/test_research_intake_intent_routing.py` 全绿是硬门槛。
- **真实 API 成功案例**：当前部署版本用「关于本篇提问」真实创建单篇全文会话、发送完整草稿，落盘请求、响应、`conversation_id` / `node_id` / `evidence_level`、SSE 处理步骤序列（应含 `rag_retrieval`、不含 `research_intake` 激活）、最终状态与产物路径。
- **回归**：`tests/conversations`、`tests/research`、`tests/literature_maps`（现 `240 passed`）；`.venv/bin/python -m pytest tests/frontend -q --deselect <已知基线>`（现 `419 passed / 1 deselected`）；`node --check`、`scripts/check_test_layout.py`、按项目配置跑 `ruff`。
- **部署**：后端改动需按 `deploy/README.md` 重启并验证 `/api/health` 200、首页 200、静态资源版本 200；真实浏览器走一遍产品步骤 1–5。
- **门禁**：需求/技术评审 → 后端一次分派（若选 C 再前端一次） → `backend-reviewer` / `backend-tester` → `tester` 跨端验收 → 架构师签字 → 台账 / 变更日志 / 复盘 / 本地 commit。

### 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 复现定位、修订本段、落地校验、验收签字 |
| 文档更新 `doc-updater` | 不适用（产品使用步骤已在本段给出） | — | — | — |
| 评审／合并 `architect` | 按 `.codebuddy/agents/architect.md` 的 `model` 字段 | 32k | `Task(architect)` | 增量需求／技术评审、合并裁决 |
| 后端开发 `backend-dev` | 按 `.codebuddy/agents/backend-dev.md` 的 `model` 字段 | 32k | `Task(backend-dev)` | 会话入口绑定短路、分类器负向规则、定向测试 |
| 前端开发 `frontend-dev` | 不适用（默认 A+B 零前端改动；若选 C 再启用） | — | — | — |
| 测试 `tester` | 按 `.codebuddy/agents/tester.md` 的 `model` 字段 | 32k | `Task(tester)` | 跨端验收总控 |

> 默认 A+B 是**纯后端改动**，按单端原则只派 `backend-dev` + `backend-reviewer` / `backend-tester`，**不跑前端 pytest 新用例**（前端既有回归仍可作为收口核对）。若用户选 C，则按前后端分派原则拆成两次分派。

---

## 2026-11-06 用户裁决与本批次冻结范围（七项汇总；已被文末「二次裁决与最终冻结范围」段取代）

**裁决来源（2026-11-06 用户原话）**：`第 2 项选 C 是破坏性方向：会删掉你此前明确保留、刚验收收口的节点分组功能；若你只是觉得「标签」这个词没用。那你把这个功能做出来吧。` / `其他按照默认。` / `关于7我先考虑一下，之后再告诉你我的决定。`

| # | 项目 | 用户裁决 | 裁决后状态 / 冻结默认值 |
|---|---|---|---|
| 1 | 次级按钮视觉可用性（`:1044` 段） | **按默认** | **已确认**：A（地图视图内）、沿用顶部按钮色板、`9→11px` |
| 2 | 地图标签（`:1136` 段） | **C 明确排除**；要求「把这个功能做出来」 | **待重新确认**：范围扩大，且与 `:619`、`:623-627` 两次历史裁决冲突，暂停实施 |
| 3 | 详情面板高度对齐（`:1174` 段） | **按默认** | **已确认**：右列跟随 grid 行高、与中列同底 |
| 4 | 「可用」筛选结果为空 Bug（`:1247` 段） | **按默认** | **已确认**：A 筛选匹配徽标可用集合（`ready` 或 `partial` 且有节点），「部分完成」仍按原始 status |
| 5 | 「跳过 2」无原因 Bug（`:1336` 段） | **按默认** | **已确认**：A 后端投影补 `skipped_items` + 前端列明论文与中文原因，只提示不加按钮 |
| 6 | 「主题相似」勾选无感（`:1431` 段） | **按默认** | **已确认**：A 加说明 + 提升虚线可见度 + 切换状态提示，不删图层 |
| 7 | 单篇全文 RAG 被误判为深度研究 Bug（`:1515` 段） | **用户暂缓**：「先考虑一下，之后再告诉你我的决定」 | **保持待确认**，不进入本批次实施 |

> 各修订段状态行中的「待确认」为产出时快照，**以本表为裁决后唯一有效状态**；逐段状态行在实施启动时同步回写。

### 无歧义、立即冻结的边界

1. **节点分组功能完整保留**：`literature_map_groups` 表、`/groups` API、节点 `group_id`、画布左下角 FAB / 分组浮层 / 高亮 / 归入、刚验收收口的 Spec043 分组批次及其验收结论，一律不删、不改、不重命名；选项 **C 及任何等价删除方向永久排除**。
2. 第 1 / 3 / 4 / 5 / 6 项严格按各段「默认方案」与「明确不做」执行，不因第 2 项讨论扩大范围；测试诚实性（不删用例、不 skip/xfail、不放宽断言与性能基线）不变。
3. 第 7 项仍挂 Spec043、不新建编号；在用户回复前**不动** `backend/app/api/routes_conversations.py`、`backend/app/research/application/intake.py`、草稿文案与其测试。
4. 原「七项合并为一个跨端批次」执行配置（一次 `css?v=29→30` / `js?v=43→44`、一次分端回归、一次部署验证、一次本地 commit）**暂不启动**：第 2 项范围未定、第 7 项待决，待用户补齐后一次性冻结，避免两次升版本号与两次部署。若用户要求已确认的 5 项先上线，再拆为两个批次并重新确认执行配置。
5. `:1136` 段的 A（只删 spec 作废存档文档）与 B（删 `labelModeSelect` 下拉）**均不再执行**：本项从「代码清理」转为「功能实现」方向，原 A/B/C 选项表、明确不做与验证方式保留仅供追溯，不再作为实施依据。

### 第 2 项需用户补齐的确认点（暂停实施）

1. **「这个功能」的指代**：(a) `:616-754` 曾作废的**地图级标签系统** —— 新增 `literature_map_tags` / `literature_map_tag_bindings`、6 个端点、地图列表按标签筛选、地图卡片 ⋯ 设置菜单、UI「分组」改叫「标签」；(b) 仅工具栏 `labelModeSelect`「标签显示模式」下拉对应的能力；(c) 其它（请指认界面位置）。
2. **是否推翻历史裁决**：`:619` 用户亲自澄清「节点分组功能是要保留的、不是新建地图级标签分类系统」，`:623-627` 用户回「按照 A」再次裁定该段继续作废、不建两张表、不加 6 个端点、不做「分组」改名。若选 (a)，即为第三次方向反转，且涉及新增数据模型 / 公开接口 / 用户行为，按 SDD 必须重新确认。
3. **若按 (a) 实现**：是否沿用 `:651-700` 既有设计（两套概念并存、不迁移节点分组数据、标签绑定不递增 `literature_maps.revision` 以免与 `PATCH /view` 的 409 踩踏、一次最多 20 个标签、XSS 只用 `textContent`）；其中「分组改叫标签」与刚收口的分组 UI 直接冲突，默认**不恢复**。
4. **编号归属**：`:631` 约定若判定为独立子系统则新建 `045-…` spec 并同步 `docs/sdd/plans/045/`；或继续挂 Spec043 作为修订段。
5. **批次排期**：默认等第 2 / 7 项齐了一次做；或已确认 5 项先上线、第 2 项另起批次。

> **在用户补齐第 2 项确认前，不改任何业务代码、不跑测试、不升版本号、不部署。** 本段仅为裁决留痕与范围冻结。（该暂停条件已由下方二次裁决解除。）

---

## 2026-11-06 用户二次裁决与最终冻结范围（七项全部确认，不拆分）

**用户原话**：`新建地图级标签分类系统 做的是这个， 沿用 :651-700 的既有设计，继续挂 Spec043` / `全部修了，不用拆分`。

**状态：实施中（2026-11-06）。** 用户已明确确认全部范围，本段取代上一段的待确认点与排期；上一段保留仅供追溯。

### 裁决解释

1. 第 2 项指代确认为 **(a) 地图级标签分类系统**：给「地图」打标签、用于地图列表筛选，与「论文节点分组」是两套并存概念。
2. 用户明确确认推翻 `:619` / `:623-627` 两次历史裁决，同意新建两张表与 6 个端点；方向由「删/清理」正式改为「新增能力」。
3. **沿用 `:651-700` 既有设计**，逐条冻结见下表。
4. **继续挂 Spec043**：不新建 `045` spec、不建 `plans/045/`（`:631`、`:754` 的建档约定由本段覆盖）。
5. **全部七项一次做、不拆分**：第 7 项此前「先考虑一下」由本句覆盖，按默认 **A+B** 执行；一次版本号（`css?v=29→30` / `js?v=43→44`）、一次分端回归、一次真实 API/浏览器 E2E、一次部署验证、一次本地 commit。
6. **节点分组功能仍然完整保留**（上一段冻结边界 1 不变）：`literature_map_groups` / `/groups` / `group_id` / 左下角 FAB / 浮层 / 高亮 / 归入与刚收口的验收结论零改动；C 及任何等价删除方向永久排除。

### 七项最终状态

| # | 项目 | 状态 | 冻结方案 |
|---|---|---|---|
| 1 | 次级按钮视觉可用性（`:1044`） | **已确认 / 实施中** | A（地图视图内）、沿用顶部按钮色板、`9→11px` |
| 2 | 地图级标签分类系统（本段） | **已确认 / 实施中** | 沿用 `:651-700`，见下方正式需求 |
| 3 | 详情面板高度对齐（`:1174`） | **已确认 / 实施中** | 右列跟随 grid 行高、与中列同底 |
| 4 | 「可用」筛选为空（`:1247`） | **已确认 / 实施中** | A 筛选匹配徽标可用集合，「部分完成」仍按原始 status |
| 5 | 「跳过 2」无原因（`:1336`） | **已确认 / 实施中** | A 后端补 `skipped_items` + 前端列明论文与中文原因，只提示不加按钮 |
| 6 | 「主题相似」无感（`:1431`） | **已确认 / 实施中** | A 加说明 + 提升虚线可见度 + 切换状态提示，不删图层 |
| 7 | 单篇全文 RAG 误判（`:1515`） | **已确认 / 实施中** | **A+B**：binding 短路 Intake + 分类器单篇负向特征，纯后端 |

### 「沿用 `:651-700`」的逐条冻结

| # | 冻结项 | 结论 |
|---|---|---|
| 1 | 两套概念并存、不迁移 | 节点分组的后端表 / API / `group_id` 全不动；地图标签另建，不迁移、不合并 |
| 2 | 数据模型 `:655-669` | 两张新表 + `GET /api/literature-maps` 每项 `tags` 只读派生，旧字段全保留 |
| 3 | 端点 `:671-681` | 6 个端点（标签 CRUD 4 + 地图绑定 1 + 列表派生 1），`/groups` 与 `/nodes/{id}/group` 不变 |
| 4 | 边界 `:683-691`、`:745` | 空值/重名/颜色/越权 422/绑定幂等与上限/删除解绑/三条件组合/XSS/键盘/移动端/徽标 3 个 +N |
| 5 | 明确不做 `:693-700` | 不迁移分组、不做层级/合并/拖拽/批量/导入导出、不改 status 语义与 `PATCH /view` 409、不改状态下拉与搜索框、不加依赖 |
| 6 | 产品步骤 `:702-709`、`:747` | 列表上方标签区 → 卡片 ⋯ → 设置/新建 → 卡片徽标 → 标签筛选可组合 |
| 7 | 验证 `:711-718` | 后端定向 + 前端定向 + 真实服务 E2E + 三档宽度 + 分端执行 + 人工验收材料 |
| 8 | **「分组」→「标签」UI 改名：不做** | 与刚收口的分组 UI 冲突、且用户强调保留分组功能。节点级一律仍叫「分组」，仅地图级新能力叫「标签」；`:647` / `:714` 的「23 处文案改名」验证项**作废** |
| 9 | `:720-726` 六个待确认问题 | 按默认：地图级、两套并存、标签多选 / 筛选单选可取消、列表上方不放新建表单（只在 ⋯ 菜单）、后端字段与 URL 不改名、一次性确认 |
| 10 | `:729-753` 卡片显示所属标签 | **一并纳入**（用户当初明确要求「标签添加上要在地图卡片中显示」）：独立 `.literature-map-list-tags` 行、最多 3 个 + `+N`、色点 + 名称、徽标不可点、无标签不渲染、文字固定深色 |
| 11 | `:669` 并发隔离（硬约束） | 标签绑定**不得**递增 `literature_maps.revision`，否则与 `PATCH /view` 的 409 乐观锁互相踩踏；标签自身用独立版本号 / `expected_revision` |
| 12 | `:646` DOM 契约（硬约束） | 卡片当前是 `<button data-map-id>`，⋯ 菜单必须调整 DOM 结构且**保留** `data-map-id`；点 ⋯ **不得**触发 `selectMap`；现有 `[data-map-id]` 断言与点击行为需回归 |

### 地图级标签分类系统 — 正式需求（已确认）

#### 一句话目标

给「地图」增加一套与论文节点分组并存、互不迁移的标签分类能力：可创建/编辑/删除标签、给地图绑定多个标签、在地图列表按标签筛选、在地图卡片显示所属标签；节点分组功能零回归。

#### 数据模型（新增，不改既有表）

| 实体 | 字段 | 类型 | 约束 |
|---|---|---|---|
| `literature_map_tags` | `tag_id` | TEXT | PK |
| | `owner_id` | TEXT | 必填，按 owner 隔离 |
| | `name` | TEXT | 去空白后非空、长度 ≤ `GROUP_NAME_MAX_LENGTH`、同 owner 下唯一（大小写不敏感） |
| | `color` | TEXT | `#RRGGBB`，默认 `#8d80e6` |
| | `created_at` / `updated_at` | TEXT | RFC3339 |
| `literature_map_tag_bindings` | `map_id` | TEXT | FK `literature_maps(map_id)`，软删地图不计 |
| | `tag_id` | TEXT | FK `literature_map_tags(tag_id)`，`UNIQUE(map_id, tag_id)`，重复绑定幂等 |
| `GET /api/literature-maps` 响应项 | `tags` | array | 只读派生 `[{tag_id, name, color}]`，旧字段全部保留 |

**并发隔离**：绑定操作不递增 `literature_maps.revision`；标签自身用独立版本号 / `expected_revision` 做冲突控制。

#### 端点 / 接口

| 动作 | 输入 | 成功 | 失败 |
|---|---|---|---|
| `GET /api/literature-maps/tags` | owner 上下文 | `200 {tags:[…]}` | 401 |
| `POST /api/literature-maps/tags` | `{name, color}` | `201 {tag_id,name,color}` | 400 名称/颜色非法、409 重名 |
| `PATCH /api/literature-maps/tags/{tag_id}` | `{name?, color?}` | `200 {…}` | 400 / 404 / 409 |
| `DELETE /api/literature-maps/tags/{tag_id}` | — | `200 {deleted, unbound_maps}` | 404；解绑所有地图 |
| `PUT /api/literature-maps/{map_id}/tags` | `{tag_ids:[…]}` | `200 {tags:[…]}` | 404 / 409 / 422 含不存在或越权 tag_id |
| `GET /api/literature-maps` | owner | 每项含 `tags` | — |
| 现有 `/groups`、`PUT /nodes/{id}/group` | 不变 | — | — |

#### 边界（每条对应一条验收）

1. 空标签列表、无标签地图、空/超长/仅空白标签名、重名（同 owner 冲突、跨 owner 允许）、非法颜色。
2. 绑定不存在 / 跨 owner 的 `tag_id` 一律 422，不产生越权可见性；重复绑定幂等；一次最多 20 个。
3. 删除标签自动解绑所有地图、筛选结果与卡片徽标立即更新；已软删地图不出现在筛选结果。
4. 卡片 ⋯ 不触发选图；菜单 Enter/Esc/焦点、点击外部关闭；移动端抽屉不溢出。
5. 标签筛选与状态筛选、搜索框三者可组合；取消标签筛选恢复全部（单选、可取消）。
6. 标签操作不改变 `literature_maps.revision`、不触发视图保存 409；节点分组（颜色/重命名/删除/归入）零回归。
7. 卡片徽标：有 N 个渲染 N 个、>3 个显示 `+N`（`title` 列全部）、空数组不渲染、删除后消失、超长名截断且保留 `title`、不与 ⋯ 重叠、键盘焦点顺序正确、三档宽度不溢出。
8. XSS：标签名只用 `textContent` / `setAttribute`，禁止 `innerHTML`；徽标文字固定深色，不拿标签色当文字色。

#### 明确不做

- 不把「分组」改叫「标签」，不改 `literature_map_groups` / `/groups` / `group_id` / 后端字段名与 URL，不迁移分组数据。
- 不做标签层级/嵌套、合并、拖拽排序、批量给多张地图打标签、标签导入导出；卡片徽标不可点。
- 不改地图创建/删除/图谱/详情/Task11 逻辑，不改后端 `status` 语义，不改 `PATCH /view` 与 409 策略。
- 不改现有「按状态筛选」下拉与搜索框；列表上方不另放新建标签表单。
- 不新增前端框架或第三方依赖，不改其它视图；不新建 `045` spec 与 `plans/045/`。
- 不删用例、不 skip/xfail、不放宽断言与性能基线。

#### 产品使用步骤（人工验收输入）

1. 打开 `http://127.0.0.1:8000/` → 文献地图；**提示**：列表上方出现「标签」区（与状态筛选并列），空态不报错。
2. 在某张地图卡片右下角点 `⋯` → **等待**菜单展开 → 选「设置标签」→ **提示**：可勾选已有标签或「新建标签」。
3. 「新建标签」填名称 + 颜色 → 点创建 → **等待**成功提示；**提示**：卡片立即出现「色点 + 名称」徽标，⋯ 按钮不与徽标重叠，选图未被触发。
4. 给同一张地图再加 3 个以上标签 → **提示**：卡片只显示前 3 个 + `+N`，鼠标悬停可看全部名称。
5. 点列表上方某标签 → **等待**列表重绘；**提示**：只显示带该标签的地图，计数与预期一致；再与状态筛选/搜索组合，再点一次取消筛选恢复全部。
6. 在 ⋯ 菜单取消某标签 / 在标签区删除标签 → **等待**重绘；**提示**：卡片徽标消失、筛选结果更新、节点分组浮层与左下角 FAB 仍可用。
7. **失败恢复**：重名 → 409 提示改名；越权/不存在 `tag_id` → 422；网络失败 → 可重试且不产生半绑定；视图保存不因标签操作报 409。
8. **产物查看**：`docs/sdd/plans/043/artifacts/` 下真实请求/响应、`tag_id` / `map_id`、最终状态与三张浏览器截图（空态 / 打标签后卡片 / 标签筛选结果）。

#### 验证方式

- **后端定向**：标签 CRUD 边界、绑定幂等与上限、删除解绑、owner 隔离、`revision` 不变、列表 `tags` 派生且旧字段保留；队列 `skipped_items` 投影；单篇 binding 短路与分类器负向特征（`:1544-1599` 边界 1–10）。
- **前端定向**：DOM 契约（`data-map-id` 保留、⋯ 不触发 `selectMap`）、菜单开关与键盘、三条件组合筛选、徽标 3 个 +N、无 `innerHTML`；`node --check`、class 与 CSS 对应、`?v=N` 已升。
- **真实服务 E2E**：新建标签 → 给地图打标签 → `GET /api/literature-maps` 返回 `tags` → 浏览器点标签筛选 → 计数一致；另跑「关于本篇提问」单篇全文会话确认走 RAG 不进 Intake；落盘请求、响应、实体 ID、最终状态、产物路径。
- **回归**：`tests/literature_maps`、`tests/conversations`、`tests/research`（现 `240 passed`）；`tests/frontend`（现 `419 passed / 1 deselected`）；`node --check`、`scripts/check_test_layout.py`、`ruff`。
- **部署**：按 `deploy/README.md` 重启，验证 `/api/health` 200、首页 200、静态资源版本 200；三档宽度真实浏览器走产品步骤 1–7。
- **门禁**：Gate 2 增量需求/技术评审 → 后端一次分派 + 前端一次分派 → 分端评审与回归 → `tester` 跨端验收 → 架构师签字 → 台账/变更日志/复盘/本地 commit。

#### 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 修订本段、冻结范围、落地校验、验收签字 |
| 文档更新 `doc-updater` | 不适用（产品使用步骤已在本段给出，含等待/提示/失败恢复/产物路径） | — | — | — |
| 评审／合并 `architect` | `Deepseek-V4.1-Flash` | 32k | `Task(architect)` | 增量需求／技术评审、验收签字、合并裁决 |
| 后端开发 `backend-dev` | `Deepseek-V4.1-Flash` | 32k | `Task(backend-dev)` | 标签存储与 6 端点、队列投影、Intake 短路与分类器、后端定向测试 |
| 前端开发 `frontend-dev` | `Deepseek-V4.1-Flash` | 32k | `Task(frontend-dev)` | 标签区／⋯ 菜单／卡片徽标 + 第 1/3/4/5/6 项前端修复 |
| 测试 `tester` | `Deepseek-V4.1-Flash` | 32k | `Task(tester)` | 跨端验收总控 |

> 分端评审 `backend-reviewer` / `frontend-reviewer` 与分端回归 `backend-tester` / `frontend-tester` 均按 `.codebuddy/agents/<role>.md` 的 `model` 字段（同为 `Deepseek-V4.1-Flash`）；本次为跨端改动，**拆成后端一次、前端一次**两次分派，不派通吃 agent。所有角色均为线上档位，Gate 4「本地 27B 显存独占」条不适用。

#### 本批次文件边界

- **后端**：`backend/app/literature_maps/infrastructure/store.py`（两张表 + 标签 CRUD/绑定 + 队列 `skipped_items` 投影）、`backend/app/literature_maps/application/service.py`（`tags` 派生）、`backend/app/api/routes_literature_maps.py`（6 端点 + 队列透传）、`backend/app/api/routes_conversations.py`（binding 短路）、`backend/app/research/application/intake.py`（单篇负向特征）、`backend/app/literature_maps/domain/` 或 `models` 中标签实体（按现有分层）、`tests/literature_maps/`、`tests/conversations/` 或 `tests/research/`。
- **前端**：`frontend/literature-maps.js`（标签区/⋯ 菜单/徽标/筛选、可用筛选、跳过明细、主题相似说明）、`frontend/literature-maps.css`（次级按钮、详情面板高度、相似度虚线可见度、标签徽标样式）、`frontend/index.html`（`css?v=29→30`、`js?v=43→44`）、`tests/frontend/` 对应契约测试与 fixture。
- **不改**：`data/**`（除运行时必要写入）、`docs/sdd/specs/034-*`、`backend/app/skills/intent.py`、`classify_intake_intent()`、RAG 检索链路、节点分组全部实现。

#### Gate 2 强制约束清单（2026-11-06 增量评审「通过（附意见）」沉淀）

> 来源：`docs/sdd/reviews/043-requirement-review.md` / `043-tech-review.md` 的「2026-11-06 增量评审」章节，结论均为**通过（附意见）**。线上档位连续 429 后按 Gate 2 失败处置临时换本地轻档完成独立评审；主会话按 `SDD-GATE-CHECKLIST.md` §2.5 读回文件、核实代码事实后修订元数据与混入的上一批次跑偏段落（**非代写结论**），留痕见两份评审文档头部。以下为对实现有约束力的清单：

1. 节点分组零回归优先；C 及任何等价删除方向永久排除。
2. 两套术语不混用：节点级仍叫「分组」、地图级叫「标签」；不做 `:647` / `:714` 的 23 处文案改名。
3. 七项各保留独立可断言验收点（可用筛选 `0/7→5/7`、跳过明细 2 条 `MAP_ABSTRACT_UNAVAILABLE`、主题相似边数切换、详情面板三列同底、单篇会话不激活 Intake、次级按钮对比度、标签 CRUD/E2E），不得用「整体通过」代替逐项判定。
4. 第 7 项按 A+B，且普通会话显式深度研究、开放式请求行为不变（`:1564-1569` 边界 2/4）。
5. 标签 CRUD / 绑定 6 端点复用现有 owner-scoped 鉴权，不扩权限面；删除解绑原子；绑定幂等用 `UNIQUE(map_id, tag_id)`。
6. 标签绑定**不得**递增 `literature_maps.revision`（`store.py:639,645` 为递增点），冲突控制用独立版本号 / `expected_revision`，避免与 `PATCH /view` 409 踩踏。
7. ⋯ 菜单保留 `data-map-id`、不触发 `selectMap`（`literature-maps.js:1845,2487`）；键盘 / 点击外部关闭；徽标截断保留 `title`、不与 ⋯ 重叠；禁 `innerHTML`。
8. A+B 分类器保持纯规则、确定性、可单测；binding 读取失败 fail-closed（`MAP_CONVERSATION_CONTEXT_UNAVAILABLE`），不泄露其它论文；单篇会话不复用 sticky。
9. `GET /api/literature-maps` 只返回 owner-scoped + `tags` 只读派生，旧字段全保留、GET 不写库；`skipped_items` 仅为投影新增字段，导出 v2 契约不变。
10. **版本号双点同步（P0）**：`frontend/index.html:9,805` 与 `tests/frontend/fixtures/literature_map_component.html:8,1126` 同步 `29/43 → 30/44`；既有契约测试硬编码断言，漏改即全红。
11. 人工验收输入含逐步点击 / 点击后提示 / 等待条件 / 失败恢复 / 产物路径；交付前人工验收准备度 ≥90%（十项至少九项），无 P0/P1、无 API E2E 失败。

> **分派通道事实（收口时需复核）**：Gate 2 期间线上档位 `Deepseek-V4.1-Flash` 连续 429，本地 `qwen3.8:27b-mlx` 一次 `No result found`，最终以 `qwen3.5:9b` 完成评审；临时档位已在任务结束还原。后续实现分派若再次受阻，按 Gate 4 失败处置（重试 → 换档 → 记录阻塞停下），**不得由主会话代写含代码文件的实现**。

#### 实现阶段阻塞记录（2026-11-06，Gate 4 未进入）

**状态：实施中（阻塞）**，spec 不转「已完成」；按 `AGENTS.md` 强制流程第 6 条保持 `实施中` 并记录阻塞。

Gate 4 含 `.py` / `.js` / `.html` / `.css` 的实现，按门禁硬规则**必须由 `backend-dev` / `frontend-dev` 子代理承担，主会话不得代行**（代行仅允许纯文档/配置/评审文档）。本轮实现分派实测：

| 尝试 | 档位 | 任务 | 结果 |
|---|---|---|---|
| 1 | `Deepseek-V4.1-Flash`（线上） | BE-1 标签数据层 | `429 Too Many Requests` |
| 2 | `qwen3.8:27b-mlx`（本地） | BE-1a 缩小版 | 19 次工具调用 / 270s，上下文 Token 达上限；`git diff --stat -- backend/ tests/` 为空、无测试文件、无日志 |
| 3 | `qwen3.8:27b-mlx`（本地） | BE-1b 极小上下文（主会话喂结构事实、禁止读 5005 行 `store.py` 全文、改为回传片段） | 17 次工具调用 / 292s，再次上下文超限，零落盘 |

- 两次本地 27B 均因自动加载 4 份 SKILL.md 叠加 `store.py` 相关片段累计超出 32k 上下文，在读取/核对阶段即停止；`ollama ps` 为空、系统内存空闲 85%，排除 OOM；`backend/app/literature_maps/infrastructure/store.py` 实测 5005 行。
- 唯一稳定可分派的本地 `qwen3.5:9b` 已完成 Gate 2 评审，但 `MODEL_REGISTRY.md` 明确「后端含并发、事务、边界要求，必须 27B 级（9b 会产生真实并发缺陷）」，**不用于后端实现**。
- 临时档位均已还原为 `Deepseek-V4.1-Flash`（`.codebuddy/agents/architect.md`、`.codebuddy/agents/backend-dev.md`）；未改动任何模型注册表或流程纪律文档。
- **阻塞结论**：Gate 4 未启动，七项实现、分端评审/回归、真实 API 与浏览器 E2E、部署验证、验收签字与本地 commit **全部未执行**；本轮零业务代码改动、未跑测试、未升版本号、未部署。
- **解除条件（任一）**：① 线上档位 429 解除后重试 `Task(backend-dev)`；② 经用户确认后临时精简 `backend-dev.md` 的 `skills` 白名单以降低 27B 上下文占用再试；③ 用户提供其它可用档位。**任何情况下都不得由主会话代写含代码文件的实现**，也不得放宽测试断言或跳过门禁来冒充完成。

---

## 2026-11-07 收口记录（七项合并批次）

**状态：已完成。** 用户 2026-11-07 授权子代理临时使用 `hy3`（0.00 倍率）后，上述阻塞解除；按强制流程第 6 条由 Agent 实际重启服务并完成运行时验证后再转 `已完成`。临时档位仅改 `.codebuddy/agents/<role>.md` 的 `model` 字段，**收口前已全部还原**，未写入流程纪律文档或提交信息。

### 解除阻塞与实现清单

- 后端 `backend-dev`：BE-1 标签存储层 + 队列 `skipped_items` 投影；BE-2 6 端点 + 列表 `tags` 派生；BE-2b 标签 CRUD 的 404/422 契约修正；BE-3 第 7 项 A+B（单篇会话短路 Intake + 分类器单篇负向特征）。
- 前端 `frontend-dev`：FE-1a 标签区／⋯ 菜单／卡片徽标／标签筛选；FE-1b 五项 UX/Bug 修复 + `css?v=29→30` / `js?v=43→44` 双点同步 + 6 个既有测试断言同步；FE-1c 详情面板 grid 回归修复（`min-height:0` + `flex:1 1 0` + `overflow:auto`）。
- 含 `.py` / `.js` / `.html` / `.css` 的实现**全部由分派子代理完成**，主模型代行仅限纯文档。

### 评审记录（本批次，三份结论齐备）

- 需求评审：[043-requirement-review.md](../reviews/043-requirement-review.md)「2026-11-06 增量需求评审」→ **通过（附意见）**（独立 `architect` 分派；主会话落地校验修订留痕）。
- 技术评审：[043-tech-review.md](../reviews/043-tech-review.md)「2026-11-06 增量技术评审」→ **通过（附意见）**，11 条强制约束已沉淀为本 spec「Gate 2 强制约束清单」。
- 前端代码评审：[043-map-tags-batch-frontend-review.md](../reviews/043-map-tags-batch-frontend-review.md) → **GO**（独立 `frontend-reviewer`；主会话补注元数据与依据，结论不变）。
- 后端代码评审：[043-map-tags-batch-backend-review.md](../reviews/043-map-tags-batch-backend-review.md) → **GO（主模型代行，非独立评审）**，原因：`hy3` 评审分派 429 + 本地轻档零落盘；报告头部／本段／台账三处留痕。
- 验收评审：[043-acceptance-review.md](../reviews/043-acceptance-review.md) → **通过，准备度 10/10**，签字栏已填并注明「主模型代行（原因：分派通道失败）」，符合 Gate 5「留空不得转已完成」。

### 验证与部署（真实执行）

| 项 | 命令 / 结果 |
|---|---|
| 后端回归 | `pytest tests/literature_maps tests/research/test_single_paper_rag_intent_routing.py tests/research/test_research_intake_intent_routing.py -q` → exit 0，**306 passed** |
| 前端回归 | `pytest tests/frontend -q` → exit 0，**427 passed** |
| 静态检查 | `node --check frontend/literature-maps.js` exit 0；`py_compile` 5 个后端改动文件 exit 0；`innerHTML` 计数 0 |
| 真实 API E2E | `docs/sdd/plans/043/artifacts/20261107-map-tags-live-e2e.json` → 8 项全绿；队列 `skipped_items` 2 条带原因 |
| 真实浏览器 E2E | `20261107-browser-live-e2e.json` + `-supplement.json` → 标签创建→徽标→筛选 7→1→7、「可用」筛选 **5 张**（修复前恒 0）、三列 bottom `[1020,1020,1020]`、详情内部滚动、「跳过项」+「缺少摘要」可见；5 张截图 |
| 部署验证 | `./deploy/stop.sh` + `PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh -d` → 新 PID 29829；`health=200`、`home=200`、`css?v=30=200`、`js?v=44=200`；`GET /api/literature-maps/tags` 200 证明新后端已加载 |

**P0=0、P1=0、API E2E 失败=0、阻塞=0**；4 个 P2 观察项（第 1/6 项像素级与浏览器计数、binding 异常提示、第 7 项 LLM 全链路 E2E）如实记录在验收报告，未冒充完成。

### 人工验收步骤（交付）

1. 打开 `http://127.0.0.1:8000/` → 点左侧「文献地图」；**等待**地图列表出现 7 张卡片，列表上方有「标签」区（空态不报错）。
2. 点某张卡片右下角 `⋯` → **等待**菜单展开 → 填「新标签名称」→ 点「创建并绑定」；**提示**：卡片出现色点 + 名称徽标，选图未被触发。
3. 点列表上方该标签 → **等待**列表重绘 → **提示**只剩 1 张；再点一次恢复 7 张；与状态筛选「可用」组合 → **提示**显示 5 张。
4. 打开有跳过项的地图 → **提示**队列面板显示「跳过项 2 个」与「缺少摘要，不能生成摘要级分析；请先获取摘要。」。
5. 选中任一节点 → **提示**详情面板与左/中列同底、内容在面板内滚动；勾选/取消「主题相似」→ **提示**显示连线数量变化。
6. **失败恢复**：重名 → 409 提示改名；越权/不存在 `tag_id` → 422；网络失败可重试且不留半绑定；标签操作不触发视图保存 409。
7. **产物查看**：`docs/sdd/plans/043/artifacts/` 下 3 个 JSON 与 5 张截图；评审文档在 `docs/sdd/reviews/043-*`；复盘在 `docs/sdd/retro/2026-11-07-map-tags-batch-retro.md`。

> 服务打开地址 **http://127.0.0.1:8000/**（端口 8000，已验证 health 与首页 200）；如需重启：`PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh -d`。仅本地提交，不 push、不合 main。

### 2026-11-07 证据补强（追加，状态维持「已完成」）

用户「继续任务」后对当前部署版本补做真实验证，覆盖上表与验收报告中的观察项表述（原文保留追溯）：

1. **第 7 项自然语言主路径真实 API E2E 通过**：真实全文节点 `21041260…`（Graph Attention Networks）→ 创建 `evidence_level=full` 会话 `e16387…` → 用用户截图原文草稿发消息 → 服务端 `POST /api/conversations/{id}/messages 200 OK`，`assistant status=completed`、2098 字符回答；`GET /api/messages/{id}/processing-steps` 为 `memory_recall → system_rule → rag_retrieval（5 条证据）→ generation`，**零 `research_intake` / `deep-research-orchestration` 步骤**，`research_session_id` 全 null。产物 `docs/sdd/plans/043/artifacts/20261107-single-paper-rag-live-e2e.json`。客户端因 OTel 导出到未启动的 3000 端口超时，但服务端 200 OK 与完整持久化可核，不冒充 mock。
2. **P2 核销**：分组浮层次级按钮 `11px` / `rgb(81,69,184)` / 白底 / 1440 与 760 下均 `44px`；主题相似 `5→0→5` 条 sim 边 +「已隐藏/已显示 5 条主题相似连线」；binding 失败有 `test_binding_read_failure_is_fail_closed`（`:115`）与下游 `binding_lookup_failed` 分支（未做破坏性真实触发）。产物 `20261107-browser-p2-corrected.json`。
3. **新增如实记录（不扩大范围）**：760px 下本批次新增 `⋯` 按钮 22px 触摸目标偏小；spec 第 1 项 44px 仅约束分组浮层次级按钮且已达标，修改 `⋯` 会影响卡片徽标布局与既有断言，属范围变化，本轮不改、待用户裁决。
4. 验收结论「通过」、准备度 10/10、P0=0 / P1=0 不变；本轮**未改业务代码、未重新部署**，仅追加证据文档与本地提交。

---

## 2026-11-07 卡片设置列表与设置标签面板缩小（已确认，实施中）

**状态：已完成（2026-11-07 随下一段「选项 C 裁决」一并收口；一级条目集合按 C 的 3 项执行）。** 用户原话：`设置标签只是卡片设置里的其中一个功能，弹出的是设置列表，还有设置标签的框太大了，缩小点`。按 Bug／改动处理规则挂到已有 Spec043，**不新建编号**。本段最初仅为只读调查与待确认修订；用户 `直接开工` 后已按下一段「选项 C 裁决」的冻结范围实施完毕并收口，详见文末「2026-11-07 卡片设置列表收口记录」。

### 只读核实结论（现状）

- **触发**：`frontend/literature-maps.js:1873-1883`，卡片 `<div role="button" data-map-id>` 右下角 `⋯` 按钮，`aria-label="设置标签：{标题}"`、`aria-haspopup="menu"`；点击 `stopPropagation()` 后调 `openTagMenu()`。
- **没有「设置列表」层级**：`openTagMenu()`（`:2063-2136`）直接创建 `div.literature-map-card-menu[role=menu]`，标题写死「设置标签」（`:2071`），随后依次追加标签勾选列表（`:2074`）、新建标签表单（`:2104`）、保存按钮（`:2124`）。即 **`⋯` 一步到位弹标签表单**，设置标签是唯一功能且占据整个面板，与用户期望「设置列表里的一项」不符。
- **面板尺寸（真实 Chromium 1440×900，只读测量）**：`260×141px`；CSS `frontend/literature-maps.css:506` 为 `width:260px; max-width:280px; padding:10px; gap:8px; font-size:10px; position:fixed; z-index:1090`。内部实测：标题 16px、选项区 0px（当前无标签）、新建表单 44px、保存按钮 35px；选项区 `:508` `max-height:180px`，色块 `:516` `28×28px`，表单输入 `padding:6px 7px`。有 N 个标签时高度随行累加，视觉更占面积。
- **760px 视口**：本次只读测量因导航元素在视口外未完成（如实记录，未冒充已测）；但面板 `width:260px` 为固定值，在 760 宽下占约 34%，相对占比更大，需一并收窄并加 `calc(100vw - 32px)` 上限。
- **现有可复用的「设置项」盘点**：卡片上目前**只有** `设置标签` 一个动作；`导出 JSON`（`:1164`）、`导出 PNG`（`:1169`）位于顶部工具栏而非卡片；代码中**没有**「重命名地图 / 删除地图」的卡片实现（grep 无命中）。因此一级列表要放哪些项，属于需要用户裁决的范围问题，见下。
- **DOM 契约不变项**：`data-map-id` 保留、⋯ 不触发 `selectMap`、菜单 Esc／点击外部关闭、焦点顺序、移动端不溢出（Gate 2 强制约束第 7 条）。

### 一句话目标

把 `⋯` 改为**两级卡片设置**：一级是紧凑的「设置列表」，「设置标签」只是其中一项；点击后才出现明显更小的「设置标签」面板。不改任何标签数据、接口与既有能力。

### 数据模型 / 接口

**无变更**：不动 `literature_map_tags` / `literature_map_tag_bindings`、6 个端点、列表 `tags` 派生、队列投影、会话 binding 与 Intake 分类器；不改 `schema_version`、不改导出契约。纯前端 UI 重构。

### 方案（默认 A，逐项列出以便一次裁决）

**① 一级「设置列表」**
- `⋯` → 弹出紧凑菜单（`role=menu`），标题或首行为「卡片设置」，条目由数组驱动便于以后扩展；`aria-label` 改为 `卡片设置：{标题}`。
- 条目点击后**切换到二级面板**（同一浮层内替换内容，不叠第二层），二级顶部有「← 返回」；Esc 从二级退回一级、再按 Esc 关闭；点击外部直接关闭；切换地图时清理两级状态。
- **默认条目集合**：仅 `设置标签` 一项（不新增功能）；候选项见「待用户裁决」第 1 条。

**② 二级「设置标签」面板缩小（默认幅度：适中）**

| 部位 | 现状 | 默认目标 |
|---|---|---|
| 面板宽 | `260px` / `max 280px` | `200px`，`max-width: min(200px, calc(100vw - 32px))` |
| padding / gap / 圆角 | `10px` / `8px` / `10px` | `8px` / `6px` / `8px` |
| 标题 | 16px 行 | 保留 11px 字号，去掉额外间距 |
| 选项区上限 | `max-height:180px` | `140px`，行高约 26px，更多时内部滚动 |
| 新建表单行 | 44px（色块 28×28、输入 `padding:6px 7px`） | ≤32px（色块 22×22、输入 `padding:4px 6px`），三列仍保持 |
| 保存按钮 | 35px | ≤28px |
| 空态整体高 | **141px** | **≤105px**（目标） |

**③ 一级列表自身尺寸**：宽 `min(160px, calc(100vw - 32px))`、`padding:6px`、条目 `min-height:32px`、`font-size:11px`、条目 `gap:2px`；不与卡片徽标／⋯ 重叠，`position:fixed` 定位沿用 `positionTagMenu()`。

### 边界（每条对应一条验收）

1. 点 `⋯` 先出现「设置列表」，**不**直接出现标签表单；点「设置标签」才出现二级；「← 返回」可回到一级。
2. 二级面板 1440×900 实测宽 ≤200px、空态高 ≤105px；760px 下不溢出视口、不遮挡卡片徽标。
3. 既有能力零回归：标签勾选／保存、新建并绑定、重命名、删除、标签筛选、卡片徽标、错误提示（409/422/网络失败可重试）全部可用；`data-map-id` 保留、⋯ 不触发 `selectMap`。
4. 键盘与关闭：Enter/Space 打开、Esc 二级→一级→关闭、焦点在两级间正确迁移、点击外部关闭、切换地图清理状态。
5. XSS：标签名仍只用 `textContent` / `setAttribute`，`innerHTML` 计数保持 0；颜色只用于色点 CSS 变量。
6. 不改后端、不改 `revision`、不触发视图保存 409；标签筛选态仍不写库／不进导出。
7. 版本号双点同步：`frontend/index.html:9,805` 与 `tests/frontend/fixtures/literature_map_component.html:8,1127` 同步 `css?v=30→31`、`js?v=44→45`，并同步 `tests/frontend/` 全部硬编码版本断言。
8. 测试诚实性：不删用例、不 skip/xfail、不放宽断言；`test_frontend_map_tags_ui.py` 的既有契约需按两级结构**改写**而非删除。

### 明确不做

- 不新增地图级业务能力（重命名／删除地图、批量操作、导入导出新逻辑）、不新增后端端点／表／字段。**（本条已被下一段「选项 C 裁决」覆盖：用户明确要求把重命名／删除地图做进来；但仍不新增端点／表／字段，只复用既有能力 + 1 行绑定清理。）**
- 不把节点分组相关 UI 或术语改名为「标签」；不动 `state.labelMode` / `labelModeSelect` / 视图保存 `label_mode`。
- 不改标签筛选区、卡片徽标视觉、次级按钮、详情面板高度、主题相似图层等其余六项已收口内容。
- 不新增前端框架／第三方依赖；不改其它视图。
- 不新建 spec 编号、不建 `plans/045/`。

### 产品使用步骤（人工验收输入）

1. 打开 `http://127.0.0.1:8000/` → 文献地图；**等待** 7 张卡片出现。
2. 点某卡片右下角 `⋯` → **提示**：出现紧凑「卡片设置」列表（不是标签表单），选图未被触发。
3. 点「设置标签」→ **提示**：出现明显更小的标签面板，含返回箭头、标签勾选、新建表单、保存。
4. 勾选／新建／保存 → **等待**成功提示；**提示**：卡片徽标与上方标签筛选同步更新。
5. 点「← 返回」→ **提示**回到设置列表；按 Esc → **提示**列表关闭；点卡片外部 → 关闭。
6. 760px 视口重复步骤 2–3 → **提示**面板不溢出、不遮挡徽标、条目可点。
7. **失败恢复**：重名 409 / 越权 422 / 网络失败均有可读中文提示且可重试；中途按 Esc 或切换地图不产生半绑定。
8. **产物查看**：`docs/sdd/plans/043/artifacts/` 下两级菜单截图、尺寸实测 JSON，以及 `tests/frontend/` 定向测试输出。

### 验证方式

- 前端定向：`node --check frontend/literature-maps.js`；`pytest tests/frontend/test_frontend_map_tags_ui.py -q`；`pytest tests/frontend -q` 全绿（当前基线 427 passed）。
- 真实浏览器：1440×900 与 760×900 两档量 `menu_box`（宽／高）并落盘；走产品步骤 1–7；截图空态一级／二级与有标签态。
- 静态核对：class↔CSS 对应、`?v=N` 双点同步、`innerHTML` 计数 0、`data-map-id` 保留、`stopPropagation` 存在。
- 单端原则：本项为**纯前端改动**，只派 `frontend-dev` + `frontend-tester`，**不跑后端 pytest**、不改后端文件。
- 收口：需求／技术增量评审 → `frontend-dev` 实现 → `frontend-reviewer` 复审 → `frontend-tester` 回归 → 真实浏览器 E2E → 部署验证（`health` / 首页 / 静态资源 `?v=31/45` 200）→ 验收签字 → 台账／复盘／本地 commit。

### 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 本段编写、范围冻结、落地校验、验收签字 |
| 文档更新 `doc-updater` | 不适用（产品使用步骤已在本段给出） | — | — | — |
| 评审／合并 `architect` | `Deepseek-V4.1-Flash` | 32k | `Task(architect)` | 增量需求／技术评审、合并裁决 |
| 前端开发 `frontend-dev` | `Deepseek-V4.1-Flash` | 32k | `Task(frontend-dev)` | 两级菜单 + 面板尺寸 + 版本号双点同步 + 定向测试 |
| 前端回归 `frontend-tester` | `Deepseek-V4.1-Flash` | 32k | `Task(frontend-tester)` | 前端契约／静态／真实浏览器回归 |
| 后端开发 | 不适用（纯前端，无后端改动） | — | — | — |

### 待用户裁决（默认值可直接回复「按默认」）

1. **一级设置列表还放哪些项**（最关键）：默认 **A｜只放「设置标签」一项**（只做层级重构、不新增能力，结构数组化便于扩展）；B｜把顶部工具栏已有的「导出 JSON」「导出 PNG」也收进列表（复用 `:1164/:1169` 现有函数、不新增能力，但改变入口位置，属用户行为变化）；C｜另加「重命名地图」「删除地图」等新能力（需新增接口／范围扩大，默认不做）。
2. **缩小幅度**：默认 **适中**（宽 260→200、空态高 141→≤105）；可选「保守」（宽 →224、仅压缩 padding/gap）或「更紧凑」（宽 →180、保存按钮并入表单行）。
3. **二级面板呈现**：默认 **同一浮层内替换 + 「← 返回」**；可选独立二级浮层（层级更明确但占屏）。
4. **一级列表只有一项时是否仍显示标题「卡片设置」**：默认 **显示**（明确层级）。
5. **批次组织**：默认**单独一个纯前端小批次**（一次 `css?v=30→31` / `js?v=44→45`、一次前端回归、一次部署验证、一次本地 commit），不并入已收口的七项批次。

> **原约束（2026-11-07 已解除）**：在用户明确确认前，不改任何业务代码、不跑测试、不升版本号、不部署。用户已回复 `直接开工` 明确确认，按冻结范围实施。

---

## 2026-11-07 选项 C 裁决：设置列表加入重命名／删除地图（范围扩大，已确认，实施中）

**状态：已完成（2026-11-07；用户「直接开工」＝按全部默认值执行，Gate 5 验收通过 16/16、architect 签字、合并裁决 APPROVE，部署验证通过）。** 用户原话：`那你把新增重命名/删除地图 作进来吧` —— 上一段待裁决第 1 条选 **C**；其余 4 项用户未另行指定，**沿用上一段默认值**（适中缩小、同浮层替换 + 「← 返回」、显示「卡片设置」标题、单独小批次）。本段此前仅只读调查；因新增破坏性操作与一处跨端接缝，按 SDD 规则 5 更新 spec 后再次请求确认，用户于 2026-11-07 回复 `直接开工` 明确确认。

### 用户确认与冻结范围（2026-11-07）

用户 `直接开工` 视为「按这个执行」的等价确认，本段下方「需再次确认的决策点」6 项默认值**全部冻结为实施依据**，不再另行确认：二级删除确认、删除选中地图后自动切第一张、一级列表仅 3 项不含导出、760px `⋯` 放大到 44px、接受 1 行后端绑定清理、其余 4 项沿用上一段默认。实施严格限于本段「边界」8 条与「明确不做」5 条；范围再扩大须停下修订 spec 并重新确认。

### 只读核实：C 不需要新增后端能力

| 事实 | 依据 |
|---|---|
| 重命名端点已存在 | `PATCH /api/literature-maps/{map_id}`（`routes_literature_maps.py:484`），请求体 `MapPatchRequest{expected_revision, name?, project_id?}`（`:36-41`），走 `service.update_map` → `store.update_map_details`（`store.py:650`） |
| 删除端点已存在 | `DELETE /api/literature-maps/{map_id}`（`:497`，`204`），走 `store.delete_map`（`store.py:708`） |
| 前端零调用 | `grep -n 'renameMap\|deleteMap\|删除地图\|PATCH.*literature-maps' frontend/literature-maps.js` 零命中；卡片上目前只有「设置标签」 |
| revision 可直接取 | `LiteratureMap.to_dict()` 含 `revision`（`domain/models.py:85`），列表 `GET ""` 用 `**item.to_dict()` 构造，故卡片 `map` 对象自带 `revision`，无需额外 GET；`GET /{map_id}`（`:471`）亦可用 |
| 乐观锁契约 | `update_map_details` 校验 `row.revision != expected_revision` → `ValueError("revision conflict")`（`store.py:656`），`_error()` 归入 409 冲突集合（`routes_literature_maps.py:323`）；成功后 `revision+1` |
| 删除语义 | **软删**：`UPDATE literature_maps SET deleted_at=?, status='stopped'` + 级联清 events/checkpoints/previews/analyses/jobs/edges/groups/nodes/idempotencies（`store.py:708-727`）；后端**无恢复/回收站端点** |

### 必须一并修的跨端接缝（P1，否则 C 留脏数据）

`delete_map()` 的清理清单**没有** `literature_map_tag_bindings` —— 该表是七项批次新增（`store.py:357`），只在删标签（`:1050`）、`set_map_tags`（`:1087`）、`list_map_tags`（`:1107`）被引用。删除地图后会残留孤儿绑定行，造成：
- `delete_tag` 返回的 `unbound_maps` 计数虚高；
- `list_map_tags` 对已软删地图仍返回绑定；
- 数据库长期累积无主行。

**方案**：在 `delete_map()` **同一事务内**追加一行 `DELETE FROM literature_map_tag_bindings WHERE map_id=?`（后端最小改动，1 行 + 1 个按能力命名的定向测试）。按「已确认范围内的小缺陷追加到当前 Task」处理，不新建编号。这也使本批次从「纯前端」变为**跨端**，按前后端分派原则拆成后端一次、前端一次两次分派。

### 一级「卡片设置」列表最终条目（默认 3 项）

1. **设置标签** → 二级缩小面板（沿用上一段方案：宽 200、空态 ≤105、勾选/新建/重命名/删除/保存）。
2. **重命名地图** → 小表单输入新名称，预填 `mapTitle(map)`，去空白、≤200 字符；确认后 `PATCH /{map_id}` body `{expected_revision: map.revision, name}`。
3. **删除地图** → **二次确认**（破坏性操作，默认必须）：显示地图名 + 「删除后不可恢复」提示 + 取消/删除两个按钮。

默认**不**把顶部工具栏已有的「导出 JSON」(`:1164`)、「导出 PNG」(`:1169`) 收进列表，避免再扩大入口变更。

### 边界（每条对应一条验收）

1. 点 `⋯` 出现一级列表且含上述 3 项；点「设置标签」进二级、点「← 返回」回一级；Esc 二级→一级→关闭；点击外部关闭；切换地图清理两级状态。
2. **重命名**：成功后即时更新卡片标题、当前标题栏（`:3009`）、`state.maps` 与 `state.map`（若选中），并把 `revision` 更新为返回的新值；**保留**列表筛选与选中态；409 → 中文提示「地图已在别处更新，请刷新后重试」且可重试；400/404/503 复用 `errorAction()`（`:253`）；空名称/仅空白不提交。
3. **删除**：二次确认前不发任何请求；取消不改动；确认后 `DELETE` 204 → 从 `state.maps` 移除、清 `state.map` / `state.selectedMapId` / groups / graph / 标签筛选（若筛的是被删地图）、`loadMaps()` 重取、关闭菜单、给明确状态提示；删除当前选中地图时切到列表第一张，无其它地图时显示空态；404/503 保持列表不变且可重试。
4. **绑定清理**：删除地图后 `literature_map_tag_bindings` 无该 `map_id` 的残留行；标签仍存在、其它地图绑定不受影响；`delete_tag` 的 `unbound_maps` 计数准确。
5. **不绕过乐观锁**：重命名必带 `expected_revision`；标签操作仍不递增 `revision`（Gate 2 第 6 条不变），不与 `PATCH /view` 的 409 互相踩踏。
6. **DOM/XSS 契约**：`data-map-id` 保留、⋯ 不触发 `selectMap`、地图名只用 `textContent`、`innerHTML` 计数 0、菜单不与卡片徽标重叠。
7. **版本号双点同步**：`frontend/index.html:9,805` 与 `tests/frontend/fixtures/literature_map_component.html:8,1127` 同步 `css?v=30→31`、`js?v=44→45`，并同步 `tests/frontend/` 全部硬编码版本断言。
8. **测试诚实性**：不删用例、不 skip/xfail、不放宽断言；`test_frontend_map_tags_ui.py` 按两级 + 3 项结构**改写**而非删除。

### 明确不做

- 不新增后端端点／表／字段／`schema_version`，不改 `PATCH /{map_id}` 与 `DELETE /{map_id}` 的契约与返回结构。后端改动 = 1 行绑定清理 + 1 处既有 sentinel 缺陷修复（见下文「真实 API E2E 暴露的 P0 缺陷」），两者都不改请求／响应契约。
- 不做「撤销删除」／回收站／恢复端点（后端为软删但无恢复能力，对用户按不可恢复呈现）。
- 不改地图 `topic` / `project_id` / 图谱／节点／分组／导出契约；不改标签数据模型与 6 端点；不改 Intake／会话 binding。
- 不改节点分组术语与 UI、不改标签筛选区／卡片徽标视觉、不改其余六项已收口内容。
- 不新增前端框架／第三方依赖；不新建 spec 编号。

### 产品使用步骤（人工验收输入）

1. 打开 `http://127.0.0.1:8000/` → 文献地图；**等待**卡片列表出现。
2. 点某卡片 `⋯` → **提示**出现紧凑「卡片设置」列表，含「设置标签 / 重命名地图 / 删除地图」三项，选图未被触发。
3. 点「设置标签」→ **提示**二级小面板；点「← 返回」→ 回到列表；按 Esc → 关闭。
4. 点「重命名地图」→ 改名称 → 确认 → **等待**成功提示；**提示**卡片标题与当前标题栏即时更新，筛选与选中态保留。
5. 制造 409：在另一标签页改动同一地图后重试 → **提示**「地图已在别处更新，请刷新后重试」，刷新后可重试成功。
6. 点「删除地图」→ **提示**出现含地图名的二次确认；点「取消」→ 无变化；再点并确认 → **等待**列表重绘；**提示**该地图消失、若它是当前选中则自动切到第一张。
7. 760px 视口重复步骤 2–4 → **提示**面板不溢出、条目可点、不遮挡徽标。
8. **产物查看**：`docs/sdd/plans/043/artifacts/` 下两级菜单截图（含 3 项）、尺寸实测 JSON、真实 API 重命名/409/删除请求响应与实体 ID。

### 验证方式（跨端）

- **后端定向**：`pytest tests/literature_maps -q`（基线 306 passed）；新增用例覆盖「删除地图后 `literature_map_tag_bindings` 无残留」「`unbound_maps` 计数准确」「其它地图绑定不受影响」；既有 `test_map_revision_conflicts.py` / `test_map_store.py` 全绿。
- **前端定向**：`node --check frontend/literature-maps.js`；`pytest tests/frontend -q`（基线 427 passed）；新增契约用例覆盖一级 3 项、重命名请求体含 `expected_revision`、删除二次确认（取消不发请求）、软删后列表清理与选中切换。
- **真实 API E2E**：对一张**测试地图**跑 `PATCH` 重命名 → `GET` 校验名称与 revision → 构造 409 → `DELETE` 204 → `GET /api/literature-maps` 不含该地图 → 查绑定表无残留；落盘请求、响应、实体 ID、最终状态、产物路径。
- **真实浏览器**：1440/760 两档走产品步骤 1–8，量一级列表与二级面板 `menu_box`，落盘尺寸 JSON 与截图。
- **部署**：按 `deploy/README.md` 重启 8000，验证 `health` / 首页 / `css?v=31` / `js?v=45` 均 200。
- **门禁**：Gate 2 增量需求／技术评审 → 后端一次分派 + 前端一次分派 → 分端评审与回归 → `tester` 跨端验收 → 架构师签字 → 台账／复盘／本地 commit。

### 执行配置（跨端）

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 本段编写、范围冻结、落地校验、验收签字 |
| 文档更新 `doc-updater` | 不适用（产品步骤已在本段给出） | — | — | — |
| 评审／合并 `architect` | `Deepseek-V4.1-Flash` | 32k | `Task(architect)` | 增量需求／技术评审、合并裁决 |
| 后端开发 `backend-dev` | `Deepseek-V4.1-Flash` | 32k | `Task(backend-dev)` | `delete_map` 1 行绑定清理 + 定向测试 |
| 前端开发 `frontend-dev` | `Deepseek-V4.1-Flash` | 32k | `Task(frontend-dev)` | 两级菜单 + 3 项 + 重命名/删除 + 缩小 + 版本号 + 定向测试 |
| 测试 `tester` | `Deepseek-V4.1-Flash` | 32k | `Task(tester)` | 跨端验收总控 |

> 分派通道风险：七项批次曾因线上档位 429 由用户临时授权 `hy3` 才解除，临时档位**已在收口时还原**。本次若再次 429，按 Gate 4 失败处置（重试 → 换档 → 记录阻塞停下）处理，**不得由主会话代写含代码文件的实现**。

### 已冻结的决策点（2026-11-07 用户 `直接开工` ＝ 全部按默认，不再确认）

1. **删除是否二次确认**：默认 **要**（显示地图名 + 「删除后不可恢复」）。
2. **删除当前选中地图后**：默认 **自动切到列表第一张**，无其它地图时空态。
3. **一级列表是否也放「导出 JSON / PNG」**：默认 **不放**（只 3 项）。
4. **760px 下 `⋯` 按钮 22px 是否顺手放大到 44px**：默认 **是**（同一区域、需回归徽标不重叠）；这同时核销上一批次遗留的观察项。
5. **是否接受 1 行后端绑定清理**：默认 **是**（否则删除后留孤儿数据，属 P1 接缝）。
6. 其余 4 项沿用上一段默认：**适中缩小**（宽 200 / 空态 ≤105）、**同浮层替换 + 「← 返回」**、**显示「卡片设置」标题**、**单独一个批次**。

> **原约束（2026-11-07 已解除）**：在用户明确确认前，不改任何业务代码、不跑测试、不升版本号、不部署。用户已回复 `直接开工` 明确确认，按冻结范围实施。

### Gate 2 增量评审结论与强制约束（2026-11-07）

| 评审 | 落盘文档 | 结论 |
|---|---|---|
| 需求评审 | `docs/sdd/reviews/043-card-settings-requirement-review.md` | **通过**（0 打回，附 Q-1~Q-6） |
| 技术评审 | `docs/sdd/reviews/043-card-settings-tech-review.md` | **通过**（无 P0；3 条 P1 已全部落为约束，附 T-1~T-12） |

两份文档头部四要素（评审者／角色／模型／分派方式 `Task(architect)`）齐备，判定均基于真实 `文件:行`。以下为已沉淀的强制约束摘要，**dev 回执须逐条引用**（完整理由见各评审文档第四／五节）：

- **Q-1** 两段 H2 标题与「已确认（实施中）」状态行一致 —— 已由架构师落实，dev 不改 spec。
- **Q-2** 重命名 409 必须显示「地图已在别处更新，请刷新后重试」，**不得透传**后端 `/view` 面向的「地图版本或作业状态已变化…」（`routes_literature_maps.py:326`）。
- **Q-3** 补两条失败恢复并实测：删除返回 404/503 → 列表不变、中文提示、菜单可重试；删除后列表重取失败 → 不静默，给「本地已移除但刷新失败，请点刷新」类提示。
- **Q-4 / T-10** `css?v=30→31`、`js?v=44→45` 同步范围 = 生产页 2 处 + fixture 2 处 + **7 个测试文件**（含 `test_frontend_map_header_actions_readability.py` 的 `MAP_JS_VERSION` / `MAP_CSS_VERSION` 常量须逐文件读实际写法再改）。
- **Q-5** 重命名 `trim()` 后空值或超 200 字符前端拦下、不提交（`store.py:657` 后端不会拒绝空串）。
- **Q-6 / T-1** 一级列表恰好 3 项、不含导出；后端唯一改动是 `delete_map()` 内 1 行 `DELETE FROM literature_map_tag_bindings WHERE map_id=?`（`:714` 之后、`return True` 之前，同事务、参数化），**不得**顺手清 `literature_map_conversation_bindings` 或其它表、不得新增端点／表／字段。
- **T-2/T-3** 该 DELETE 与其余 9 条同处 `with self.transaction()`；新增 3 条用例（删后无残留 / 其它地图绑定不受影响 / `unbound_maps` 计数准确），并做「移走该行→新测试失败→复原」验证；不得删／skip／放宽既有用例，跑 `pytest tests/literature_maps -q`（基线 306 passed，只增不减）。
- **T-4** 重命名后手动更新 `state.maps[i]`、`state.map`（若选中）、`refs.currentTitle`（`:3009`）、`renderCurrentMeta()`，用 `payload.map.revision` 覆盖 revision（PATCH 返回体直接带新值，**禁止**再 GET），再 `renderMapList()` + `renderTagFilterBar()`；不得依赖 `loadMaps()` 重设 `state.map`（`:2633-2636` 不会）。
- **T-5** 一级条目数组驱动、`aria-label` 改 `卡片设置：{标题}`、保留 `aria-haspopup=menu` 与 `stopPropagation()`。
- **T-6** 地图名／确认文案只用 `textContent` / `input.value` / `setAttribute`；`innerHTML` 保持 0；`data-map-id` 保留、⋯ 不触发 `selectMap`。
- **T-7（P1）** 重命名／删除发起前依次 `await flushPendingViewSave()` → `await waitForPendingViewFlush(state.selectedMapId)` → 再发请求；重命名 body 用 `state.map.revision`，避免与在途 `PATCH /view`（`saveView()` 用 `state.map.revision`）互踩。
- **T-8（P1）** 删除选中图成功后走 `selectMap(第一张)` 借 `resetMapSelectionState` 的 `++state.mapRequest` 使在途失效；无其它地图时**显式**清 `state.map/selectedMapId/graph/groups` 并给空态（不得只调 `loadMaps`）；删除未选中图仅移除 + 重绘 + `loadMaps()`；始终 `closeTagMenu()`。删除地图后**标签筛选条保留**、仅重算 `filteredMaps()`（标签本身仍存在）。
- **T-9（P1）** `test_frontend_map_tags_ui.py` 改写并新增断言、不删既有 6 例：一级 3 项字面量、二级「← 返回」、请求体含 `expected_revision` + `name`、删除二次确认断言须**非恒真**（不得用 `"confirm" in MODULE`）、删除成功后过滤与切图、`fetch(` 计数先按真实实现核对再定（不得放宽为 `>=`）、新 CSS 类须同时断言存在于 CSS 且 `#literature-maps-view` 限定。
- **T-11** 面板宽 260→200、`max-width` 用 `min(200px, calc(100vw - 32px))`、padding 10→8、gap 8→6、选项区 180→140、色块 28→22、输入 padding 6px 7px→4px 6px、保存 ≤28px；760px 触发器 22→44px 并同步 `.literature-map-list-item` `padding-right`（`css:491`）到 ≥50px 防徽标／标题重叠；空态高 ≤105px 须真实浏览器实测。
- **T-12** 若删除确认／重命名采用菜单内表单，须保证 Esc／返回／取消不残留待删状态、切换地图时清理两级状态。

**P2 登记不修**：`update_map_details()` 事务外 `get_map` 的理论竞态（`store.py:660`，改需动返回契约，越界）；软删后数据实体仍在库（无恢复端点，对用户按不可恢复呈现，验收记录写明）；`fetch(` 计数断言的历史脆弱性。

**顺序**：`backend-dev` 先（前端 E2E「删后无残留」依赖它），`frontend-dev` 后；两次分派文件无交集。

### 2026-11-07 真实 API E2E 暴露的 P0 缺陷（本批次内修复，不改契约）

- **发现**：对当前部署版本跑真实 API E2E，`POST /api/literature-maps` 建测试地图 → `PATCH /api/literature-maps/{map_id}`，body 只带 `{expected_revision, name}`（**不带 `project_id`**，正是本批次前端「重命名地图」发出的请求）→ **503 `MAP_STORAGE_UNAVAILABLE`**；同批次 GET、标签绑定、DELETE、列表均 200。首次产物 `docs/sdd/plans/043/artifacts/20261107-card-settings-live-e2e.json` 如实记录 5 个失败检查项，未冒充通过；服务端 `deploy/run.log` 有两条 PATCH 503。
- **根因（既有缺陷，非本批次引入）**：`backend/app/literature_maps/application/service.py:54` 与 `backend/app/literature_maps/infrastructure/store.py:45` **各自定义** `_UNSET = object()`，实测 `service._UNSET is store._UNSET == False`。`service.update_map()`（`:927-930`）在路由未传 `project_id` 时把 service 哨兵原样转发给 store；store `:658` 的 `project_id is _UNSET` 判定为假，于是把裸 `object()` 绑进 SQLite → `sqlite3.ProgrammingError: Error binding parameter 2: type 'object' is not supported` → `_error()` 归入 503。临时库复现：转发 service 哨兵必抛该错，省略 `project_id` 则成功（name 更新、revision 0→1）。即历史 `PATCH /{map_id}` 在「只改 name」时从未真正可用。
- **影响**：本批次「重命名地图」主路径必然失败，属 **P0**，必须在本批次内修，否则功能不可交付。
- **范围判定**：按「已确认范围内的小缺陷追加到当前 Task」处理 —— **不改变目标、数据模型、公开接口（请求体与返回结构不变）、用户行为（重命名本就应成功）**，因此不退回 `待确认`、不新建编号、不请求再次确认；仅把上文「明确不做」中「唯一后端改动是 1 行绑定清理」澄清为「1 行绑定清理 + 1 处既有 sentinel 缺陷修复」。
- **处置**：`backend-dev` 一次最小分派，只改 `service.py:927-936` 的 `update_map()`：未显式传 `project_id` 时调用 store **省略该参数**；显式传（含 `None`）时照旧转发并保留 `_validate_project()` 校验；不动 `_UNSET` 定义、不跨模块导出哨兵、不改路由与 store 的 1 行清理。新增 `tests/literature_maps/test_map_details_patch_api.py` 6 例：只带 name 的 PATCH 200 + revision +1 + `project_id` 保持（P0 回归锁）、显式 `null` 清空、未知 project 404 且不写入、旧 revision 409、不存在 404、跨 owner 404。
- **验证**：`py_compile` exit 0；三路径回归 **315 passed**（基线 309 + 6，只增不减）；诚实性验证「还原 HEAD → `1 failed`（恰为 `assert 503 == 200`）→ 复原 → 6 passed」；`check_test_layout.py` / `check_test_naming.py` 均 ok。服务重启后按原 E2E 脚本重跑，结果见同名产物 JSON。
- **门禁补充**：本次新增后端改动需由 `backend-reviewer` 做一次 P0 修复增量复审；验收报告须把「PATCH 只带 name」列为真实 API 主路径验收点。

---

## 2026-11-07 卡片设置列表收口记录

**状态：已完成。** 用户 `直接开工` 确认 6 项冻结默认值后按范围实施；Gate 5 跨端验收 **16/16 通过**、`architect` 签字、合并裁决 **APPROVE**，真实服务部署验证通过。

### 实现清单

- **前端**：`⋯` → 一级紧凑「卡片设置」列表（数组驱动、恰好 3 项，不含导出）；同浮层替换出二级「设置标签」/「重命名地图」/「删除地图」，带「← 返回」；Esc 二级→一级→关闭、外部点击关闭、切换地图清状态；重命名复用 `PATCH /{map_id}`（带 `expected_revision`，409 专属文案，成功后用返回体新 revision 同步本地状态与标题）；删除二次确认（取消零请求、确认后状态清理与自动切图、失败可重试、刷新失败专属提示）；`⋯` 22→44px（760px）且卡片 `padding-right:30→52px`；版本号 `css?v=30→31`、`js?v=44→45` 双点 + 7 个测试文件硬编码断言同步。
- **后端**：`delete_map()` 同事务追加 1 行 `DELETE FROM literature_map_tag_bindings WHERE map_id=?`（P1 孤儿绑定）；`service.update_map()` 不再把自身 `_UNSET` 哨兵转发给 store（P0：只带 name 的 PATCH 曾稳定 503）。未新增端点／表／字段，未改请求／响应契约。
- **尺寸实测**：1440×900 一级 `160×136`、二级标签面板 **`200×94.8`**（原 `260×141`，达成 ≤200 / 空态 ≤105）；760×900 触发器 `44×44`、两级面板均在视口内且触发器不遮挡卡片文本。

### 门禁与分工（真实发生）

| 门禁 | 产出 | 结论 |
|---|---|---|
| Gate 2 需求／技术 | `reviews/043-card-settings-requirement-review.md`、`043-card-settings-tech-review.md`（`Task(architect)`） | 均通过，Q-1~Q-6 / T-1~T-12 沉淀为强制约束 |
| Gate 3 用户确认 | 用户 `直接开工`；`spec-status-changelog.md` 已登记 | 已确认 |
| Gate 4 实现 | `Task(backend-dev)` ×2、`Task(frontend-dev)` ×4（跨端拆两次以上，文件无交集） | 代码与定向测试均落盘、主会话读回校验 |
| 后端评审／复审 | `reviews/043-card-settings-backend-review.md`（`Task(backend-reviewer)` + P0 增量复审） | GO（附条件：真实 API 复验通过，已核销） |
| 前端评审／复审 | `reviews/043-card-settings-frontend-review.md`（`Task(frontend-reviewer)` + 3 次 P1 复审） | GO，P1-01/02/03 全 CLOSED |
| Gate 5 验收／签字 | `reviews/043-card-settings-acceptance-review.md`（`Task(tester)` 16/16 + `architect` 签字）、`reviews/043-card-settings-merge-decision.md`（APPROVE） | 通过 |

主会话只做编排、最小增量落地校验与纯文档同步；含代码文件的改动全部由 `backend-dev` / `frontend-dev` 分派完成。

### 验证（命令 / 退出码 / 通过数量 / 阻塞项）

| 验证 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | exit 0 |
| `.venv/bin/python -m pytest tests/frontend -q` | **439 passed**，exit 0（基线 427，只增不减） |
| `.venv/bin/python -m pytest tests/literature_maps tests/research/test_single_paper_rag_intent_routing.py tests/research/test_research_intake_intent_routing.py -q` | **315 passed**，exit 0（基线 306+3，只增不减） |
| `check_test_layout.py` / `check_test_naming.py` | ok / ok，exit 0 |
| 真实 API E2E `artifacts/20261107-card-settings-live-e2e.json` | **16/16 全绿**，exit 0（首轮失败证据另存 `...-first-run-failed.json`） |
| 真实浏览器 E2E `artifacts/20261107-card-settings-browser-e2e.json` + 6 张 PNG + 可复现 `.py` | **32/32 全绿**，`page_errors=[]`，exit 0 |
| 全量回归 `artifacts/20261107-card-settings-full-regression.log` | `2 failed, 4011 passed, 2 skipped, 67 subtests passed`，**exit 1** |
| 部署运行时验证 | `/`、`/api/health`、`css?v=31`、`js?v=45`、`/api/literature-maps/tags` **5/5 = 200** |

**阻塞项**：无本批次阻塞。全量回归的 2 个失败位于 `tests/paper_discovery/`（临时目录 `paper-import-*` 未清理），用**未含本批次任何改动的 HEAD 快照**复跑同样 `2 failed / exit 1`，且本批次零文件涉及该模块 → 判定为**既有独立缺陷**，已如实登记并建议另开 Bug Spec，不写成通过、也不计入本批次失败。

### 部署与打开方式

服务由 `launchctl` 托管在 `127.0.0.1:8000`（本批次重启后 PID 39227）。打开 **http://127.0.0.1:8000/#literature-maps-view**；启动命令 `PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh -d`，停止 `./deploy/stop.sh`；当前托管标签 `com.researchagent.recovery8000`（非开机自启，见 `deploy/README.md`）。

### 人工验收步骤（可复现）

1. 打开 `http://127.0.0.1:8000/#literature-maps-view` → **等待**卡片列表出现。
2. 点某卡片右下角 `⋯` → **提示**紧凑「卡片设置」列表，含「设置标签 / 重命名地图 / 删除地图」三项，卡片未被选中。
3. 点「设置标签」→ **提示**明显更小的标签面板（200px 宽）；点「← 返回」→ 回列表；按 Esc → 关闭；点卡片外部 → 关闭。
4. 点「重命名地图」→ 改名称 → 确认 → **等待**「地图已重命名。」；**提示**卡片标题即时更新、筛选与选中态保留。
5. 制造 409：另一标签页改动同一地图后重试 → **提示**「地图已在别处更新，请刷新后重试」，刷新后可重试成功。
6. 点「删除地图」→ **提示**含地图名与「删除后不可恢复」的二次确认；点「取消」→ 无变化；再点并确认 → **等待**列表重绘；**提示**该地图消失，若它是当前选中则自动切到第一张。
7. 760px 视口先点「地图列表」展开，再重复步骤 2–4 → **提示**面板不溢出、条目可点、`⋯` 44px 不遮挡文字。
8. **失败恢复**：404/503 保留列表与菜单并可重试；刷新失败给「地图已在本地移除，但列表刷新失败，请点击刷新重新加载地图列表。」。**产物查看**：`docs/sdd/plans/043/artifacts/20261107-card-settings-*.json` / `*.png` 与 `docs/sdd/reviews/043-card-settings-*.md`。

> 步骤 1–8 已由真实 Chromium 自动化按同一路径执行（`20261107-card-settings-browser-e2e.py` 可复现），**未冒充用户人工走查**；仍建议用户实走一遍。

### 遗留项（不阻塞）

P2-01 `finalizeMapDeletion()` 里残留 `state.maps` 的隐式依赖（当前路径不可达）；P2-02 5xx 措辞已 ≥95% 消解；P2-03 视觉指标已由真实浏览器实测关闭；LOW-01 `positionTagMenu()` 清内联约束早于 class 切换（当前结果正确，属顺序脆弱点）；`tests/paper_discovery/` 2 个既有失败建议另开 Bug Spec；人工走查待用户执行。

### 引用路径

`reviews/043-card-settings-{requirement,tech,backend,frontend,acceptance}-review.md`、`reviews/043-card-settings-merge-decision.md`、`retro/2026-11-07-card-settings-retro.md`、`plans/043/artifacts/20261107-card-settings-*`、`docs/sdd/spec-status-changelog.md`（收口条目）。
