# 任务 11 — USENIX accepted papers 与 arXiv 兜底来源

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03、05、08；被依赖：任务 12
> 当前状态：`完成`

## 一句话目标

在保留 DBLP/OpenAlex 已发表检索的前提下，为 USENIX Security 增加 accepted/prepublication 列表检索、官方 PDF 优先下载和严格 arXiv 兜底。

## 当前证据

- USENIX 列表页：`https://www.usenix.org/conference/usenixsecurity26/cycle1-accepted-papers`，页面列出 accepted 论文详情链接。
- USENIX 详情页公开提供正式 PDF 与 prepublication PDF，例如 `peng-jiaqian` 页面。
- arXiv 官方 API 使用 Atom 元数据，支持 `search_query`、`id_list`、分页；连续请求应间隔至少 3 秒并缓存。
- 当前 DBLP 在本环境可能超时；本任务的 accepted 路线必须能够独立产生候选快照。

## 前置门禁

- Spec015 补充范围已由用户确认，且 Task03/05 的候选快照、下载安全和命名契约仍有效。
- 只能访问固定的 `www.usenix.org`、`arxiv.org`、`export.arxiv.org` HTTPS origin。
- 不读取用户凭证，不复制浏览器 Cookie，不抓取任意会议网站。

## 思维链（可观察设计阶段）

1. 先用 fixture 固定列表页、详情页和两类 PDF 链接，确认解析不依赖文件名猜测。
2. 再实现来源适配器：列表 → 详情 → 显式媒体链接；每一步记录 URL 类型、阶段和稳定错误码。
3. 增加 arXiv 匹配器，只在 USENIX PDF 不可用时调用；以规范化标题、作者集合和年份计算阈值，低于阈值拒绝。
4. 将 accepted/prepublication 状态与来源链接写入候选快照，复用现有导入器和 PDF 安全校验。
5. 最后验证来源失败降级、缓存/限速、重复合并和 UI `publication_scope` 语义。

## 子任务拆分与子 Agent 分派

### A：USENIX 列表/详情解析器

- 角色：`junior-dev`；模型：`qwen3.8:27b-mlx`。
- 代码范围：最多修改 2 个代码文件、150 行（本地 Ollama 限制）；不得与 B 并行修改同一文件。

```text
你是 junior-dev，使用 qwen3.8:27b-mlx。实现 Spec015 Task11 的 USENIX accepted-papers 解析最小切片。
只读取：docs/sdd/specs/015-security-paper-discovery.md、docs/sdd/plans/015/task-11-usenix-accepted-and-arxiv-fallback.md、现有 paper discovery domain/source/parser 测试。
允许修改：最多 2 个代码文件（USENIX source/parser 及其测试），总改动不超过 150 行；不得改 API、数据库 schema、下载安全模块或前端。
禁止：任意网站爬取、猜测 PDF 路径、跟随非 allowlist 链接、读取 Cookie/密码、执行 git reset/stash/clean、覆盖用户已有修改。
完成状态：fixture 能从列表页提取 presentation URL，再从详情页提取显式正式/prepublication PDF URL、标题、作者和年份，并保留 accepted/prepublication。
必须验证：.venv/bin/python -m pytest -q <新增测试>；.venv/bin/python -m py_compile <修改的 Python 文件>；git diff --check。
结果写入：docs/sdd/reviews/015-task11-usenix-parser.md；日志写入 .codebuddy/agent-logs/junior-dev-spec015-task11-usenix-<timestamp>.md。
固定返回字段：结果状态和摘要；改动文件；测试命令、退出码和结果；产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束和总耗时；可用时记录模型、token 和工具调用统计。
先回传代码片段和测试结果，再回传说明。
```

### B：arXiv 兜底与候选来源字段

- 角色：`junior-dev`；模型：`qwen3.8:27b-mlx`。
- 代码范围：最多修改 2 个代码文件、150 行；不得与 A 并行修改同一文件。

