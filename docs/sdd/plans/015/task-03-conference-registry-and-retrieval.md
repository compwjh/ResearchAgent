# 任务 03 — 建立会议配置与论文召回

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 02 条件放行
> 当前状态：`完成`

> Task02 tech-lead 结论：先实现四个内置会议的 publication search、主会过滤、去重、OpenAlex 补全和搜索会话；DBLP Venue Search/自定义会议搜索新增保持 blocked，直到取得成功 live venue/api 样本。

## 一句话目标

建立可持久化的会议配置、DBLP 会议搜索和按会议/年份召回服务，稳定返回经过主会过滤、去重并由 OpenAlex 补全的论文候选。

## 背景与前置条件

- 使用任务 02 冻结的 DBLP/OpenAlex 契约、主会样本和限流结论。
- 复用现有 HTTP 客户端、配置和文章领域对象中可兼容的部分，避免复制不安全下载逻辑。
- 本任务只负责召回和元数据，不负责最终 rerank、PDF 下载或前端。

## 数据、配置与接口

- 新增 `ConferenceSource`、`PaperCandidate`、搜索会话存储和四个内置会议种子。
- 实现 `/api/papers/conferences` 的列表、搜索、新增、修改和删除语义。
- 实现 `/api/papers/search` 的校验、DBLP 召回、主会过滤、去重、OpenAlex 补全和初排输出。
- 候选必须生成服务端 `search_id/candidate_id`，保存 24 小时，后续导入不接受客户端 URL。

### 技术复审修订门禁

- SQLite 固定 schema version、UTC 时间、主外键、`ON DELETE`、唯一索引、WAL、`foreign_keys=ON`、`busy_timeout`、显式事务和过期清理；幂等由数据库唯一约束兜底。
- 会议、搜索会话和候选的状态迁移、终态、非法迁移响应和启动恢复规则必须在 schema/测试中明确；批次计数不得作为可漂移的独立事实源。
- v1 不实现查询扩展模型；检索只使用服务端校验后的原查询。后续扩展必须另立 spec，不得改变年份/会议过滤条件。

## 实施步骤与文件边界

1. 先设计 SQLite schema、唯一约束、升级初始化和过期搜索清理，不修改现有知识库 schema。
2. 建立会议仓储和四大顶会种子；内置源不可删除，用户源的 DBLP 标识必须来自服务端 Venue Search 结果。
3. 建立 DBLP 客户端，支持编码查询、年份分页、超时、有限重试和明确 User-Agent。
4. 实现会议搜索到配置候选的映射，并保存实际 stream 和主会别名。
5. 实现论文召回和 Workshop/Poster/Demo/Tutorial 等过滤；未知类型默认不直接放行，记录可诊断原因。
6. 实现 DOI、DBLP key、规范化标题+年份+会议三级去重。
7. 建立 OpenAlex 补全器；按 DOI 优先、标题兜底，单源失败返回 warning。
8. 计算可重复的初排分数，生成搜索会话和候选 id；分页和 limit 必须受服务端上限控制。
9. 接入路由与配置开关，功能关闭时不初始化外部访问。
10. 使用本地 Ollama junior-dev 时，每个代码分派控制在最多 2 个代码文件、150 行；线上模型不受该数量上限约束，但仓储、客户端、服务、路由仍应按风险拆分并逐文件读回。

## 子代理分派

- 分派 A（`junior-dev`）：会议/搜索领域模型与 SQLite 仓储，最多 2 文件。
- 分派 B（`junior-dev`）：DBLP Venue/Search 客户端，最多 2 文件。
- 分派 C（`junior-dev`）：OpenAlex 补全与候选合并，最多 2 文件。
- 分派 D（`junior-dev`）：会议与搜索路由，最多 2 文件。
- 最小上下文为本 task、现有 `article_search.py`、领域模型和路由入口；回传后架构师读回并跑针对性测试。

## 边界与明确不做

- 空查询、空会议、非法年份、超限 limit、未知会议必须在访问外部源前拒绝。
- 严格限制并发、分页和候选池，避免一次方向查询拉取无界数据。
- 不在本任务加载 embedding/Reranker，不解析出版商 HTML，不下载 PDF。
- 不允许客户端提交任意 DBLP stream 或抓取 URL绕过会议配置。
- 不将完整摘要或查询写入默认日志。

## 验收标准

- 四个内置会议首次启动幂等创建，用户会议可搜索、新增、修改、停用和删除。
- 四个默认会议和多个年份均能返回论文，非主会样本被过滤。
- DBLP/OpenAlex 重复记录稳定合并，候选 id 不暴露下载信任边界。
- OpenAlex 故障时仍返回 DBLP 结果并附 warning；所有源失败时返回稳定错误。
- 搜索会话过期和清理行为可测试，功能开关关闭时零外部请求。

## 风险、回滚与产出

- 风险：会议出版物名称随年份变化；通过可编辑 alias 列表和冻结样本测试控制。
- 回滚：关闭功能开关并移除新增路由；独立 SQLite 状态可保留，不影响知识库。
- 产出：会议配置、召回/补全服务、搜索会话和接口测试。
- 执行结果：已完成领域模型/SQLite 仓储、DBLP publication search、OpenAlex 补全、搜索编排及内置会议/搜索 API；最终定向验收 41 passed，Tech Lead 最终签核通过。自定义会议 Venue Search 保持 blocked，导入 FK/TTL 候选快照移交 Task05。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师(自身) | 创建任务计划，状态为待执行 |
| 2026-09-04 | 架构师(自身) | 基于 Task02 条件放行，启动内置会议 publication search、过滤、去重、OpenAlex 补全与搜索会话；Venue Search 保持 blocked |
| 2026-09-04 | junior-dev / tech-lead | 完成 SQLite、DBLP、OpenAlex 与搜索编排首轮切片；Tech Lead 复核发现并推动修复跨会话主键冲突和 DBLP query 未透传两个 P0，定向测试累计 19 passed，P1 复审待完成 |
| 2026-09-04 | tester / tech-lead | Task03 API 与核心功能验收、最终技术签核通过；定向测试 41 passed。内置会议与 OpenAlex 收窄范围完成，Venue Search/custom conference blocked，导入 FK/TTL 移交 Task05 |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-015-task-03",
  "spec_id": "015",
  "title": "# 任务 03 — 建立会议配置与论文召回",
  "status": "completed",
  "priority": 100,
  "created_at": "2026-10-19T01:15:24+00:00",
  "depends_on": [
    "spec-015-task-02"
  ],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/015/task-03-conference-registry-and-retrieval.md",
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
Read: ["docs/sdd/plans/015/task-03-conference-registry-and-retrieval.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/015/task-03-conference-registry-and-retrieval.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
