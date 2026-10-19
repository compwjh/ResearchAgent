# Task 03 — 桌面自动建图 MVP

> 关联：[Spec043](../../specs/043-literature-map-topic-exploration.md) ｜ 索引：[README](./README.md)  
> 依赖：02 Go；Spec明确确认且需求/技术评审通过；被依赖：04；当前状态：**进行中**。

## 一句话目标

交付用户可输入主题、看到真实图谱、点选论文并保存重开的桌面纵向MVP。

## 当前证据与前置条件

- 当前只有已确认的产品讨论与本轮规划文档；本Task未实施、未测试、未部署。既有API资产不等于地图功能已存在。
- 复用代码位置是调研入口，未来实现时需对照实际提交核实，不复制过期实现。后续新增模块/前端文件按前置Task固定报告定位，不猜文件名。
- Spec处于待确认时禁止实现。需求/技术门禁通过及用户明确确认后，先核对工作区/实现分支，保护Spec032暂停快照及其他任务修改。
- 前置Task真实通过后才能执行；若预生成接口尚未冻结，应标阻塞而非自行发明第二套合同。

## 最小上下文

- `docs/sdd/specs/043-literature-map-topic-exploration.md（本Task有关章节）`
- `docs/sdd/plans/043/README.md`
- `backend/app/api/common.py`
- `backend/app/api/routes_paper.py`
- `backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py`
- `backend/app/paper_discovery/application/catalog_search_graph.py`
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`

## 数据、配置与接口增量

- v1合同已冻结并经Task02复核：[interface-contract.md](./artifacts/task-03/interface-contract.md)。后续两端实现以此为准，不凭聊天猜测字段。
- 以Spec数据模型和端点章节为边界；本Task冻结v1身份/schema_version/公开接口/事件/幂等/revision和迁移契约。
- 地图范围最多200节点；首批默认30可20/50，扩展apply每批最多20。任何测试样例不得暗中改阈值或范围。
- 后端与前端交接固定输入输出、错误码和可观察状态，类型/版本变化先更新接口交接。

## 实施步骤与文件边界

1. 先冻结v1 map/node/edge/job/event/preview身份、schema_version、revision、幂等、错误和事件合同，报告写入artifacts/task-03/interface-contract.md；只冻结后续扩展字段，不提前实现所有功能。
2. 新增backend/app/literature_maps/{domain,application,infrastructure}与地图路由，复用SQLite增量迁移/执行器/现有S2与embedding服务；地图job语义独立，owner贯穿全部读写。
3. 持久化map/node/edge/view与作业检查点；项目删除置空地图project，map删除不触碰共享目录/KB/会话。冷启动可读已有图，重启可恢复未完成获取。
4. 创建主题任务：默认30、允许20/50，scope可选；metadata-only、真实相关性筛选、不足partial。在选中集合内补引用；cosine>=0.75每节点top3后无向去重，不自动递归扩图。
5. 复用embedding客户端与持久向量缓存，模型/内容hash变化才补算；引用图在向量不可用时保持可用。关键词/摘要无则缺失。
6. 前端新增独立地图组件与showView入口。现有主导航＋工作区左列表/筛选＋中央SVG＋右可关闭详情；紫色浅底，引用有向实线/相似无向虚线分层开关，图例显示依据。
7. 实现阶段进度、partial/错误/重试提示、缩放平移/适应画布/搜索定位/拖动保存/年份下载状态筛选。无需AI、分组、导出或手机完整布局。
8. 详情桥接现有安全原文链接与主动导入句柄，失败仍走既有论文恢复能力，不另造下载。查看地图不下载；离开页面不停后台任务。
9. 前端改动同步静态资源版本和DOM契约；定向验证后部署精确候选版本，跑真实API创建/查询及浏览器核心smoke。

允许范围：后端新增literature_maps领域及必要地图路由/生命周期注册、项目删除解绑窄接缝；前端独立地图组件与导航/样式。两端分别分派，其他领域只做已列必要适配。

## 子任务拆分与分派

1. backend-dev：只承担本端/本角色步骤，使用上述最小上下文；当前模型从角色配置读取，实际调用遵循当次用户覆盖，不在本Task固化临时型号。
2. frontend-dev：只承担本端/本角色步骤，使用上述最小上下文；当前模型从角色配置读取，实际调用遵循当次用户覆盖，不在本Task固化临时型号。
- 后端完成后由独立 backend-reviewer 复核，backend-tester 运行后端精准验证。
- 前端完成后由独立 frontend-reviewer 复核，frontend-tester 做DOM/版本/XSS/交互契约与浏览器核对；不因前端单端改动运行后端全量。
- 主会话负责依赖接续与裁决；长报告落盘读回，不以口头“改好了”直接接部署。日志按spec/task/角色分层。

## 可直接使用的分派 Prompt

### backend-dev

```text
角色：backend-dev。模型按本次主会话明确分派；不修改长期配置。Spec043 Task03：桌面自动建图 MVP。
目标：交付用户可输入主题、看到真实图谱、点选论文并保存重开的桌面纵向MVP。
只读取本Task、关联Spec有关章节、前置任务固定交接报告，以及“最小上下文”列出的本端必要文件。角色技能按项目绑定加载，不全仓扫描；前端不要读取后端实现，后端不要扫描前端vendor。
允许范围：backend/** 与 tests/literature_maps/（必要时既有受影响后端领域测试）；不得修改frontend/**。报告例外写本Task artifacts 下固定报告，进展日志写 .codebuddy/agent-logs/spec-043/task-03/backend-dev/。
执行本Task实施步骤中属于本角色的部分；跨端公开契约只以已冻结文档为准，缺失或冲突先报告主会话，不自行猜测。
禁止：未确认就实现、扩大Spec、重写下载/embedding/chat框架、读取或输出.env凭据、保存隐藏推理、篡改旧研究任务、清空数据库、覆盖用户修改、自动push/合并main、伪造验证或提前宣称部署。
完成后可观察状态：本Task验收标准属于本端的条目达到，并明确尚未由真实API/浏览器验证的部分。
验证：运行本Task“验证命令”中属于本端的精确命令，补充实际改动文件ruff/语法或前端静态检查；除Task08最终收口外不跑全量。
返回并落盘：结果状态/摘要；改动文件；命令、退出码、通过数；产物路径；决策依据；风险与阻塞；主会话下一动作；开始/结束/耗时；可取得时记录模型/token/工具次数，不编造缺失指标。
```

### frontend-dev

```text
角色：frontend-dev。模型按本次主会话明确分派；不修改长期配置。Spec043 Task03：桌面自动建图 MVP。
目标：交付用户可输入主题、看到真实图谱、点选论文并保存重开的桌面纵向MVP。
只读取本Task、关联Spec有关章节、前置任务固定交接报告，以及“最小上下文”列出的本端必要文件。角色技能按项目绑定加载，不全仓扫描；前端不要读取后端实现，后端不要扫描前端vendor。
允许范围：frontend/** 与本Task对应的前端契约测试；不得修改backend/**。报告例外写本Task artifacts 下固定报告，进展日志写 .codebuddy/agent-logs/spec-043/task-03/frontend-dev/。
执行本Task实施步骤中属于本角色的部分；跨端公开契约只以已冻结文档为准，缺失或冲突先报告主会话，不自行猜测。
禁止：未确认就实现、扩大Spec、重写下载/embedding/chat框架、读取或输出.env凭据、保存隐藏推理、篡改旧研究任务、清空数据库、覆盖用户修改、自动push/合并main、伪造验证或提前宣称部署。
完成后可观察状态：本Task验收标准属于本端的条目达到，并明确尚未由真实API/浏览器验证的部分。
验证：运行本Task“验证命令”中属于本端的精确命令，补充实际改动文件ruff/语法或前端静态检查；除Task08最终收口外不跑全量。
返回并落盘：结果状态/摘要；改动文件；命令、退出码、通过数；产物路径；决策依据；风险与阻塞；主会话下一动作；开始/结束/耗时；可取得时记录模型/token/工具次数，不编造缺失指标。
```

## 返回后的主会话校验

1. 读取实际diff与固定报告，确认修改范围/引用/产物存在，无占位实现或 unrelated 覆盖。
2. 核对测试命令、退出码、数量及真实/合成/只读重放证据类别；不得把定向测试当真实E2E。
3. 对照Spec逐条核实身份/来源/关系方向/删除边界/密钥脱敏及本Task停止条件。
4. 组织对应端独立复审与集中修复；通过后接依赖Task或部署里程碑，未通过写清阻塞。
5. 同步Task、README和Spec任务索引实际状态；状态变化写统一台账，不能提前填完成。

## 实时监控

- 正常线上子Agent等待其主动回传，不常态轮询日志；具体角色日志位于上文路径。
- 只有用户要求/明确异常才读取一次对应日志定位。
- 实现后通过地图job与events接口观察实际阶段/计数/failed_units；目前接口未实现，不声称可调用。
- 可用只读核对：`git status --short`、`git diff --check`。不得并发启动多个使用同一存储的未评审服务。

## 验证命令与验收

下列新测试路径为本Task计划创建的能力命名测试，不表示文件已存在或已执行；实施时先补红灯测试并落盘真实命令结果。
- `.venv/bin/python -m pytest -q tests/literature_maps/test_map_identity.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_discovery.py tests/literature_maps/test_map_similarity.py tests/literature_maps/test_map_api.py`
- `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py`
- `.venv/bin/python scripts/check_test_layout.py`

- 真实主题→202 map/job→真实节点及引用→相似层→保存重开可操作；没有人工填假节点替代。
- 200节点交互不持续阻塞，点击详情与拖动不反复全图重排，布局持久。
- 项目解绑/owner隔离/不下载/引用方向/缓存/相似降级/目标不足皆有精准测试。
- API和浏览器实际结果/版本/端口有据；首个MVP部署不是Spec最终完成。
- 测试文件/函数名不含spec/task数字，源码归领域子目录；全量回归只在Task08最终候选。
- 本Task结果不足时标明“不通过/阻塞”，不得记录为“已完成”。

## 风险、停止条件与回滚

核心创建、身份隔离、真实引用或持久化失败即停止发布并同范围修复；不扩张到自动下载/整图综述。
- 保留用户数据和已完成结果；迁移前备份，回滚禁用新增入口/作业，不删共享目录/KB/旧报告，不reset/stash/clean覆盖修改。
- 真实外部API限流/权限失败保留脱敏证据，说明具体下一步，不绕过访问控制。
- Spec范围或公开接口发生实质变化先回架构师/用户确认，不靠实现者自由设计补齐。

## 产出物

- `artifacts/task-03/interface-contract.md`（待执行后生成）
- `artifacts/task-03/backend-report.md`（待执行后生成）
- `artifacts/task-03/frontend-report.md`（待执行后生成）
- `artifacts/task-03/mvp-e2e-report.md`（待执行后生成）
- 代码/测试/评审与本Task交付应可追溯到同一候选提交；上述固定文件追加修复记录，不重复建多轮报告。
- artifacts路径均相对 `docs/sdd/plans/043/`。目前未产生，不预造结果或真实数据。

## 执行结果

2026-10-19阶段检查点（主会话纯文档记录，非验收签字）：

- 已复审候选提交 `4cb5735`，地图域测试62项通过；前端独立复审通过，后端最后四项P1窄复审通过。
- 使用 `PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh` 启动本机候选，`http://127.0.0.1:8000/api/ready` 返回200。
- 真实主题“graph attention networks”、limit20创建地图 `9b1e4739443e40c98400cfb69aec1e45`、作业 `b4ccc1dfe6814c36a42a1f67e7681f52`；得到20个节点，布局保存重开通过，但引用响应无效、零引用边，终态partial；一次主动导入返回PDF_NOT_FOUND。详见 `artifacts/task-03/api-e2e.md` 与 `api-evidence.json`。
- 当前真实E2E不通过，Task保持进行中，不交人工验收。引用provider响应及主题相关性排序继续诊断；地图导入遗漏既有arXiv解析能力的接缝正在修复，需独立复审、重启后重新验证。
- 浏览器独立验收进行中；不将可行性测试、mock、HTTP202或健康检查当成核心功能成功。

## 变更日志

- 2026-10-19：主会话依据已确认讨论纯文档代行建档，非独立评审；Task保持待执行，未改业务代码。
