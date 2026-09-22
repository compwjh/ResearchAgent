# Spec 032 执行计划：多来源 Worker、自动导入与人工修复

> 关联：[Spec 032](../../specs/032-research-source-expansion.md)
> 当前状态：实施中（2026-09-20 新版已确认；Task06、Task08–Task12 已完成，Task07、Task13 部分完成；Task15–Task17 已完成最小实现，待 Task14 真实环境验收与最终收口）。

先读 [资产与缺口审计](./asset-gap-audit.md)。旧 Task02–05 保留历史产出与真实缺口，不能把“有 Adapter/Registry”直接等同于产品可用。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-source-adapter-contract.md) | 原 Adapter/缓存合同资产 | Spec027/015 | 历史资产；独立合同门禁未闭环 |
| [03](./task-03-openalex-crossref-adapters.md) | OpenAlex/Crossref Adapter | 02 | 代码已产出，主链未接 |
| [04](./task-04-security-conference-adapters.md) | IEEE S&P、CCS、NDSS Adapter | 02 | 代码/样本已产出，官网主链未接 |
| [05](./task-05-source-merge-progress-ui.md) | 原来源注册/API/provenance 阶段交付 | 03、04 | 部分完成、待纠偏 |
| [06](./task-06-unified-source-contract.md) | 统一 ID、authority、类型与回归 | 02–05、新版确认 | 已完成（定向验证通过） |
| [07](./task-07-official-catalog-coverage.md) | 官网目录与逐年字段覆盖 | 06 | 部分完成（IEEE S&P/NDSS 2024 固定样本；CCS 2021–25 bounded NO-GO） |
| [08](./task-08-catalog-runtime-integration.md) | 真实同步、Graph/Store/Planner 接线 | 06、07 | 已完成（旧 Graph + 新来源 Worker bridge；真实 smoke 留 Task14） |
| [09](./task-09-source-worker-skills-tools.md) | 会议 Worker Skill 与统一 Tool | 06–08 | 已完成（worker-tool-v1；未验证来源保持 blocked） |
| [10](./task-10-approved-plan-auto-import.md) | 批准计划内自动导入 | 08、09 | 已完成（定向验证通过） |
| [11](./task-11-paper-issue-recovery.md) | 待处理论文、登录/上传/恢复 | 10 | 已完成（后端定向验证通过；前端留 Task12） |
| [12](./task-12-source-progress-issue-ui.md) | 来源/字段/修复界面 | 08、11 | 已完成（前端定向验证通过；真实 smoke 留 Task14） |
| [13](./task-13-spec0321-carryover.md) | 032.1 余项移交 | 09、032.1 评审 | 部分完成（静态/契约通过；真实服务 smoke 阻塞） |
| [14](./task-14-review-regression-deploy.md) | 最终验收、全量回归、部署和复盘 | 06–13 | 实施中 |
| [15](./task-15-semantic-scholar-metadata-enrichment.md) | Academic Graph 批量详情补全缺失字段与 provenance | 06、08、14 | 最小实现完成；待 Task14 真实 key/重启验收 |
| [16](./task-16-semantic-scholar-bulk-recall.md) | 候选不足时的有界辅助召回与严格身份门禁 | 07、08、15 | 最小实现完成；SQLite 重启/重复 query 已验证，待 Task14 真实候选与最终收口 |
| [17](./task-17-semantic-scholar-graph-assistance.md) | autocomplete、引用/参考文献图辅助 | 15、16 | 最小实现完成；待 Task14 真实 key/部署验收 |

## 统一规则

- 官方来源字段优先，聚合来源只补缺并按真实来源写 provenance；搜索阶段不探测或下载 PDF。
- Semantic Scholar 只作为受控聚合补全/召回：批量详情补缺字段，候选不足时有界 bulk recall；所有请求共用 1 RPS 限流，API key 仅服务端读取。
- 四会议逐年验收，未验证年份只可有界尝试；必须有真实样本才能标记可用。
- 批准的 Research Task 自动导入、普通检索手动导入；失败具体论文入待处理队列，整源失败留来源进度。
- 开发 Task 只跑受影响定向测试，Task14 唯一一次全量回归。
- 产出写入 `docs/sdd/plans/032/artifacts/task-NN/`。

## Task04 验收证据（2026-09-14 补充，状态待 spec 负责人确认）

Task04 的适配器**已实现并有真实数据验收**，但计划状态尚未更新。证据集中在
`artifacts/task-04/`：

- `cross-conference-oa-acceptance.md` — 三会议横评、多年度（2022–2025，12 组合全绿）、
  Task02 合同符合性、412 篇内容正确性（错链 1 篇，0.24%）、文本层审计（零扫描件）
- `doi-resolver-fix-report.md` / `doi-resolver-import-path-fix.md` — `doi.org` 解析地址
  在批量下载器与入库路径的修复（同一实现，测试用 `is` 断言锁定）
- `enrichment-batching-fix.md` — 富化 N+1 批量化，三会议 753s → 40.8s
- `oa-end-to-end-acceptance.md` — 发现 → 富化 → 下载 → 入库闭环

两个历史发现已纳入修订版：

1. **Task02 合同**：已有实现可以复用，但返回类型/ID/authority 尚不一致，由 Task06 统一并复验。
2. **错链门禁**：OpenAlex 预印本错挂 DOI 曾出现约 0.24% 的静默错误；由 Task10 把内容/身份核验纳入自动入库门禁。

## 变更日志

- 2026-09-20：经用户共同理解确认重排 Task06–14；旧 Task02–05 按事实区分代码资产与完整验收，032.1 余项移交 Task13。
- 2026-09-14：补 Task04 验收证据索引（未改动各 Task 状态，待 spec 负责人确认）。
- 2026-09-12：随 Spec032 创建。
