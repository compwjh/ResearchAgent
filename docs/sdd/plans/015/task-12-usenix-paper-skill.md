# 任务 12 — USENIX 论文来源 Skill 与跨 IDE 使用协议

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)
> 依赖：任务 11
> 当前状态：`完成`

> ⚠️ **设计更正（2026-09-05）**：USENIX skill 是**产品资产**，不属于开发工具目录 `.codebuddy/skills/`。`.codebuddy/skills/usenix-*` 两份副本已移除，仅保留 `.agents/skills/usenix-*`（供 ResearchAgent 运行时加载）；开发流程规则 `AGENTS.md` 不再收录该段。开发子代理（backend-dev / frontend-dev 等）永远不需要下论文功能，不应把产品资产放进开发技能目录。

## 一句话目标

创建两个职责隔离的可移植项目级 Skill：下载版负责用户选定论文后的 PDF 下载/验证/导入，目录版负责 USENIX/DBLP 元数据检索、增量缓存、进度和 RAG；两者不得混用。

## 当前证据

- 下载 Skill：`.agents/skills/usenix-accepted-papers/SKILL.md`。
- 目录检索 Skill：`.agents/skills/usenix-paper-catalog-search/SKILL.md`。
- CodeBuddy 薄适配器：`.codebuddy/skills/usenix-accepted-papers/SKILL.md`、`.codebuddy/skills/usenix-paper-catalog-search/SKILL.md`。
- Skill 编写规范：`/Users/wjh/.agents/skills/create-skill/SKILL.md`。
- 业务实现与下载安全由 Task11 提供，Skill 不复制业务代码。

## 前置门禁

- Task11 的 source/parser、arXiv 严格匹配和测试报告已落盘并通过。
- Skill 只能引用项目内真实存在的命令、接口和文件路径。
- 不能在 Skill 中保存密码、Cookie、Token、profile 路径内容或任意站点抓取指令。

## 思维链（可观察设计阶段）

1. 固定触发语义：用户要求“搜索/检索论文元数据”使用目录版；用户已选择论文并要求“下载/导入”使用下载版。
2. 目录版只执行页面元数据 → SQLite目录 → 独立RAG → 进度/分页，不请求、下载或验证PDF。
3. 下载版只接受冻结结果ID，执行官方PDF → prepublication → 严格arXiv匹配 → 既有安全导入/回填。
4. 固定停止条件：来源不在allowlist、匹配不确定、PDF校验失败、任务信息不足或需要凭证时停止并记录阻塞。
5. 固定交接格式：返回来源/出版阶段、目录或下载结果、错误码、产物路径和后续动作。

## 子任务与分派

本任务为纯 Skill/文档文件，不修改业务代码。由架构师依据 `create-skill` 规范落盘；若需要产品文案复核，再分派 `pm` 读取本任务和 Spec015，不得扫描全项目。

## Skill 必须包含

- 触发场景与范围：仅 USENIX Security accepted-papers 试点。
- 适用角色：ResearchAgent 主 Agent、项目 Agent、PM、Tech Lead、QA、调度器和执行 Agent；不局限于 junior-dev。
- 真实来源 URL 模板与 allowlist。
- accepted/prepublication/published 的状态区分。
- USENIX 正式 PDF → prepublication PDF → arXiv 严格匹配的顺序。
- 3 秒 arXiv 请求间隔、缓存、有限重试和稳定错误码。
- 禁止任意 URL、猜测 PDF 路径、绕过登录/验证码/付费墙和凭证落盘。
- 结果回填到 Task/SQLite 的固定字段和日志路径。
- 跨 IDE 调用示例；若没有目标子 Agent 或信息不足，必须阻塞。

## 主 Agent 校验

1. 读回两个主 Skill 和两个适配器，确认 YAML front matter 合法且职责互斥。
2. 检查所有引用路径存在，下载版只引用导入链，目录版只引用检索链。
3. 用静态 grep 确认目录版没有 `download_candidate`、`_get_pdf`、PDF GET/HEAD/Range 或 Cookie/Authorization/password/token 示例。
4. 运行 Skill 文档链接检查和 `git diff --check`。

## 验收标准

- 在 Codex、CodeBuddy 或其他支持项目 Skill 的 IDE 中，搜索请求命中目录版，下载请求命中下载版；Task13–17只引用目录版。
- 下载版不要求重新理解完整项目，不会把 accepted 论文误标为 published；目录版不触碰PDF。
- 来源失败、匹配不确定或缺少目标子 Agent 时停止并返回固定阻塞字段。
- Skill 本身不触碰用户 Chrome profile、Cookie 或认证内容。

## 风险、停止条件与回滚

- Task11 未通过时下载版保持阻塞；Task13–17未确认时目录版只允许文档评审。
- 任一 Skill 引用不存在路径或跨越职责边界时停止，先修 Task 文档契约。
- 回滚只恢复 Skill/适配器文档，不修改业务代码和用户已有文件。

## 产出物

- `.agents/skills/usenix-accepted-papers/SKILL.md`（下载与导入版）
- `.agents/skills/usenix-paper-catalog-search/SKILL.md`（目录元数据版）
- `.codebuddy/skills/usenix-accepted-papers/SKILL.md`（下载适配器）
- `.codebuddy/skills/usenix-paper-catalog-search/SKILL.md`（目录检索适配器）
- Skill 静态校验报告。

## 执行结果

已完成历史交付。本轮已将项目能力拆为下载/导入版和目录元数据检索版，并创建对应 CodeBuddy 薄适配器；Task13–17 指向目录版，搜索阶段禁止下载/验证PDF。新目录流程的业务实现和运行时验收仍由 Task13–17 负责，不能因 Skill 文档已落盘而提前宣称完成。

验收报告：`docs/sdd/reviews/015-task11-acceptance-review.md`。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-05 | 架构师（自身） | 创建 USENIX accepted 论文来源 Skill 任务，状态为待确认 |
| 2026-09-05 | 架构师（自身） | 用户澄清 Skill 属于 ResearchAgent 项目级能力；创建主 Skill 与 CodeBuddy 适配器并完成静态/跨 IDE 验收，任务转已完成 |
| 2026-09-05 | 架构师（自身） | 根据待确认的 Task13–17 文档更新主 Skill：区分元数据发现与用户导入，指向新增任务，禁止搜索阶段 PDF 探测和重复基础设施；仅更新协议文档，未执行新流程代码 |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-015-task-12",
  "spec_id": "015",
  "title": "# 任务 12 — USENIX 论文来源 Skill 与跨 IDE 使用协议",
  "status": "completed",
  "priority": 100,
  "created_at": "2026-10-19T01:15:24+00:00",
  "depends_on": [
    "spec-015-task-11"
  ],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/015/task-12-usenix-paper-skill.md",
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
Read: ["docs/sdd/plans/015/task-12-usenix-paper-skill.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/015/task-12-usenix-paper-skill.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
