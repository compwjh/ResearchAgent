# 任务 17 — 执行复用审计、验收、部署与复盘

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)
> 依赖：任务 13、14、15、16；被依赖：无
> 当前状态：`阻塞`
> 主 Skill：`.agents/skills/usenix-paper-catalog-search/SKILL.md`；公开论文导入验收的下载子步骤另按 `.agents/skills/usenix-accepted-papers/SKILL.md` 执行

## 一句话目标

由 QA 和 Tech Lead 独立证明 USENIX 增量目录、LangGraph、RAG、分页、恢复和复用约束全部成立，完成本地提交、部署、运行时验收与复盘后才允许 Spec015 收口。

## 当前证据

- Task11/12 的旧范围曾完成 `552 passed`，但不能替代新增 Task13–16 的验收。
- `docs/sdd/reviews/015-acceptance-review.md` 是旧阶段报告，必须追加本轮真实结果和 Tech Lead 签字，不能直接沿用旧结论。
- Task13 的复用审计是本轮代码评审输入；缺少审计或实际diff时不得签字。
- 用户要求本轮先只落盘文档；本任务在用户后续明确安排前保持待执行。

## 前置门禁

1. Task13–16 状态、README与Spec索引均为已完成，所有实施报告路径真实存在。
2. 所有子Agent固定返回字段已回填，缺失测试退出码/耗时/文件清单时先补文档。
3. 工作树中Spec017保持独立，不得纳入Spec015提交、验收或部署。
4. 验收开始前记录分支、HEAD、工作树、运行端口和依赖版本；不reset/stash/clean。

## 验收矩阵

| 领域 | 必须证明 |
|---|---|
| 复用 | 下载、安全、导入、批任务、身份、BGE-M3/RRF调用现有实现；无第二套同类实现 |
| 官方解析 | 四个固定样本覆盖2024 summer/fall、2025/2026 cycle；标题、摘要、可选关键词和显式链接正确 |
| 增量缓存 | 2022后搜索2022–2024只取缺失年份；同一unit并发只抓一次；重启仍命中SQLite |
| 权威合并 | USENIX字段不被DBLP覆盖；DBLP只补空值；无官方摘要的DBLP-only不展示 |
| LangGraph | 固定节点、来源并行、事件、partial/failed、节点中断恢复和幂等成立 |
| RAG | 独立collection、BGE-M3 dense+sparse、RRF、可选reranker降级、会议/年份过滤成立 |
| API/UI | POST 202、来源卡片、进度轮询、稳定错误、10条分页、迟到响应隔离、旧同步路径删除 |
| 导入 | 搜索不请求PDF；用户导入后才走官方→prepublication→严格arXiv与既有安全下载 |
| 安全 | allowlist、SSRF、重定向、日志脱敏、XSS、无凭证/Token/Cookie/敏感命令落盘 |
| 交付 | 全量测试、运行时真实USENIX检索、导入至少1篇公开PDF、健康检查、部署和本地commit |

## 思维链（可观察执行阶段）

1. QA先基于Spec A1–A20和本任务矩阵建立测试清单，不依赖开发自述。
2. 执行静态复用/安全审计、定向测试、全量回归、并发/恢复和fixture测试。
3. 启动本地服务，通过真实UI和API检索用户给定USENIX年份；记录来源进度、缓存命中和分页证据。
4. 选择一篇公开论文执行既有导入链，确认搜索期间无PDF请求、导入时才验证下载。
5. Tech Lead读取Spec复用章节、Task13审计、实际diff、QA报告和运行时证据，独立签字或打回。
6. 通过后更新所有状态、复盘和changelog，创建原子本地commit；不push、不合并main。
7. 按AGENTS.md部署并验证首页、健康接口和检索链；最终回复给出可点击地址、实际端口和启动命令。

## 子任务拆分与子 Agent 分派

### A：QA独立验收

