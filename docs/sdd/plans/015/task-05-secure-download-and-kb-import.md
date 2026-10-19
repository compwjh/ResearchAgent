# 任务 05 — 实现安全下载、规范命名与知识库导入

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 03
> 当前状态：`完成`

## 一句话目标

把服务端论文候选安全地下载为真实 PDF，按“年份-会议-标题”规范命名，并通过统一知识库导入服务完成可恢复的元数据、文件和索引交付。

## 背景与前置条件

- 复用现有 `article_download.py` 的流式下载和 PDF 魔数校验，以及 `/api/kb/upload` 背后的入库能力。
- 当前知识库部分流程假设物理文件名为 `{paper_id}.pdf`，本任务必须引入路径解析兼容层，不能直接改名导致重建/删除失效。
- 输入只接受任务 03 搜索会话中的候选；不得信任客户端 URL、标题或会议名。

> “原子化交付”按 saga/补偿语义落地：文件、JSON、v1 Qdrant 和 v2 异步任务没有跨介质事务；每阶段必须记录 commit point、失败补偿和启动对账。

## 数据、配置与接口

- 增加统一 `import_candidate()` 服务，输入服务端候选与任务 id，输出 `paper_id`、`stored_name` 和真实索引状态。
- 扩展 `PaperRecord` 的可选论文元数据和物理文件名字段。
- 建立稳定错误码：`PAPER_ALREADY_EXISTS`、`PDF_NOT_FOUND`、`LOGIN_REQUIRED`、`DOWNLOAD_TIMEOUT`、`DOWNLOAD_BLOCKED`、`INVALID_PDF`、`PDF_TOO_LARGE`、`KB_IMPORT_FAILED`。
- 文件名规则严格按 spec 执行，唯一性不依赖展示标题。

## 实施步骤与文件边界

1. 抽取知识库统一导入入口，使上传和论文导入共享验证、保存、记录和索引逻辑；保持原上传接口兼容。
2. 为 `PaperRecord` 增加可选元数据和 `stored_name`，建立旧记录路径回退：优先记录路径，缺失时使用原 `{paper_id}.pdf`。
3. 实现 DOI、DBLP key、规范标题组合键查询；下载前先查一次，写入锁内再查一次。
4. 实现安全 URL 策略：禁止自动跟随重定向；每跳仅允许 HTTPS、默认端口和最小域名 allowlist，拒绝用户信息、混淆/非标准 IP、IPv4-mapped IPv6、loopback/private/link-local/multicast/reserved/unspecified 地址；解析后的公共 IP 必须绑定到实际连接或复核 peer IP，防止 DNS rebinding。
5. 复用流式下载并限制超时、重定向、响应大小；临时文件必须位于受控目录。
6. 校验 HTTP、Content-Type、`%PDF` 魔数和 PDF 解析页数；任一失败不进入知识库。
7. 实现规范文件名函数，覆盖非法字符、Unicode、空标题、超长、保留名和同名冲突。
8. 保存文件、元数据和索引：v1 索引成功后条目标记 `completed`；v2 单独记录异步索引事件，失败不得撤销 v1 可检索论文；任一未完成阶段不得显示 `completed`。
9. 成功后删除临时文件；失败清理未验证文件并保留任务错误信息，不记录敏感 URL 参数。
10. 更新重建、删除、列表和引用所需的路径解析，不破坏旧记录。

## 子代理分派

- 分派 A（`junior-dev`）：安全 URL 校验与下载适配，最多 2 文件。
- 分派 B（`junior-dev`）：文件命名与去重服务，最多 2 文件。
- 分派 C（`junior-dev`）：`PaperRecord` 兼容扩展与路径解析，最多 2 文件。
- 分派 D（`junior-dev`）：统一知识库导入入口与论文候选适配，最多 2 文件。
- 每次分派要求先回传代码、后说明；架构师读回后执行静态检查和针对性测试。

## 边界与明确不做

