# 任务 09 — 评审、部署与复盘

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 08
> 当前状态：`阻塞`

## 一句话目标

完成独立验收、开发主管签字、文档和 Git 收口，并实际启动服务验证论文检索、公开导入、批量导入和 ACM/IEEE 登录续传后再将 spec-015 标为已完成。

> 技术复审打回项必须在实现前回填并复审；在 T1–T13 未全部关闭、Spec 015 未获用户确认前，本任务不得执行。

## 背景与前置条件

- 需求评审和技术评审应在 spec 确认前已真实落盘；若仍缺失，不能用本任务补写成“事前评审”。
- 任务 02–08 必须全部完成并回填真实文件、命令、结果、风险和变更日志。
- 验收遵循 `docs/sdd/SDD-GATE-CHECKLIST.md`，主会话不代替 tester 或 tech-lead 签字。

## 数据、配置与接口

- 评审文件：`docs/sdd/reviews/015-requirement-review.md`、`015-tech-review.md`、`015-acceptance-review.md`。
- 复盘文件：`docs/sdd/retro/` 下 spec-015 对应复盘。
- 状态同步：spec、README、所有 task 与 `spec-status-changelog.md`。
- Git 目标：在 `feature/spec-015-security-paper-discovery` 做原子化本地 commit，不 push、不合并 main。

## 实施步骤

1. 核对 spec 与任务实际实现一致；若接口、范围或验收发生实质变化，停止并回到 spec 修订/重新确认。
2. 由 `tester` 按 A1–A15 执行验收，写入测试环境、命令、逐项证据、失败项和真实结论。
3. 由 `tech-lead` 做代码与安全审查，复核排序集、SSRF、凭证边界、旧数据兼容和回归结果，并在验收文档签字。
4. 缺陷按归属退回任务 03–08；修复后重跑针对性和全量测试，更新验收文档，不覆盖历史失败证据。
5. 检查三份评审、task 状态、链接、变更日志、模型登记、运行产物忽略规则和全仓冲突标记。
6. 主动完成复盘，记录数据源、登录桥接、站点解析、排序评测和多 Agent 编排的可复用经验。
7. 停止旧服务后按项目正式启动方式启动；若默认端口占用，选择可用端口并记录实际地址。
8. 验证首页、`/api/health`、知识库健康、会议列表、方向搜索、单篇公开导入、批量部分成功、知识库问答。
9. 在用户参与下复验 ACM、IEEE 登录续传；无合法访问样本则验收保持阻塞，不标完成。
10. 全部通过后把 task、README 和 spec 状态更新为完成，追加状态台账；按关注点本地 commit，不 push、不合 main。

## 子代理分派

- `tester`：独立执行验收并写 `015-acceptance-review.md`，使用 `qwen3.5:9b`。
- `tech-lead`：Code Review、风险裁决和验收签字，使用 `qwen3.8:27b-mlx`。
- 若验收发现代码缺陷，必须回到 `junior-dev` 小任务分派，不能由架构师直接代写。
- 架构师只负责门禁编排、文件读回、部署、最终状态和本地提交。

## 实时监控

```bash
tail -f deploy/run.log
curl -sS http://127.0.0.1:8000/api/health
git status --short --branch
git diff --check
```

## 验收标准

- 三份评审文档真实存在，结论明确；验收报告有 tester 结论和 tech-lead 签字。
- A1–A15 全部通过，冻结排序指标、安全矩阵和真实 ACM/IEEE 证据可追溯。
- 首页、健康检查、搜索、公开/批量导入和知识库问答在实际服务上成功。
- 所有 task 执行结果、状态、链接、spec changelog 和状态台账一致。
- 复盘已落盘，全仓无冲突标记、敏感信息和不应提交的运行产物。
- spec 状态只在上述条件全部满足后从实施中转为已完成。
- 本地 commit 符合 Conventional Commits 并关联 `spec-015`；不 push、不主动合并 main。

## 明确不做

- 不在验收未签字、真实登录未验证或测试失败时标记完成。
- 不伪造用户登录、外部下载、测试数量、覆盖率或运行地址。
- 不清理、回滚或提交其他 spec 的未归属修改。
- 不主动 push、创建 PR 或合并 main，除非用户另行授权。

## 风险与回滚

| 风险 | 处置 |
|---|---|
| 外部站点在验收时不可用 | 保留离线回归结果，真实验收标阻塞并记录重试条件 |
| 默认端口占用 | 选择可用端口启动并报告实际地址，不杀死无关进程 |
| 发现范围外需求 | 记录后续 spec，不纳入本轮“顺手实现” |
| 验收失败 | 保持实施中，退回归属 task；不转已完成 |

## 产出物与执行结果

- 产出：验收评审、开发主管签字、复盘、部署证据、状态台账和本地 commit。
- 执行结果：已完成离线收口检查与本地部署验证。全量 pytest `520 passed, 1 skipped, 5 warnings, 38 subtests`；首页 HTTP 200、`/api/health` HTTP 200 且返回 `paper_discovery_enabled`、会议列表接口可用；Reranker 因模型文件缺失按既定策略降级为 RRF。Task04 rerank/nDCG、DBLP Venue Search/自定义会议、旧 KB 物理端到端、真实 GUI/窄屏、公开 PDF 与 ACM/IEEE 合法登录仍无可验证环境，故任务保持实施中，不标记 Spec015 完成。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师(自身) | 创建任务计划，状态为待执行 |
| 2026-09-05 | 架构师（自身） | 补记用户 Chrome 的 ACM/IEEE 外站会话证据；项目 Playwright profile 尚未完成登录续传与知识库导入，Task09 保持实施中 |
| 2026-09-05 | 架构师（自身） | 重启服务后复现 DBLP `DBLP_UNAVAILABLE`，服务健康与 Playwright 健康均通过；无搜索候选时无法进入登录流程，Task09 继续保持外部数据源阻塞 |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-015-task-09",
  "spec_id": "015",
  "title": "# 任务 09 — 评审、部署与复盘",
  "status": "blocked",
  "priority": 100,
  "created_at": "2026-10-19T01:15:24+00:00",
  "depends_on": [
    "spec-015-task-08"
  ],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/015/task-09-review-deploy-retro.md",
    "docs/sdd/plans/016/artifacts/legacy-task-audit.md",
    "docs/sdd/TASK-PROTOCOL.md"
  ],
  "worktree": {
    "path": ".worktrees/spec-015",
    "branch": "feature/spec-015-security-paper-discovery",
    "mode": "per_spec",
    "base_rule": "explicit_commit"
  },
  "max_attempts": 3,
  "prompt_version": 1,
  "return_schema": "sdd-run-result/v1",
  "expected_artifacts": [],
  "validation_commands": [],
  "migration_state": "verified"
}
<!-- sdd-task-meta:v1:end -->
<!-- sdd-task-prompt:v1:begin -->
Role: backend-tester
Read: ["docs/sdd/plans/015/task-09-review-deploy-retro.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/015/task-09-review-deploy-retro.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
