# Spec 032 执行计划：数据源与安全会议扩展

> 关联：[Spec 032](../../specs/032-research-source-expansion.md)
> 当前状态：待确认。

## 任务索引

| Task | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [02](./task-02-source-adapter-contract.md) | Adapter、字段 provenance 和增量缓存合同 | Spec027/015、确认、双评审 | 待执行 |
| [03](./task-03-openalex-crossref-adapters.md) | 聚合书目来源接入 | 02 | 待执行 |
| [04](./task-04-security-conference-adapters.md) | IEEE S&P、ACM CCS、NDSS 官方目录 | 02 | 待执行 |
| [05](./task-05-source-merge-progress-ui.md) | 来源合并、Research Task 进度和界面 | 03、04 | 待执行 |
| [06](./task-06-review-regression-deploy.md) | 最终验收、全量回归、部署和复盘 | 02–05 | 待执行 |

## 统一规则

- 官方来源字段优先，聚合来源只补缺；搜索阶段不下载 PDF。
- 新来源必须有固定样本后才允许启用。
- 开发 Task 定向测试，Task06 唯一一次全量回归。
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

两个仍待决策的点：

1. **Task02 状态**：合同在代码层已由 Task04 的适配器满足（见 `cross-conference-oa-acceptance.md`
   §1c），缺的是状态确认而非实现；Task02 是 Task03–06 的依赖。
2. **Task05 入库门禁**：实测存在 0.24% 的**静默**错链（OpenAlex 把预印本挂错 DOI），
   下载链每一步都"成功"、只有内容对不上。建议入库前加内容校验门禁。

## 变更日志

- 2026-09-14：补 Task04 验收证据索引（未改动各 Task 状态，待 spec 负责人确认）。
- 2026-09-12：随 Spec032 创建。
