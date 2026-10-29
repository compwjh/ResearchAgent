# Spec030 Task08 canonical report store writer 后端评审

日期：2026-10-29
范围：research_store.py 新增 save_report_generation_output 及 test_report_canonical_persistence.py。只读评审；未改业务代码或测试。

## 结论

**BLOCK** — 发现 1 项 HIGH 级 reservation 身份校验缺口：writer 未校验 WorkItem JSON 中重复保存的报告/计划身份字段，且未校验嵌套 reservation 的 plan_version。因此 WorkItem 输入身份与 canonical reservation 不一致时，writer 仍能成功落库。

其余重点项通过：写入使用单个 BEGIN IMMEDIATE 事务与旧 report_json 条件 CAS；只允许 generating 行新写；保留 budget 和 store_state 的 stage、rewrite_count、claims、limits；owner/task/report row/数据库列 plan 与 reservation 中的 report ID、version、request key 有校验；相同内容的终态 replay 不写入，差异终态写入会冲突。

## 问题

### [HIGH] canonical writer 未核对 WorkItem 输入中的完整 reservation 身份

**文件：** [research_store.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:6177)

_report_reservation_work_item 检查了 WorkItem 数据库列中的 plan_version，并从 input_json.report_generation 核对 report_id、report_version、request_key。它没有核对该嵌套对象的 plan_version，也没有核对 input_json 顶层的 report_id、report_version、request_key、plan_version。这些顶层字段会被实际调用方读取；例如上下文 Builder 从 work_item.input_params["report_version"] 取报告版本（[orchestrator.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/application/orchestrator.py:3809)）。

我用临时数据库独立探针将 WorkItem input_json 顶层 report/plan 版本和嵌套 report_generation.plan_version 改成 99，保留嵌套 report ID/version/request key；随后以原 reservation version 1 调用 writer。Writer 接受了不一致绑定并把 canonical 内容写入 version 1（revision 变为 1）。这允许由错误 report_version 输入执行的结果被存入另一个 canonical reservation。

**修复方向：** _report_reservation_work_item 应校验顶层及嵌套的 report_id、report_version、plan_version、request_key 均与 canonical report 和 generation reservation 一致；request_fingerprint 也应保持完整性校验。增加测试篡改每个重复字段，确认读取 reservation 与 canonical writer 都 fail closed。

## 验证

- 命令：/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_canonical_persistence.py
- 结果：退出码 0；5 passed in 0.31s。
- 并发 CAS 临时库探针：两条同 revision 不同内容并发写入，一个成功推进到 revision 1，另一个抛出 ResearchReportGenerationStateConflict。
- 终态 replay 临时库探针：draft 终态后相同内容 replay 返回 replayed=True，revision 保持 6。
- Reservation 绑定临时库探针：重复身份字段不一致时 writer 接受了写入，复现上述阻塞项。
- 未运行全量测试、部署或 Git 操作。

## Review Summary

| Severity | Count | Status |
|----------|------:|--------|
| CRITICAL | 0 | pass |
| HIGH | 1 | block |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **BLOCK** — 1 HIGH reservation identity issue must be resolved before this store writer can pass review.

## Reservation identity 修复复审（2026-10-29）

**复审结论：PASS（原 BLOCK 项已关闭）。** 上文首次 BLOCK 与原始复现保留作为历史记录；作者修复后复核确认共享 binder 会校验 canonical report 行的 report_id/version/plan_version、generation 版本与 request_key、WorkItem 数据库列 plan、WorkItem 顶层和嵌套 reservation 的 report_id/version/plan_version/request_key，以及有效格式且顶层/嵌套一致的 request_fingerprint。reservation input 会覆盖 caller 提供的顶层 plan_version/request_fingerprint，绑定为 store-owned 值。读 reservation 与 canonical write 共用该检查，身份不一致时 fail closed。实现见 [research_store.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:6155)。

- 定向测试：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_canonical_persistence.py tests/research/test_report_version_reservation.py`，退出码 0，`32 passed in 0.62s`（canonical persistence 15 项，reservation 17 项）。
- 独立身份探针：逐一修改顶层/嵌套 report_id、report_version、plan_version、request_key、request_fingerprint 共 10 种字段；reservation reader 与 canonical writer 均拒绝全部篡改。额外传入冲突的 caller 顶层 plan_version/fingerprint，reservation 输出仍与 store-owned report plan 和计算指纹一致。结果 PASS。
- 原有 budget ledger 保留、CAS、终态 exact replay 证据仍见上文首次评审与定向用例。
- 未运行全量测试、部署或 Git 操作。

首次 Review Summary 中的 BLOCK 保留为修复前结论；按本次独立复审，canonical reservation 身份不一致写入问题已修复，当前 canonical store 范围通过。
