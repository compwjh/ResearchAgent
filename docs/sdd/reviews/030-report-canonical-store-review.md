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

## Startup successor / rebind CAS 独立复审（2026-10-29）

**结论：PASS；本次未发现新增阻塞。** 此切片评审 `rebind_report_generation_successor` 对“WorkItem 已完成、但 Orchestrator 尚未保存 canonical report”以及 startup audit interrupted 两种恢复切点的 CAS 与 ledger 行为。上方初始 HIGH BLOCK 及其修复记录保留为历史；reservation identity 和本次 successor/rebind 均已复核通过。

### 复核结果

- owner/task、当前 plan、plan 行状态、report/task/version、canonical generation identity、request key 均在同一个 `BEGIN IMMEDIATE` 事务内验证；只接受仍为 `generating` 的 canonical report。报告行的原 report JSON 参与条件更新，generation 当前 WorkItem ID 则作为应用层 CAS token（[research_store.py](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:6644)）。
- 仅允许当前绑定的 synthesizer WorkItem 为 `interrupted` 或 `completed` 时换绑。旧 WorkItem 行不重开、不覆盖其终态或 output；新行复制必要的 synthesis 输入并重新盖 store-owned 身份，状态为 `queued`，绑定同一个 report、report version、plan version 和 request key。对应实现见 [rebind_report_generation_successor](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/backend/app/research/infrastructure/research_store.py:6612) 和 [completed checkpoint 回归用例](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/tests/research/test_report_canonical_persistence.py:504)。
- 只更新 `generation.work_item_id`，不改变 report status、revision、stage、rewrite count、budget 或 claims。claims 中旧 `work_item_id` 保留为历史使用记录。相同 successor 的重放只读返回 `replayed=True`；错误 predecessor、已被竞争者换绑、未知或重复 successor ID 均 fail closed。
- 多次恢复可沿链重新绑定；每个先前 WorkItem 保持 interrupted/completed 终态，reservation report version 与 ledger 不变。`BEGIN IMMEDIATE` 串行化竞争事务；不同 successor ID 同时争用同一旧绑定时只允许一个获胜，败者不会留下 WorkItem 行。

### 验证

- `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_canonical_persistence.py` — 退出码 0，**26 passed in 0.58s**。
- 独立 SQLite 探针：同 successor 并发重放结果为一个新绑定、一个 `replayed=True`；仅存在一条 successor，已完成 predecessor 的状态及 output 保持不变。
- 独立 SQLite 探针：不同 successor 并发竞争结果为一个成功、一个 `ResearchReportGenerationStateConflict`；report 绑定获胜 ID，败者 ID 没有 WorkItem 行。
- 独立 SQLite 探针：对新 successor 再次 interrupted 后链式 rebind 到第二个 successor，仍为 report version 1，两个 predecessor 均保持 interrupted。
- 测试中的 completed checkpoint 场景也确认旧输出保持原样，generation claim 继续指向旧 WorkItem；budget/store-state ledger 不重置。
- 未运行全量测试、部署或 Git 操作。本次未改生产代码或测试。

**当前 canonical store review：PASS。** 原始 BLOCK 仍保留在历史章节；其身份校验缺口已关闭，successor/rebind CAS 无新增问题。