```text
你是tester，使用qwen3.5:9b。执行Spec015 Task17完整验收，不修改生产代码。
只读取：已确认Spec015、Task13–17、Task13复用审计、Task13–16全部实现报告、实际git diff、相关测试和deploy/README.md。
允许修改：测试代码（如验收缺口需要，先按本地模型≤2代码文件/约150行拆分）、docs/sdd/reviews/015-acceptance-review.md、docs/sdd/reviews/015-task17-acceptance.md；日志写.codebuddy/agent-logs/tester-spec015-task17-<timestamp>.md。
禁止：修生产bug并继续判通过；修改Spec结论；纳入Spec017；删除数据；git reset/stash/clean/push/merge；记录Cookie/Token/Authorization。
完成状态：逐项给出A1–A20和验收矩阵的通过/不通过/阻塞、命令退出码、测试计数、运行时证据、敏感扫描和真实失败；任一硬项失败结论必须是不通过。
必须验证：Task13–16定向测试；全量pytest；node --check；git diff --check；冲突标记；敏感产物；真实服务health、搜索任务进度、两来源状态、缓存增量、10条分页和公开PDF导入。
固定返回字段：结果状态和摘要；改动文件；所有命令/退出码/计数；产物路径；A1–A20矩阵；决策依据；风险阻塞；主Agent动作；起止/耗时；可用时模型token工具统计。
```

### B：Tech Lead复用审计与验收签字

```text
你是tech-lead，使用qwen3.8:27b-mlx。对Spec015 Task13–17执行最终代码/复用/验收评审。
只读取：Spec015复用章节和A1–A20、Task13–17、Task13复用审计、实际git diff、QA报告、实现报告及直接相关代码测试。
允许修改：docs/sdd/reviews/015-catalog-tech-review.md、docs/sdd/reviews/015-acceptance-review.md签字栏、日志.codebuddy/agent-logs/tech-lead-spec015-task17-<timestamp>.md。
禁止：修改代码后自行签字；忽略未解释的第二套实现；引用聊天代替文件证据；纳入Spec017；git reset/stash/clean/push/merge。
完成状态：逐项判定复用、架构、数据迁移、并发恢复、来源权威、RAG隔离、API/UI、安全和测试；结论只能通过或打回。通过时填写真实签字、时间与证据路径。
必须验证：rg调用关系、实际diff、QA命令退出码、所有引用路径、git diff --check和敏感扫描。
固定返回字段：结论/摘要、改动文件、验证命令/退出码、产物、逐项复用审计、决策、风险阻塞、主Agent动作、起止/耗时、可用时模型token工具统计。
```

### C：失败修复循环

QA或Tech Lead打回时，主Agent必须把每个缺陷写入Task17执行结果并按文件范围重新分派junior-dev；修复后先由QA复验，再由Tech Lead重签。连续三次相同客观阻塞才允许将Spec标为阻塞。不得由主Agent直接修改代码或降低验收标准。

## 子 Agent 必须返回的字段

结论、摘要、改动文件、完整命令和退出码、测试计数、A1–A20矩阵、复用审计矩阵、运行时/部署证据路径、风险阻塞、主Agent后续动作、起止时间和总耗时；可用时模型/token/工具统计。

## 主 Agent 回填校验

1. 逐条核对QA与Tech Lead报告，不接受“同旧版本一致”“见聊天”或无退出码结论。
2. 确认所有评审文件真实存在、签字栏有明确结论，Task/README/Spec状态一致。
3. 运行全量测试、前端语法、diff、冲突和敏感扫描；记录准确计数。
4. 复核Git暂存范围只含Spec015，排除Spec017、环境文件、日志、SQLite、浏览器profile和凭证。
5. 创建符合Conventional Commits且关联spec-015的本地原子commit；不push、不合并main。
6. 启动本地服务，验证首页、健康接口和搜索任务；记录实际端口/PID/命令。
7. 完成`docs/sdd/retro/2026-09-*-spec-015-usenix-catalog-retro.md`、changelog和Spec最终状态后再报告完成。

