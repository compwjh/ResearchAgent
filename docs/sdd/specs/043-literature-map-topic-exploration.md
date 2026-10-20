# Spec 043 — 交互式文献地图与自动主题探索

## 状态

**当前状态：实施中**（2026-10-19）。
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
| MapAnalysis | analysis_id、map_id、node_id、evidence_level、source_version、status、result_ref | 用户触发；摘要/全文分开；全文就绪不覆盖旧分析 |
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
| AI/会话 | POST /{map_id}/nodes/{node_id}/analyses；POST /{map_id}/nodes/{node_id}/conversations | 用户触发，返回现有异步/会话句柄与 evidence_level；项目绑定校验 |
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
- 节点短标签为作者/年份，悬浮和详情显示全标题；缺作者/年份时回退标题短标签。颜色为统一默认或人工分组，不推断学术立场。
- 详情显示真实标题、作者、年份、发表来源、摘要、原始关键词、可取得引用数及来源、下载/索引状态；缺失明确标记，不由模型填充。

### 后续 AI、会话、整理与手机

- 用户点击才分析：未取得全文只能摘要级总结/问答；下载且索引可用才提供全文级，并复用现有 RAG 和 document allowlist。
- 全文就绪提示主动重新分析；保留摘要级旧结果、依据版本及旧会话，不自动覆盖或自动消耗模型。
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
6. 后续 Task：按摘要/全文依据点击分析或问答；人工分组、PNG/JSON导出；手机通过详情抽屉完成核心操作。
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

| 编号 | 标题 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | Spec与规划文档 | 本文件 | — | 已完成（仅建档） |
| 02 | 准备与可行性门禁 | [Task02](../plans/043/task-02-validate-feasibility.md) | 01 | 已完成（Go） |
| 03 | 桌面自动建图 MVP | [Task03](../plans/043/task-03-desktop-map-mvp.md) | 02 | 阶段已完成（PASS_WITH_LIMITATIONS） |
| 04 | 扩展与恢复 | [Task04](../plans/043/task-04-expansion-recovery.md) | 03 | 阶段已完成（PASS_WITH_LIMITATIONS） |
| 05 | AI分析与会话 | [Task05](../plans/043/task-05-analysis-conversations.md) | 04 | 摘要/会话真实通过；全文KB partial阻塞 |
| 06 | 整理与导出 | [Task06](../plans/043/task-06-groups-exports.md) | 04 | 阶段已完成（真实API/PNG/JSON PASS） |
| 07 | 手机适配 | [Task07](../plans/043/task-07-mobile-map.md) | 05、06 | 实施中；全文KB阻塞独立保留 |
| 08 | 最终验收与收口 | [Task08](../plans/043/task-08-acceptance-deploy-retro.md) | 02–07 | 待执行 |

## 评审记录

- 需求评审：[043-requirement-review.md](../reviews/043-requirement-review.md)（独立评审通过，2026-10-19）。
- 技术评审：[043-tech-review.md](../reviews/043-tech-review.md)（独立评审通过，2026-10-19）。
- 验收评审：`docs/sdd/reviews/043-acceptance-review.md`（待评审（未执行）；测试报告与架构师签字均未产生）。
- 建档为主会话纯文档代行；随后需求/技术评审已真实独立执行，验收尚未执行。

## 变更日志

- 2026-10-19：Grilling Q1–Q27与截图布局确认，选择自动有界主题图谱、独立项目绑定、分层引用/相似与阶段交付。
- 2026-10-19：只读复用核对确认现有S2客户端/目录RAG/作业/会话资产；明确身份不可混用、引用方向、持久缓存缺口。
- 2026-10-19：用户要求先落盘；主会话代行纯文档建档，状态待确认，Task02–08待执行，无代码/部署/数据迁移。
- 2026-10-19：用户明确授权实现，独立需求/技术评审通过，状态转已确认再实施中；Task02开始。纳入真实30/50返回数量、owner-scoped解绑失败保留项目和合同先行门禁，未宣称真实API已通过。
- 2026-10-19：Task02独立合并Go（8项精准测试、真实S2引用和200节点620边浏览器压力档），Task03合同冻结并开始分端实现；尚无生产地图API/部署成功证据。
