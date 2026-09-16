# Spec034 验收评审

日期：2026-09-16（Asia/Shanghai）
范围：Task02–Task11、收口缺陷修复、后端/前端交付、真实服务与真实研究 Smoke。

## 结论

**GO，Spec034 可收口为已完成。**

原 Task10 tester 报告记录了修复前模型输出契约与候选排序导致的 `partial`；主 Agent 随后完成 Search Worker 事实恢复、WorkItem 绑定归一化、目录 RAG 降级排序和 Task11 五篇候选报告修复，并在本次收口补齐 Intake SSE 序号、冲突按钮与计划按钮样式缺陷；仍保留 fail-closed 证据门禁。

## 验收证据

- 定向回归：Task10/Task11 与本轮前端修复集合通过（Task10 后端 `20 passed`，Spec034 前端 `31 passed`）。
- 最终全量回归：`2478 passed, 1 skipped, 5 warnings, 67 subtests`，退出码 0；测试运行时将上下文压缩设为 `COMPACTION_SUMMARY_MODE=rule`，避免依赖外部 Ollama 的非确定性摘要。
- 真实部署：临时端口 `18083`，`GET /api/health` 与页面访问成功，服务随后已停止。
- 真实流程：本机 `qwen3.8:27b-q4_K_M` 完成 Intake → Plan → Approval → 两个 Search Worker → Evaluator → Synthesizer。
- 真实任务：`research_task_id=929d24e696935fd0b6188796814a7ab9`，Session/Task 终态均为 `completed`。
- 真实 Artifact：Markdown `e3dd030b4f1d4488ab1e697b0c00364a`、HTML `d16dd1d6fcca492b9eec7aa90a6ef497`、citation manifest `c1e87022b560420190cc462bb83f801b`。
- 失败场景仍保持 `MODEL_UNAVAILABLE`/`partial` 和无 Artifact，不通过放宽校验伪造成功。

详细过程与旧 NO-GO 复验记录：[`Task10 acceptance-review-final`](../plans/034/artifacts/task-10/acceptance-review-final.md)、[`smoke-report`](../plans/034/artifacts/task-10/smoke-report.md)。

## 签字

- Tester：引用 Task10 tester 交接报告；最终成功 Smoke 由主 Agent 按固定验收步骤补充复验。
- Tech Lead：架构师（主会话代行，明确标注）。
