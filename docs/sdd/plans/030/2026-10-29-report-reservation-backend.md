# Spec 030 Task 08：报告版本 reservation 后端交接

- 日期：2026-10-29
- 执行角色：backend-dev
- 范围：仅原子报告版本/request-key reservation 与 reservation 查询；未接入 API、Orchestrator、AgentRunner 或正式发布链。
- 代码：`backend/app/research/infrastructure/research_store.py`、`tests/research/test_report_version_reservation.py`
- 进展日志：`.codebuddy/agent-logs/spec-030/task-08/backend-dev/20261029-115328.md`

## 接口

```python
reservation = store.reserve_report_generation(
    research_task_id,
    owner_id,
    plan_version=plan_version,
    request_key=request_uuid,
    request_payload={"plan_version": plan_version, "title": title},
    work_item_input=server_built_input,  # optional
    report_version=explicit_version,    # optional; may only match an existing reservation
)
```

返回 `ReportGenerationReservation(report, work_item, replayed)`。通过
`store.get_report_generation_reservation(task_id, owner_id, request_key=uuid)` 可按任务、owner 和 UUID 查回原 reservation；未找到或 owner 不匹配返回 `None`。

`ResearchReportReservationConflict` 是可供上层映射的类型化冲突，`code` 为：

- `REPORT_GENERATION_IN_PROGRESS`：另一个 key 已有 generating reservation；异常带 `existing_report` 和 `existing_work_item_id`。
- `REPORT_IDEMPOTENCY_KEY_REUSED`：同 key 的规范化请求体或 plan version 不同。
- `REPORT_VERSION_CONFLICT`：显式版本不匹配、或新请求试图指定版本/使用非当前计划。

## 持久化与边界

- 在一个 `BEGIN IMMEDIATE` 事务中验证任务 owner、当前 plan 版本与 plan 的 active/completed 状态；先查同 key 的历史 reservation（包括终态），再检查不同 key 的 generating 冲突。
- 请求体使用排序后的紧凑 JSON 计算 SHA-256；fingerprint、request key、report id 与版本保存在同 reservation 的 WorkItem input。相同 key 和请求体返回原 report/version/WorkItem；不匹配时无写入并返回类型化冲突。
- 新版本在同一事务内取 `research_reports` 与 `research_artifacts` 的最大版本加一，写 generating ResearchReport，并绑定一个 synthesis WorkItem。仅复用同 task/plan、queued 且未绑定 report reservation 的 synthesizer；running、terminal 或已绑定行不改写。没有安全可复用项时创建 queued `synthesize_preliminary_report` / `synthesizer` 行，依赖当前 plan 下已完成的 evaluator/coverage/replan 项。
- Report 与 WorkItem 插入或更新在同一事务中提交；任一失败回滚两者。读取同 key 终态 reservation 不会重开 WorkItem。reservation 从不更新 ResearchTask 状态。无 SQL schema migration。
- `report_json.generation` 当前记录版本、key、WorkItem、路径与未发布/未运行占位信息。完整质量字段、预算账本、状态推进、Artifact/message 投影和恢复链由 Task 08 其余实现补齐；集成代码必须保留 `generation.request_key/work_item_id/report_version` 与 WorkItem input 的 `report_generation` 字段。

## 定向测试与证据

本测试全部使用 pytest 临时目录里的 research SQLite DB；artifact 版本上界用同一临时目录中的 memory/research DB 建立。无 live service、模型调用或共享业务数据库写入。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_version_reservation.py` | 0 | 17 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --collect-only -q tests/research/test_report_version_reservation.py` | 0 | 17 collected，无 collection error |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/research/infrastructure/research_store.py tests/research/test_report_version_reservation.py` | 0 | 编译通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check backend/app/research/infrastructure/research_store.py tests/research/test_report_version_reservation.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | 无 spec/task 编号违规 |
| `git diff --check` | 0 | 无空白/补丁格式问题 |

TDD RED 阶段首次收集因尚无 `ResearchReportReservationConflict` 符号而失败；添加实现后 17 项全部转绿。运行环境注意：worktree 没有本地 `.venv`；在 zsh 中 source 根 `.venv/bin/activate` 后，`python` alias 仍指向 `/opt/anaconda3/bin/python`。改用上表所列根 `.venv` 绝对路径后，默认 pytest conftest 正常加载，测试 17/17 通过。

覆盖项包括：版本读取 report 与 Artifact 最大值、同 key 同 payload 跨完成/重试返回同一身份、同 key body 不同的冲突、不同 key 生成期间冲突、相同/不同 key 并发、终态任务/WorkItem 不重开、运行中/绑定了其它 reservation 的 WorkItem 不被改写、显式版本限制、owner/current plan 状态校验、按 key owner-scoped 查询、WorkItem 插入失败回滚和 ResearchReport 插入失败时 queued WorkItem 更新回滚。

## 未覆盖与风险

- 此切片没有连接 POST/GET、Orchestrator、ResearchService executor、AgentRunner、质量验证或启动恢复；目前不能据此声称用户报告生成缺陷已修复，也不代表 Spec 030 收口。
- `report_json.generation` 是 reservation 阶段的部分身份记录；后续生成集成须补齐合同要求的完整 generation/budget 结构，并保证保存、恢复和 WorkItem input 更新不丢失 reservation key、report version 与 WorkItem ID。
- 尚未实现 generating-only 报告状态推进或 interrupted WorkItem successor 创建；本切片只确保新版本不重开旧 terminal WorkItem，恢复续跑由 Task 08 集成负责。
- 默认工作树还显示 report-quality foundation 相关文件由并行任务持有；本切片未编辑那些文件。
