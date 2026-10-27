# Spec043 执行索引：交互式文献地图与自动主题探索

> 关联：[Spec043](../../specs/043-literature-map-topic-exploration.md)
> 历史交付状态（非本轮当前状态）：2026-10-22候选 `a328932` 的Task02–08已完成，全量 `exit 0`、`3224 passed / 0 failed / 2 skipped / 67 subtests / 5 warnings`，tester与architect双签；本轮Task09状态见下文。保留旧失败、provider partial、非物理真机及未执行故障注入限制，不将READY_FOR_USER等同用户已人工通过。

## 交付主线

2026-10-27当前增量：**实施中**，[Task10](task-10-map-usability.md)完成Grilling Q1–Q10选择，独立需求/技术评审已GO，用户已确认共同理解；在独立工作目录按Task10实施。

2026-10-24历史修订：**已完成**；Task09独立复核、真实入库/全文/浏览器、最终全量3384通过与覆盖率82.38%均通过，tester与architect双签READY_FOR_USER（10/10），已部署8000JSv18。本轮[Task09](task-09-map-interaction-analysis.md)承接图谱交互、自动摘要、全文指引、提问草稿及最后导入接缝修复；[人工步骤](task-09-manual-acceptance.md)、[最终回归](task-09-final-regression.md)、[复盘](../../retro/2026-10-24-spec043-map-interaction.md)。主会话仅同步文档，不替代独立签字；来源partial保留，不等同用户已实际验收。

输入主题自动建图 → 真实引用与稀疏相似 → 点击论文详情/主动入库 → 保存重开 → 预览扩展/刷新/恢复 → 有依据的AI与会话 → 分组导出 → 手机 → 最终验收。
不依赖Spec032正式报告生成，不恢复其暂停工作；不把图谱改为只能手动选论文。

## Task 索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| 01 | Spec与规划文档 | — | 已完成（仅建档） |
| [02](./task-02-validate-feasibility.md) | 准备与可行性门禁 | 01（Spec与需求/技术门禁已确认后执行） | 已完成（Go） |
| [03](./task-03-desktop-map-mvp.md) | 桌面自动建图 MVP | 02 Go；Spec明确确认且需求/技术评审通过 | 阶段已完成（PASS_WITH_LIMITATIONS） |
| [04](./task-04-expansion-recovery.md) | 扩展与恢复 | 03 | 阶段已完成（PASS_WITH_LIMITATIONS） |
| [05](./task-05-analysis-conversations.md) | AI 分析与会话 | 04 | 阶段已完成（PASS_WITH_LIMITATIONS；摘要/全文API真实PASS，历史与全文入口已由最终浏览器观察） |
| [06](./task-06-groups-exports.md) | 整理与导出 | 04 | 阶段已完成（真实API/PNG/JSON PASS） |
| [07](./task-07-mobile-map.md) | 手机适配 | 05、06 | 阶段已完成（候选`1a3ff26`真实375/390/1440浏览器PASS；非物理真机） |
| [08](./task-08-acceptance-deploy-retro.md) | 最终验收与收口 | 02–07全部完成 | 已完成（a328932 runtime/browser/full regression/deployment PASS；tester 与 architect 双签） |
| [09](./task-09-map-interaction-analysis.md) | 图谱交互与自动摘要修订 | 03、05、07旧版资产 | 已完成：不可用操作反馈；最新51项前端测试、独立签字及真实页面通过 |
| [10](./task-10-map-usability.md) | 地图间距、配色与详情反馈 | 03、05、06、07、09历史资产；本轮确认与门禁 | 实施中（已确认共同理解） |

## 执行约定

- Task09依赖旧版03/05/07已交付资产，当前增量评审GO、前后端实施中；最终由本轮增量API/浏览器、独立签字及全量证据重新收口，不冒用旧Task08报告。

- Spec为“做什么”的权威来源，Task为“怎么做”的实施交接；后续不得依赖聊天猜测需求。
- Task03首个桌面纵向MVP，Task04补扩展/恢复；05和06可在04后按互不冲突范围执行，07依赖两者，08最后统一收口。
- 仅在Spec确认及门禁满足后分派实现，前后端分开。模型按当次用户指派，长期角色配置不因临时选择修改。
- 初始建档由主会话纯文档代行；需求与技术独立评审已通过，见 `../../reviews/043-requirement-review.md` 与 `../../reviews/043-tech-review.md`。最终验收评审已完成，见 `../../reviews/043-acceptance-review.md`；历史失败与限制仍按证据分类保留。
- 每Task复用少量固定报告，代码/测试/评审读回后才交下一门禁；Task精准测试，最终全量在08。
- 测试按能力命名，放tests/literature_maps或现有frontend等领域；不带spec/task编号，tests根目录不放测试文件。
- 已有产物以各Task的实际报告为准；Task02可行性与Task03开发/复审报告已落盘，Task03/04阶段证据与 Task05/07 最终真实 API/浏览器证据均已归档。不将可行性探针或静态夹具当产品成功证据；Task08 全量/重启/部署已绑定最终候选 `a328932`，旧候选与失败证据仍保留。

