# 任务 09 — 评审、部署与复盘

> 关联：[spec-014](../../specs/014-kb-reranker.md) ｜ 索引：[README](./README.md)
> 依赖：任务 07、08
> 当前状态：`完成`

## 一句话目标

完成 SDD 三道门禁、真实运行时验收、服务部署、文档收口和本地提交，使 spec-014 达到可交付状态。

## 实施步骤

### Gate 1–2：实现前评审

1. spec 确认前由 `tech-lead` 分别生成 `014-requirement-review.md` 与 `014-tech-review.md`。
2. 任一评审打回，则 spec 保持/退回 `待确认`，修订后重新评审。
3. 两项通过且用户明确确认后，spec 才转 `已确认`，随后记录 `实施中`。

### Gate 3–4：测试与验收

4. 汇总 Task 07 的单测、质量、性能、内存和降级证据。
5. `tester` 生成 `docs/sdd/reviews/014-acceptance-review.md`，结论只能为通过/不通过。
6. `tech-lead` 阅读真实实现、测试和报告，完成验收签字；未签字不得转完成。

### Gate 5：部署与运行验证

7. 使用实际部署脚本启动 Reranker 与 FastAPI；若默认端口占用则选择可用端口并记录。
8. 验证首页、`/api/kb/health`、真实知识库问题、引用和 Langfuse rerank span。
9. 停止 Reranker 再提问，验证 RRF 降级；随后恢复服务并复测。

### 收口

10. 更新 spec 的评审记录、任务状态、实际改动、验证结果与变更日志。
11. 更新 `spec-status-changelog.md`，满足所有 DoD 后将 spec 转 `已完成`。
12. 生成 `docs/sdd/retro/2026-09-xx-spec-014-reranker-retro.md`，记录兼容模型、运行时、质量探针和跨分支集成经验。
13. `git status` 审核范围，在 feature 分支做关联 `spec-014` 的本地原子 commit；不 push、不合并 main。

## 子代理分派

- 需求/技术/验收签字：`tech-lead`，`gpt-5.6-luna`，高推理。
- 测试与验收报告：`tester`，`gpt-5.6-luna`，高推理。
- 发现代码缺陷时退回 `junior-dev` 窄任务修复，不由架构师越权代行。
- 所有角色产出必须落盘；失败按门禁规则重试并保留日志。

## 验收清单

- 三份评审文档存在且结论真实，验收签字已填。
- Spec A1–A12 全部有命令或运行记录支持。
- 全量测试、覆盖率、MRR@5、延迟与内存结果已记录。
- 服务实际运行，最终回复包含可点击地址、实际端口和启动命令。
- changelog、任务状态、复盘、引用路径全部一致且可访问。
- 冲突标记扫描为 0，提交不含 `.env`、模型、日志、PID 或他人未完成改动。

## 明确不做

- 不跳过独立评审或用“测试通过”代替开发主管签字。
- 不主动 push、创建 PR、合并 main 或删除其他 worktree。
- 不在服务未真实启动时声称部署完成。

## 风险、回滚与产出

- 任一门禁失败：保持真实状态，退回对应任务，不强行收口。
- 运行时阻塞：写明具体错误与可执行解决命令，不声称已部署。
- 产出：三份评审、运行记录、更新后的 spec/changelog、复盘与本地 commit。
- 执行结果：已完成联合启动和健康验证（FastAPI `8000`、Reranker `11435`、Langfuse `3000` 均可达），并验证 Reranker 长片段 `ubatch-size=1024` 修复、启用与停服降级。四组合真实 KB ask 与恢复闭环均已补齐，验收报告结论为通过，tech-lead 签字已填，复盘已落盘，Spec 014 已转 `已完成`。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-02 | 架构师(自身) | 创建任务计划，状态为待执行 |
| 2026-09-02 | 用户 | 指定剩余任务使用 Luna 高推理，等待 Task 08 前置满足 |
| 2026-09-04 | 架构师(主会话) | 定位并修复 `create_chat_model` 默认 `reasoning=True` 回归（`6daa498`），补 2 条契约测试，全量 `351 passed` |
| 2026-09-04 | 架构师(主会话) | 用 `deepseek-coder-v2:16b` 复测 KB ask 与普通聊天，均完整 `done`，解除关键阻塞第 2 项 |
| 2026-09-04 | 架构师(主会话) | 补齐 tech-lead 签字、复盘、spec 状态与状态台账，Spec 014 转 `已完成` |

