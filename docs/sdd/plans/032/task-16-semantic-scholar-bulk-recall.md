# Task 16：Semantic Scholar 候选池辅助召回

> 关联：[Spec 032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task07、Task08、Task15 ｜ 当前状态：`最小实现完成；SQLite 重启/重复 query 已验证，待 Task14 真实候选与最终收口`

## 一句话目标

当官方目录与 DBLP 候选不足时，以 Academic Graph bulk search 有界补充候选；结果必须标记聚合来源并经过现有论文评估，不得仅凭 venue 字段归入会议。

## 当前证据

- `SemanticScholarGraphClient.search_bulk` 已提供 `query/year/limit/fields` 约束和稳定错误码。
- `CatalogSearchGraph` 已在候选不足且 key/开关允许时有界写入聚合候选；候选写入 `semantic_scholar` source record，不进入官方 source scope。
- 当前尚未把 Semantic Scholar 加入 `search_source_progress`/SourceRegistry，避免旧 SQLite CHECK 约束被未知来源破坏；这部分留 schema 评审。

## 前置门禁

- 只在候选数低于批准计划的 `target_paper_count` 时触发，且有硬上限和超时。
- 结果进入独立聚合候选池，先经过 `research-paper-evaluation`，不直接当作官方会议论文。
- 不自动下载 PDF；不接受用户传入任意 URL；保留 Semantic Scholar paperId 与查询证据。

## 思维链

1. 读取已冻结官方/DBLP 数量和批准范围，计算缺口而不是重复查询。
2. 按 query + year 做 bulk search，记录分页 token、响应 hash 和限流事件。
3. 以 DOI、ArXiv、标题/作者/年份做去重和身份门禁；venue 仅作为候选提示。
4. 候选评估通过后再进入统一目录/报告链；失败只形成 `degraded` 证据。

## 分派 Prompt

```text
角色：后端开发；模型：按 Spec032 执行配置；只读取 Spec032、Task16、CatalogSearchGraph、PaperDiscoveryStore、research-paper-evaluation Skill 和 SemanticScholarGraphClient。
允许修改：backend/app/paper_discovery/** 与 tests/paper_discovery/** 的聚合召回模块；禁止修改官方来源解析器、PDF 下载/导入、安全 allowlist、前端和报告合成器。
必须遵守：有界 limit/分页/超时；聚合来源不可覆盖官方字段；不能凭 venue 宣称会议归属；搜索阶段不下载 PDF；不可引入第二套目录缓存。
必须运行相关定向测试并把结果写入 docs/sdd/plans/032/artifacts/task-16/，日志写入 .codebuddy/agent-logs/spec-032/task-16/backend-dev/。
固定返回：结果状态和摘要、改动文件、测试命令/退出码/结果、产物路径、决策依据、风险与阻塞、主 Agent 后续动作、开始/结束/总耗时、可用时模型/token/工具统计。
```

## 主 Agent 校验步骤

- 验证官方候选达到目标时完全不发 Semantic Scholar bulk 请求。
- 验证不足时只补缺口上限，重复搜索命中缓存，不重复入库。
- 验证候选没有会议官方证据时保持 `aggregate/unverified`，不能进入官方 source scope。

## 测试与验收标准

固定 MockTransport 覆盖分页、429、空结果、重复 DOI、同名不同年和 venue 误判；服务重启后仍能读取候选证据；限流统计可审计。

## 风险、停止条件与回滚

若需要修改 `search_source_progress` 的 CHECK 或公开 SourceKind，先提交 schema 迁移和技术评审；不得直接把未知 source 写入旧 SQLite。

## 产出物

聚合候选池、评估接线、缓存/分页测试和验收证据。

## 执行结果

客户端与 Graph 辅助召回已完成；真实 SQLite 持久化、重启后 completed fetch-unit 命中和重复 query 不重复请求已通过定向测试。真实外部 bulk、评估器贯通和 Spec032 最终收口仍待 Task14。

## 变更日志

- 2026-09-21：新增有界 bulk recall 任务，明确不把 Semantic Scholar 变成官方会议来源。