## 复用硬边界

S2客户端/1RPS、现有下载导入/登录上传恢复、embedding/RAG、项目与会话、前端壳复用；新增literature_maps领域、地图作业和持久节点/边/预览。S2 ID不等于catalog ID；引用方向与相似边类型分开。
PNG/JSON不含秘密；建图不下载；缺字段不编造；删除地图不删PDF；向量故障只降级相似层。
截图只借鉴布局：现有主导航＋地图列表/筛选＋中央SVG＋右侧详情，后续手机详情抽屉；不复制支持/反对语义。

## 验收核心案例

Task02固定真实主题和论文ID；Task03真实主题创建并读回地图、关系与布局，部署桌面MVP；Task04扩展预览后确认及恢复；Task05–07分别提供真实分域证据。
Task08准备逐步可执行手工案例，记录每步点击/提示/等待/恢复/结果路径。至少9/10且无核心阻塞才交付，API失败不让用户代排错。

## 状态与变更

- 2026-10-19：共同理解确认后按用户要求创建Spec、全部Task与本索引，Spec保持待确认，不实现业务代码。
- 2026-10-19：需求/技术独立评审通过，用户授权实现；Task02进行中。验收尚未执行，不以方案通过代替真实验证。
- 2026-10-19：Task02已完成；Task03前端复审及后端最后四项P1窄复审通过，地图域62项测试通过。本机候选服务已启动并验证就绪，两个独立验收子代理执行真实API和浏览器检查；Task03保持进行中。
- 2026-10-19：真实E2E暴露并修复相关性排序、arXiv解析接缝、导入诊断持久化及画布平移保存。候选 `4d075a4` 本机8000就绪；真实地图 `0baabeae7268429c9f7e4de8098ae1d0` 已有20节点、12引用边、5相似边，浏览器保存重开通过；引用仍有provider限流/歧义响应，导入仍受arXiv匹配不确定与S2限流阻塞。地图域84项测试通过，不等于真实导入通过。正在复用既有adapter补精确arXiv ID元数据查询；Task03未完成，Task04尚未开始。
- 2026-10-21：Task05 候选 `82c816f` 的摘要/全文 source gate、全文分析/幂等、全文会话/幂等及 QA/SSE 真实 API PASS，阶段验收记录为 PASS_WITH_LIMITATIONS；早期全文 BLOCK、scoped reindex 后仍 BLOCK、服务不可达 continuation 均保留。Task07 候选 `1a3ff26` 的真实 375/390/1440 浏览器复验 PASS，阶段签字完成；全文 v1/v2 与全文按钮可见，未重复触发分析 POST。Task08 全量回归由 `map_regression_preflight` 独立隔离执行，首轮 `3191/18/14/67/5`（passed/failed/skipped/subtests/warnings）BLOCK；运行中 job stop 保留成果与进程重启恢复已真实 PASS，root 正在分派同范围修复与重跑，最终验收/部署/签字尚未完成。
- 2026-10-22：候选 `a328932` 完成最终 runtime/browser/full-regression/deployment 验证；全量 `exit 0`、`3224/0/2/67/5`（passed/failed/skipped/subtests/warnings），列表关闭动画延迟复核通过，tester 与 architect 双签，Task08/Spec043 状态及台账已收口为已完成。用户人工验收尚未实际执行；READY_FOR_USER 仅表示可交付人工验收，历史首轮失败与既有限制保持原记录。

## 当前修订

[Task10 — 地图间距、配色与详情反馈](task-10-map-usability.md)：待执行，Spec待确认。

## 待确认增量

[Task11：论文关联扩展与后台分析](task-11-paper-expansion.md)：待执行（修订待确认），先核实现有资产并通过[Grilling](2026-10-27-paper-expansion-grilling.md)确认边界，不实现新代码。

Task11规划更新：Q1–Q15均采用推荐，独立需求／技术评审已GO；[接口合同](task-11-interface-contract.md)冻结分页、跨预览原子确认及后台恢复设计。修订待用户共同理解确认，任务仍待执行，不实施。

Task11当前：用户在共同理解摘要后要求继续，需求／技术GO，修订已确认、任务待执行；先完成Task10未部署全文提示候选收尾，再按冻结合同分端开发。历史待确认文字保留为过程记录。
