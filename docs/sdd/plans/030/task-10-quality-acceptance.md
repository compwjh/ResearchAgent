# Task 10：质量门禁最终验收与用户交付准备

关联：Spec 030 2026-10-29 修订；依赖 Task 08 后端 PASS、Task 09 前端 PASS 及对应分端评审。
状态：已完成（2026-10-31，READY_FOR_USER）。methods E2E、五项内容rubric、三产物HTTP/hash、浏览器、后端3476及前端388全量、tester与独立architect签字均通过；准备度10/10。详见[正式验收](../../reviews/030-report-quality-acceptance-review.md)与[人工步骤](2026-10-31-manual-acceptance.md)。这不是用户已验收的声明，历史失败与当前摘要级/专家访谈限制保留。

## 目标与责任

由 tester 完成跨端验收与真实 API E2E；backend-tester/frontend-tester 提供各自精确回归结论；architect 独立复核合同、人工语义 rubric 记录、验收签字与收口材料。tester 必须独立阅读 E2E 最终 Markdown/JSON 和 Evidence refs，逐项给出下方人工 PASS/FAIL；机器结构检查不能代替语义评审。按项目 spec-acceptance-protocol 执行：自然语言入口是产品主路径，不能以 mock、单元测试、内部函数或纯结构化表单代替。

## 成功 E2E

在当前分支/部署地址上选一个可行主题并建立新鲜任务，从真实自然语言 Intake、计划审批、论文检索/选集、证据矩阵、报告合成一直到查看与下载完成。使用摘要级证据可接受，但每项方法/结果必须有对应有效证据并明确证据限制；必须证明 5 篇逐篇分析、至少 1 项跨论文比较、至少 3 条跨论文支持综合发现、CJK 正文至少 1,500、报告/Artifact/会话消息共用 report_version、正式状态只在门禁通过后产生。

把脱敏真实证据写入 docs/sdd/plans/030/artifacts/task-10/api-e2e/<run-id>/，至少记录服务 URL/端口/分支版本、起止时间、自然语言输入、关键 HTTP 请求/响应、session/task/work-item/AgentRun/report/artifact IDs、plan_version 与 report_version、状态轨迹/等待条件、实际 provider/model/fallback branch/原因、循环/工具/预算/耗时可取得值、CJK/结构/引用质量结果，以及 Markdown/HTML/manifest 的查看/下载路径。Token/cost 未提供则写 null。失败运行也保存为不可覆盖记录；不保存凭据、Cookie、原始隐藏思维链或未脱敏报告内容。

复核 Task 07 指出的读路径副作用：不再对历史样本调用 session detail/events 作为无写探测。真实新任务中的 UI/SSE 调用属于验收链路时可使用，但要将其实际请求和可能的 reconciliation/projection retry 状态变化记入状态轨迹。

### 人工语义质量 rubric（REQ-01）

先单列机器结论与人工结论。机器 PASS 只表示 schema/字符计数/批准选集、Evidence ID→paper/source-level 映射、dimension、Artifact hash/version、budget/revision 等可确定规则通过；它不证明内容真实、有意义或非重复。tester 对同一最终 E2E 产物逐项人工判定，任何一项 FAIL 则语义验收 FAIL，并记录报告段落、涉及的 paper/Evidence ID 和简短理由：

1. **逐篇忠实度**：至少 5 篇的 method/findings/limitations 有具体、互相区分的陈述，能回到所引 Evidence；来源未说明处标未知。若仅目录证据，方法/结果不得超出目录字段；摘要级证据不得补写摘要未载明的全文实验细节。
2. **比较有效性**：至少 1 项比较实际解释一个已批准维度上的差异、共同点或关系，涉及至少 2 篇论文且引用其 Evidence。把两篇摘要并排重复、但没有指出比较关系，判 FAIL。
3. **综合发现支持**：至少 3 条是跨论文推断，每条均可由至少 2 篇不同论文的有效 Evidence 支持；逐篇发现重述或只在句尾堆 ID，不算综合发现。
4. **研究缺口与未知**：缺口能从已纳入证据范围说明，未知事实不被写成肯定结论；未提供的信息明确标“来源未说明/不可用”或等价状态。
5. **非填充内容**：正文段落各自提供可辨识的信息，不以重复模板、目录卡片堆叠、改写同一空泛结论或引用清单凑 1,500 CJK。拒绝示例：给五篇逐字重复“该研究具有重要意义”作为五篇发现；重复一段通用背景来达字数；只列标题/作者/年份/引用号却声称已比较。人工记录一个代表性失败位置即可，无需另建文本相似度评分器。

Rubric 记录格式：每项 `PASS|FAIL`、对应报告章节、paper_id/Evidence ID、理由；没有逐项证据不得签 PASS。若 machine PASS 但 human FAIL，Task10 仍 BLOCKED；在已确认范围内由实现侧修 prompt/反馈并以新 `Idempotency-Key` 生成新版本，最多执行合同限定的两轮定向改写；不得改写既有版本或把人工结论伪装成 machine `quality_validation` 字段。

## 失败覆盖与回滚

用 Task08/09 定向用例确认：短于 1,500；五篇但无比较；字符达标但无三条受支持发现；无效引用/跨论文 ID；不足五篇或证据只有目录字段；模型超时/预算耗尽；两轮改写用尽；deterministic fallback；同 key 重试复用版本、新 key 主动重试生成新版本；reservation 与持久化各切点恢复；未发布 Artifact 不可列举/下载；旧报告/Artifact hash 不变。关键失败均不得产生 published Artifact 或 completed 会话消息。

Task10 在 Spec 收口时执行 Gate 要求的受影响回归与唯一全量回归，保存命令、退出码、通过数、失败数和阻塞。随后按 deploy/README 实际启动部署版本，验证 health/root 与真实报告查看/下载端点；若失败保持 Spec 实施中并记录具体阻塞，不宣称可访问。回滚使用上一个可用部署版本，保留失败证据、草稿和旧 Artifact，不删除数据库记录。

## 人工案例与准备度

只有 Agent 的自然语言 API E2E 成功、关键 Artifact 存在、没有未解决 P0/P1 后，才编写人工验收步骤。使用当前 UI 的真实按钮名与提示；每步写清点击/输入、点击后提示、等待条件、等待中状态、下一步、失败恢复。案例同时列出入口、前置条件、成功/失败判据、正文与下载位置，并将 UI 看到的 report_version 对照 API run_id/task_id/artifact_id。未现场确认的文案不得猜写，按阻塞处理。

按十项 readiness matrix 逐条 PASS/FAIL/N/A（只有明确排除范围才可 N/A）。至少 9/10 PASS、自然语言 API E2E 成功、正式关键产物存在且无 P0/P1 才能判 READY_FOR_USER；其他情况统一 BLOCKED，写明已完成步骤、真实失败证据、是否可重试和解除条件。人工交付后仍需完整验收签字、status changelog、变更日志和复盘，才可将 Spec 标记已完成。

## 本 Task 完成产物

- 不可覆盖的 API E2E Artifact（成功或失败）。
- 可独立复现的人工验收案例。
- 十项准备度矩阵、P0/P1 列表及 tester 结论。
- architect 验收签字与部署证据；最终结论仅 READY_FOR_USER 或 BLOCKED。