## 实时监控命令

```bash
tail -f .codebuddy/agent-logs/tester-spec015-task17-*.md
tail -f .codebuddy/agent-logs/tech-lead-spec015-task17-*.md
tail -f deploy/run.log
```

## 测试与验收标准

- A1–A20全部有真实证据；不适用项必须有Spec依据，不能省略。
- 四个固定fixture、增量缓存、并发租约、重启恢复、partial/failed矩阵全部通过。
- 真实USENIX查询能展示两来源进度和每页10篇；重复范围命中缓存。
- 搜索阶段无PDF请求；导入一篇公开PDF后能在个人知识库检索。
- 复用审计无未解释重复实现，个人KB与目录collection完全隔离。
- 全量回归、运行时部署、安全/敏感扫描和Tech Lead签字全部通过。

## 风险、停止条件与回滚

- 外部网络不可用：fixture测试继续，但真实验收标记阻塞，Spec不得完成。
- Qdrant/Ollama依赖不可用：记录健康证据并修复部署；不得用fake替代最终运行时验收。
- 发现敏感信息：立即停止提交和部署，清除工作树产物并报告；不得把秘密写入评审。
- 回滚使用实施前Spec015检查点commit和功能开关；不reset/stash/clean，不删除已导入论文。

## 产出物

- 更新后的`docs/sdd/reviews/015-acceptance-review.md`。
- `docs/sdd/reviews/015-task17-acceptance.md`。
- `docs/sdd/reviews/015-catalog-tech-review.md`。
- Spec015增量目录复盘、状态台账、本地commit与运行时部署证据。

## 执行结果

USENIX-only 验收完成。见 [`015-task17-acceptance-usenix-only.md`](../../reviews/015-task17-acceptance-usenix-only.md)：fix-g 定向 105 passed、重点并发/过期租约/跨 DOI 合并/DBLP 与 USENIX partial 7 passed、前端契约 4 passed、Node 语法和仓库扫描通过；后端最终全量 650 passed、1 skipped、5 warnings、38 subtests。见 [`015-task15-backend-review-final.md`](../../reviews/015-task15-backend-review-final.md)，fix-h 的失败释放和过期恢复已核对。

本阶段明确不阻塞的 deferred：ACM/IEEE 合法登录、自定义会议/DBLP Venue Search、A14 排序质量标注集、真实公开 PDF 导入和 GUI/窄屏运行时证据；这些属于后续会议扩展/质量专项，不伪造为已完成。

部署证据：8000 被沙箱外既有 Python 进程占用且无法由当前环境停止，故以 `RERANKER_ENABLED=false .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8001` 启动本版本。`GET /api/health` 返回 200，首页返回 200（15,735 bytes），最小 USENIX 异步请求返回 202，search_id 为 `8988428774904044aefac7cbf9ee9d1b`。服务保持运行供用户测试；启动日志提示 Qdrant 文件目录被另一实例占用，检索将按既有降级语义运行。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-05 | 架构师（自身） | 创建Task17，固定独立QA、Tech Lead复用审计、失败修复循环、提交部署与收口门禁；未执行验收 |
| 2026-09-08 | tester / backend-reviewer | 完成 USENIX-only 跨端验收与后端复用/并发复审；将 ACM/IEEE、自定义会议、排序质量和真实导入列为后续 deferred，不作为本轮目录变更阻塞 |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-015-task-17",
  "spec_id": "015",
  "title": "# 任务 17 — 执行复用审计、验收、部署与复盘",
  "status": "blocked",
  "priority": 100,
  "created_at": "2026-10-19T01:15:24+00:00",
  "depends_on": [
    "spec-015-task-13",
    "spec-015-task-14",
    "spec-015-task-15",
    "spec-015-task-16"
  ],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/015/task-17-review-acceptance-deploy-retro.md",
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
Read: ["docs/sdd/plans/015/task-17-review-acceptance-deploy-retro.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/015/task-17-review-acceptance-deploy-retro.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
