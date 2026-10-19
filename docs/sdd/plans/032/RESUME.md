# Spec032 暂停交接（2026-10-19）

状态：用户切换任务，暂停至下次继续；未完成，不交付人工验收。保存代码不代表验收通过。

## 恢复基线

- 分支 `codex/spec032-final-acceptance`；整理前 HEAD `4070323`。本次只保存成果，不新开发、不跑研究请求、不部署、不 push 或合并 main。
- 定时跟进已暂停；编排试行已归档，下次使用原生子 Agent 编排。
- 历史服务端口 8000，启动命令 `PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`；恢复时重新核实进程、部署提交及 ready，不假定仍在运行。

## 已完成并有验证证据

- 自然语言 Intake 能生成计划，真实案例识别 min/max/target/budget=5，并使用实际 plan hash 批准。
- 真实 USENIX 2024 案例已走通检索、评估、覆盖检查与 5/5 可信 PDF 自动导入及索引，有真实 document/import IDs。不是所有来源和年份都已验收。
- `38a0da1`：统一 fresh、恢复与持久化完整矩阵校验，独立复审通过，86 项相关测试。
- `e83fdd6`：evaluator 的 null 聚合标记、类型校验及合法 ID 保护，独立复审通过，119 项测试；后续真实运行原 scope 错误未复现。
- `7d68342`：固定脱敏校验诊断与反馈调用时序，独立复审通过；不保存模型全文、隐藏推理或凭据。
- `4070323`：普通输出错误也发送结构化纠错反馈，独立复审通过；runtime 61、matrix 22、recovery 2 项测试。真实 evaluator、synthesizer 均出现反馈后成功的证据。
- 其他已有实现、Task 和历史提交见 README 与 `artifacts/task-14/current-execution-plan.md`；定向通过不代表全量回归通过。

## 已写完代码、下次先收验：正式报告转换修复

- 文件：`backend/app/research/application/orchestrator.py`、`tests/research/test_research_report_matrix_bridge.py`。
- 实证根因：真实 syn attempt-2 的矩阵已合法，但 runtime-owned `work_item_id` 进入 `ReportSynthesisOutput(extra="forbid")` 导致 `extra_forbidden`，未执行矩阵入库与正式报告生成。
- 最小修复：转换时仅移除 runner 已校验的 `work_item_id` 并重算 hash；没有放宽未知字段或证据合同。
- 开发验证：新增回归 1 passed，matrix bridge 23 passed，编译及 diff 检查通过；真实输出只读重放通过矩阵和 report envelope 校验（2 dimensions / 5 claims / 10 evidence / 10 cells）。
- **尚未独立复审通过**：reviewer 当时因账号用量限制中断；未部署、未跑修复后的真实 E2E。不得把保存快照或开发验证写成最终完成。
- 诊断：`artifacts/task-14/current-canonical-delivery-diagnosis.md`。

## 最后真实 E2E：保留失败证据

- 基线 `4070323`；task `6184c29c7f32577e8c44e4eeb4a3b4c4`。
- Intake、审批、检索、评估及五篇导入成功；syn 首次缺矩阵后收到反馈，第二次完成并产生候选 artifacts。
- 终态仍为 `partial / REPORT_NOT_READY`；matrix HTTP 409，正式报告 JSON/Markdown/HTML 均 HTTP 404。artifact 不能代替 canonical ResearchReport。
- 请求、响应、实体/导入 ID 和产物：`artifacts/task-14/current-research-e2e-contract-feedback-report.md` 及对应 `-evidence.json`。
- 准备度 4/10，不能要求用户人工验收。

## 下次工作顺序

1. 核对分支与其他任务的新改动，独立复审上述已写完修复，优先复用既有实现。
2. 复审通过后部署精确候选，验证首页、ready、实际模型和无刷新 reasoning-options。静态模型列表曾与缓存能力矛盾，不盲选档或改全局配置。
3. 全新自然语言五篇研究：实际计划批准 → 五篇选择/导入 → matrix 200 → 正式报告三格式非空、引用及终态正确；不修改旧任务、不伪造证据。
4. 对账 Task07 多来源逐年覆盖、Task13 会话 Skill 延续、Task15–17 Semantic Scholar 真实 API/重启证据、任务内登录/上传/重试与不可变报告新版本。未验证年份继续标未验证，不用 USENIX 单例代替全部来源。
5. 补前端真实操作与逐步人工验收材料；最终候选才跑全量回归，补最终评审签字、复盘、状态台账和部署运行验证，全部满足再标完成。

未完成事项全部留待下次；本轮不删除代码、历史报告或运行数据。
