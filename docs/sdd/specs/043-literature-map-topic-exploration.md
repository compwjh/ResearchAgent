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
- 人工验收阶段 UX 缺陷复审：[043-node-style-disclosure-frontend-review.md](../reviews/043-node-style-disclosure-frontend-review.md) 与 [043-node-style-disclosure-frontend-regression.md](../reviews/043-node-style-disclosure-frontend-regression.md)（两轮独立复审通过、0 阻塞；单端回归 READY，含真实浏览器可见性与变异验证）。

## 变更日志

- 2026-11-05：用户人工验收反馈文献地图「节点样式」浮层一打开就展开，要求点击才弹出。两轮修复：①`frontend/literature-maps.js` 删除两处 `nodeStyleDisclosure.open = ...`（桌面默认展开、视口切换强制展开），`?v=37→38`；②真实浏览器复测发现仅删 `open` 不够——`literature-maps.css` 给 fieldset 显式 `display:flex` 覆盖 UA 折叠隐藏，补 `:not([open]) > .literature-map-node-style { display:none }`，CSS `?v=25→26`。新增 2 个按能力命名的测试（JS 契约 + 真实浏览器可见性）并同步全部版本号断言。`frontend-reviewer` 两轮复审通过（0 阻塞）、`frontend-tester` 两轮回归 READY（72 passed/0 failed、4 可见性用例、变异验证）；主会话浏览器复测：折叠 `display:none / 0×0`、点击展开 `flex / 416×47`、700↔1280 切换仍折叠、summary 常驻可点。主会话代行纯文档同步（评审记录、本变更日志、状态台账），无业务代码改动；实现、测试、两份评审报告同分支同提交，本地 ff 合并 main，未 push。

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
