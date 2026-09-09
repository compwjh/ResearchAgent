# 论文检索（Paper Discovery）

用户从外部学术来源（USENIX Security 官网、DBLP 辅助书目）按研究方向与年份检索论文、并把候选论文导入知识库的场景。本文件只收录该场景特有的词汇，供人与 Agent 共用一套说法。

## Language

**检索作业（SearchJob）**:
一次检索请求从创建到终态的完整记录，由 `search_id` 标识，是"这次检索"的唯一说法。
_Avoid_: 搜索会话、搜索任务、search session、job

**来源进度（SourceProgress）**:
某一个外部来源（USENIX / DBLP）在某次检索作业内的进展，包括缓存、抓取、完成、论文数与失败原因。
_Avoid_: 来源状态、来源卡、source card

**整体状态（JobStatus）**:
一次检索作业的生命周期状态（`queued` / `running` / `completed` / `partial` / `failed`），只在一处呈现。
_Avoid_: 检索状态、结果状态、进度状态

**年份校验边界（YearValidationBoundary）**:
后端在参数校验时接受的年份下限与上限（当前为 1900 至当年）。越界即拒绝请求。
_Avoid_: 合法范围、合法年份、受控范围

**目录覆盖边界（CatalogCoverageBoundary）**:
外部来源实际提供论文目录的最早年份（USENIX 为 2022）。早于该年不报错，但没有目录可检索。
_Avoid_: 可用年份、支持年份、有数据的年份

**空结果归因（EmptyReason）**:
检索成功但结果为零时的原因区分：`year_out_of_catalog`（所选年份早于目录覆盖边界）、`no_match`（年份有目录但无匹配论文）、`source_failed`（来源失败导致无结果）。
_Avoid_: 空态、没搜到、零结果原因

**提示条（Notice）**:
呈现给用户的单条错误或状态提示，含发生了什么与下一步动作。
_Avoid_: 报错、toast、alert、提示语

**可重试错误（RetryableFailure）**:
外部来源临时不可用一类、重试可能成功的失败；提示条上带重试入口。
_Avoid_: 临时错误、软失败、retry

**阻塞错误（BlockingFailure）**:
重试也无法成功的失败（参数非法、功能关闭、资源不存在）；提示条只说明原因与改法。
_Avoid_: 硬失败、致命错误

**部分降级（PartialResult）**:
部分来源失败但仍有结果可用；保留结果并说明来源不完整。
_Avoid_: 部分成功、降级结果、partial
