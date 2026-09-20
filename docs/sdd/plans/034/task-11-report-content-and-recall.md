# Task 11：至少五篇候选与实质性综述输出

> 关联 Spec：034 会话式深度研究与真实子 Agent Runtime  
> 依赖：Task06、Task08、Task10  
> 被依赖：Spec029 全文证据升级  
> 当前状态：`已完成（实现与目录复验）`

## 一句话目标

在 USENIX 目录证据可用时，研究任务至少保留五篇相关论文（候选不足时如实返回），并让 Markdown/HTML 报告包含标题、摘要、关键词和跨论文归纳，而不只输出 ID。

## 当前证据

- Task10 真实 Smoke 已生成 Artifact，但 Markdown 只有一篇证据对象和引用清单。
- `ReportSynthesizer` 当前模板只渲染 `candidate_id`，`agent_runtime` 明确禁止 section summary 和 paper findings。
- Search Worker 已能返回真实目录候选；Evaluator 输入必须继续受 `catalog_evidence` 白名单约束。

## 前置门禁

- 只使用 USENIX 目录/摘要证据；搜索阶段不下载 PDF。
- 候选、标题、摘要、关键词必须来自已验证 ToolResult 或目录快照；不得模型臆造。
- 证据不足五篇时输出实际数量与原因，不伪造数量。

## 实施范围

- 评估器在候选不少于五篇且达到软阈值时保留至少五篇；目标数量仍受既有预算上限约束。
- 扩展受控报告字段，允许安全的 `title`、`abstract`、`keywords`、`summary` 和 `comparison` 文本。
- Markdown 至少包含研究范围、逐篇摘要、主题/方法归纳、局限和引用清单；HTML 仍由固定安全渲染器派生。
- 保留现有引用白名单、哈希、Artifact 幂等和失败闭环。

## 明确不做

- 不在本 Task 下载或解析 PDF，不改变 Spec029 的全文导入流程。
- 不保存 Prompt、隐藏思维链、凭据、任意 URL 或未经证据支持的结论。
- 不重写目录、下载、知识库或调度实现。

## 验收标准

- 固定主题能返回至少五篇真实 USENIX 目录论文；候选数不足时结果为 partial 并说明原因。
- Markdown 不再只有证据 ID，包含真实标题/摘要/关键词（存在时）和跨论文归纳。
- 恶意 URL、Prompt/CoT、越界引用和未验证论文仍被拒绝。
- 受影响后端定向测试、Artifact 下载和现有 Spec034 报告测试通过。

## 执行结果

已完成实现，待真实 USENIX 主题 Smoke 收口：

- 候选池不少于 5 篇时，评估器在既有 20 篇硬上限内至少保留 5 篇；候选不足时保持真实数量。
- Search→Evaluator→Synthesizer 只传递脱敏目录标题、摘要、关键词及有限主题字段。
- Markdown/HTML 输出论文标题、摘要、关键词；模型遗漏已验证候选时自动追加“目录证据补充”章节。
- 定向回归：`114 passed, 5 subtests passed`；`py_compile` 与 `git diff --check` 通过。
- 实现报告：`artifacts/task-11/report-five-candidates.md`、`artifacts/task-11/rich-report.md`。
- 2026-09-16 使用当前缓存目录候选池 `search_id=dd5c47aa0cb541188b884c27fa233e67` 做真实生成复验：固定 5 篇 USENIX 模糊测试论文，`ReportSynthesizer` 产出 5 条引用、约 8.9k 字符 Markdown；标题与摘要来自 `catalog_papers`，关键词字段为空时输出“目录未提供”，不由模型补写。样本：[usenix-fuzzing-sample.md](./artifacts/task-11/usenix-fuzzing-sample.md)。
- 同日全量回归曾运行至 1002 个用例后因会话压缩 worker 的 4 个既有用例停滞而中断（`queued/running` 未转终态）；该失败不涉及 Task11 文件，但按门禁保留为 Spec034 收口阻塞，不能把 Spec034 标为已完成。

## 变更日志

| 时间 | 变更 |
|---|---|
| 2026-09-16 | 根据真实 Smoke 发现报告只有 155 字，新增候选数量与报告内容补强 Task。 |