```text
你是 junior-dev，使用 qwen3.8:27b-mlx。实现 Spec015 Task11 的 arXiv 严格匹配与来源元数据最小切片。
只读取：docs/sdd/specs/015-security-paper-discovery.md、docs/sdd/plans/015/task-11-usenix-accepted-and-arxiv-fallback.md、现有 PaperCandidate/OpenAlex/下载测试。
允许修改：最多 2 个代码文件（arXiv adapter 或候选字段及其测试），总改动不超过 150 行；不得改前端、批量状态机或无关旧文章流程。
禁止：把宽泛 arXiv 结果直接导入；无 3 秒间隔的连续请求；下载非 export.arxiv.org/arxiv.org PDF；读取凭证；git reset/stash/clean。
完成状态：USENIX PDF 不可用时才触发查询；标题+作者+年份未达到固定阈值返回 no-match；命中保留 arxiv_id、source_kind 和 publication_stage；请求结果可缓存且失败可降级。
必须验证：.venv/bin/python -m pytest -q <新增测试>；.venv/bin/python -m py_compile <修改的 Python 文件>；git diff --check。
结果写入：docs/sdd/reviews/015-task11-arxiv-fallback.md；日志写入 .codebuddy/agent-logs/junior-dev-spec015-task11-arxiv-<timestamp>.md。
固定返回字段：结果状态和摘要；改动文件；测试命令、退出码和结果；产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束和总耗时；可用时记录模型、token 和工具调用统计。
先回传代码片段和测试结果，再回传说明。
```

## 主 Agent 回填校验

1. 读回每个改动文件，确认无占位符、任意 URL 抓取和隐藏凭证。
2. 运行新增 source/parser、下载安全、批量导入和旧 KB 回归；检查候选状态没有把 accepted 标成 published。
3. 用冻结 fixture 验证正式 PDF → prepublication PDF → arXiv 的优先级、失败码和缓存限速。
4. 检查 SQLite 快照包含来源链接但不包含 query token、Cookie 或完整认证 URL。
5. 运行 `git diff --check`、冲突标记扫描和敏感信息扫描。

## 实时监控命令

```bash
tail -f .codebuddy/agent-logs/junior-dev-spec015-task11-*.md
tail -f deploy/run.log
.venv/bin/python -m pytest -q tests/test_paper_discovery_search.py tests/test_paper_download_security.py
```

## 测试与验收标准

- accepted 列表中的每个详情链接只能来自固定 USENIX origin。
- 正式 PDF 缺失或无效时，prepublication PDF 可安全回退；两者均失败才查询 arXiv。
- arXiv 仅接受标题、作者、年份严格匹配的结果，低分结果不进入候选。
- accepted/prepublication 候选在 API、文件名和知识库元数据中保持正确出版阶段。
- 同一论文跨 DBLP/USENIX/arXiv 命中只保留一个候选，并保留来源优先级。
- 请求节流、缓存、超时、重定向、SSRF、伪 PDF、超限 PDF 和日志脱敏回归全部通过。

## 风险、停止条件与回滚

- USENIX DOM 变化：fixture 解析失败立即停止，不放宽选择器到任意链接。
- arXiv 匹配歧义：停止自动导入并返回 `ARXIV_MATCH_UNCERTAIN`，不降低阈值。
- 来源限流或网络不可用：保存可重试的 source error，不阻塞 DBLP 已有结果。
- 任何凭证或非 allowlist URL 进入日志/快照：立即停止并回退到现有 DBLP/OpenAlex 路线。

## 产出物

- USENIX accepted 列表/详情 source/parser、fixture 和定向测试。
- arXiv API adapter、严格匹配测试、缓存/限速配置。
- 来源阶段字段、API 快照和 Task11 评审报告。

## 执行结果

已完成。USENIX accepted 列表/详情解析、官方 PDF→prepublication→arXiv 严格兜底、候选来源字段与 SQLite 迁移、`publication_scope` 搜索/API 接线、缓存/节流/SSRF/PDF 页校验和跨来源去重均已实现。Tech Lead 最终复评通过，QA 验收通过；全仓回归 `552 passed`（5 warnings，38 subtests）。

验收报告：`docs/sdd/reviews/015-task11-acceptance-review.md`。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-05 | 架构师（自身） | 根据用户要求创建 USENIX accepted + arXiv 第二来源任务，状态为待确认 |
| 2026-09-05 | 架构师（自身） | 用户确认后分派 Luna high junior-dev 完成 parser、arXiv、候选字段、搜索/API 接线及安全修订；Tech Lead 复评通过，QA 验收通过，任务转已完成 |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-015-task-11",
  "spec_id": "015",
  "title": "# 任务 11 — USENIX accepted papers 与 arXiv 兜底来源",
  "status": "completed",
  "priority": 100,
  "created_at": "2026-10-19T01:15:24+00:00",
  "depends_on": [
    "spec-015-task-03",
    "spec-015-task-05",
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
    "docs/sdd/plans/015/task-11-usenix-accepted-and-arxiv-fallback.md",
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
Read: ["docs/sdd/plans/015/task-11-usenix-accepted-and-arxiv-fallback.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/015/task-11-usenix-accepted-and-arxiv-fallback.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