## 补充执行结果（2026-09-04）

验收报告已由 tester 更新，真实证据包括：

- 全量回归 `346 passed`，Spec 014 专项回归 `100 passed`。
- Reranker 启动参数加入 `--ubatch-size 1024` 后，真实 KB ask HTTP 200；SSE 已观察到 `meta/stage/citations`。
- Langfuse `events_full` 已读到真实成功和降级 `kb.rerank` 事件，并能与 `kb.retrieval` 父阶段按 trace 关联；成功样本 `input_count=20/output_count=1`，停服样本 `degraded_reason=connection`。
- Langfuse Web、FastAPI `/api/health`、`/api/kb/health` 和 Reranker `/health` 均已取得 HTTP 200；停服期间 KB ask 仍开始返回 SSE，恢复后 probe/health 通过。

收口判定仍为**阻塞**：off/off 两次真实 KB ask 分别在 120/330 秒内未出现 `done`、以及在 citations 后因 Ollama HTTP 400 进入 error；四种组合没有全部形成独立完整的 `KB ask -> trace/span -> done` 证据，缺少 tech-lead 验收签字和 Spec 014 复盘文档。因此不将 Spec 014 改为 `已完成`，不执行本任务要求的最终本地提交。

## 最终执行结果（2026-09-04 收口）

上述两个阻塞的根因已定位并修复，收口条件全部满足。

### 阻塞根因

`run_chat` 原有默认 `think=True`，且 `langchain_ollama` 会把 `reasoning` 映射为请求体 `think` 字段（`"think": kwargs.pop("reasoning", self.reasoning)`）。实测 `deepseek-coder-v2:16b` 的 `/api/chat`：`think=true` → HTTP 400 `does not support thinking`；`think=false` / `null` / 不传 → HTTP 200。因此：

- `qwen3.5:9b` 被强制开启思维链，120/330 秒窗口内无 `done`；
- 换成 `deepseek-coder-v2:16b` 则 `think=true` 直接 400，SSE 在 `citations` 后进入 error。

### 修复与复核

1. `8c1c3ae`：KB 问答显式 `think=False` / `reasoning=False`。
2. `6daa498`：`8c1c3ae` 顺带把 `create_chat_model` 的 `reasoning` 默认值改为 `True`，导致所有仅传模型名的调用方（`article_agent` 意图分类、`download_paper_skill`、`kb/retrieve.py`、langchain 聊天链路）都被强制下发 `think=true`。已改回默认值 `None`（仅显式传入 `True`/`False` 时才下发），默认路径恢复改动前行为，并新增 2 条契约测试锁定该语义。
3. 复核：`deepseek-coder-v2:16b` 的 KB ask HTTP 200 且 SSE 完整收口到 `done`（259 token，**0 个 error 事件**）；普通聊天同样 HTTP 200 收口到 `done`；全量回归 `351 passed, 5 warnings, 29 subtests passed`。

### 收口产出

- 三份评审：`014-requirement-review.md`、`014-tech-review.md`、`014-acceptance-review.md`（含 tech-lead 签字）。
- 复盘：`docs/sdd/retro/2026-09-04-spec-014-reranker-retro.md`。
- `docs/sdd/specs/014-kb-reranker.md` 状态转 `已完成`；`spec-status-changelog.md` 已追加。
- 本地原子 commit（不含 `.env`、模型、日志、PID，也不含他人正在编辑的 Spec 015 文档）。
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-014-task-09",
  "spec_id": "014",
  "title": "# 任务 09 — 评审、部署与复盘",
  "status": "completed",
  "priority": 100,
  "created_at": "2026-10-19T01:13:51+00:00",
  "depends_on": [
    "spec-014-task-07",
    "spec-014-task-08"
  ],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/014/task-09-review-deploy-retro.md",
    "docs/sdd/plans/016/artifacts/legacy-task-audit.md",
    "docs/sdd/TASK-PROTOCOL.md"
  ],
  "worktree": {
    "path": ".worktrees/spec-014",
    "branch": "feature/spec-014-kb-reranker",
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
Read: ["docs/sdd/plans/014/task-09-review-deploy-retro.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/014/task-09-review-deploy-retro.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