- 禁止任意 URL、内网地址、DNS rebinding 后目标和跨协议重定向。
- 非 PDF、HTML 登录页伪装 PDF、加密不可读 PDF、零页 PDF 和超限 PDF 均拒绝。
- 同名不同 DOI 不覆盖；相同论文并发导入只允许一个成功。
- 不在本任务实现 Playwright、批量调度或前端。
- 不下载附件、代码、数据集，不使用文献互助或绕过访问控制。

## 验收标准

- 公开 PDF 可实际下载、规范命名、写入知识库并参与检索。
- SSRF 测试覆盖 IPv4/IPv6 loopback、私网、link-local、重定向和非 HTTPS。
- 伪 PDF、HTML、超大文件、超时和中途断流均不留下成功记录。
- 重复和并发导入幂等，下载前和写入前两次检查真实生效。
- 新旧物理文件名记录均可列出、重建、引用和删除。
- v1/v2 索引状态真实，索引失败不会返回错误的 v1 完成语义；孤儿文件/记录可由启动对账恢复。

## 风险、回滚与产出

- 风险：重构上传入口影响现有知识库；必须用原上传全链路回归和旧数据样本保护。
- 回滚：关闭论文检索入口；保留已成功导入记录，不迁移或删除旧文件。
- 产出：安全下载器、命名/去重、统一导入服务、兼容路径和测试。
- 执行结果：已完成单篇安全下载、规范命名/身份去重、PaperRecord 路径兼容、固定服务端 allowlist、失败补偿和单篇导入 API；定向回归 150 passed，修复项精确回归 11 passed，并发幂等 10/10 轮通过。批量任务与登录续传移交 Task06。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师(自身) | 创建任务计划，状态为待执行 |
| 2026-09-04 | 架构师 / junior-dev | Task03 完成后启动 Task05；安全 URL 校验切片完成，规范命名切片实施中；Venue Search、Playwright 与批量流程不在本任务前置范围 |
| 2026-09-04 | junior-dev | 完成论文身份键与规范文件名切片；开始实际 HTTP 安全下载适配，继续保持不自动跟随重定向 |
| 2026-09-04 | junior-dev | 完成安全下载适配、PaperRecord 兼容与注入式 `import_candidate()`；启动单篇导入 API 接入 |
| 2026-09-04 | junior-dev / tester / Tech Lead | 完成安全修复（固定 allowlist、孤儿清理、向量补偿、DBLP key、Content-Type）；150 passed，Task05 技术复核与验收均通过 |
<!-- sdd-task-meta:v1:begin -->
{
  "schema_version": 1,
  "task_id": "spec-015-task-05",
  "spec_id": "015",
  "title": "# 任务 05 — 实现安全下载、规范命名与知识库导入",
  "status": "completed",
  "priority": 100,
  "created_at": "2026-10-19T01:15:24+00:00",
  "depends_on": [
    "spec-015-task-03"
  ],
  "required_gates": [],
  "agent_role": "backend-tester",
  "required_capabilities": [
    "read",
    "edit",
    "shell"
  ],
  "allowed_paths": [
    "docs/sdd/plans/015/task-05-secure-download-and-kb-import.md",
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
Read: ["docs/sdd/plans/015/task-05-secure-download-and-kb-import.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Allowed paths: ["docs/sdd/plans/015/task-05-secure-download-and-kb-import.md", "docs/sdd/plans/016/artifacts/legacy-task-audit.md", "docs/sdd/TASK-PROTOCOL.md"]
Forbidden: do not invent metrics, claim unsupported evidence, expand scope, edit completed/partial/unverified legacy sources, or push/merge/reset/stash/clean.
Validation: none
Result: write {{RESULT_PATH}} and follow the complete `sdd-run-result/v1` schema in TASK-PROTOCOL.md. Include schema, run_id, task_id, task_hash, prompt_hash, outcome, summary, changed_files, artifacts, commands, tests, decisions, risks, blockers, main_agent_actions, started_at, ended_at, duration_ms, model, token_usage, tool_call_count, and log_paths. Unknown historical metrics remain null.
Return schema: sdd-run-result/v1
Objective: preserve audited scope.
Read-only audit: do not repeat business implementation.
<!-- sdd-task-prompt:v1:end -->
