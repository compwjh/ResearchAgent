# Spec022 Task08 最终后端评审报告

## 最新复核结论（共享安全原语候选）

**GO（P0=0，P1=0，P2=4）**。

上一轮三个功能性阻塞项已关闭，随后发现的跨上下文架构回归也已关闭：URL/peer 安全原语已抽取到 `backend/app/core/url_security.py`，Article Assistant、Paper Discovery infrastructure 和 USENIX source 均改用 core；`paper_download_security` 仅保留兼容重导出。模块边界合同、受影响后端集合和论文安全集合本轮均通过。仍保留 4 项非阻塞历史 P2；本报告只代表 backend reviewer，不替代 Task08 tester 的全量回归、部署和跨端验收。

本轮只读复核，未修改业务代码、未修改测试、未运行前端、未部署。

## 修复项复核

### 已关闭：Article Assistant SSRF 防护

- `article_download.py` 已改为手动逐跳请求，使用服务端配置的 download/allowed-host allowlist；候选自身 `pdf_url/article_url` 不会扩展 allowlist。
- 初始 URL、HTML 链接和每个重定向目标都经过 scheme/host/端口、DNS 公网地址和重定向校验；实际连接 peer 必须匹配解析地址；未配置来源时在发网前 fail-closed。
- 私网候选、未配置公网候选、重定向至私网和下载清理均有新增测试，相关 Article Assistant 与 paper download 集合通过。

### 已关闭：SystemRule fail-closed

- `_system_rule()` 校验 owner/content/enabled/ISO 时间戳，`get_system_rule()` 将解析/行形状异常统一包装为 `SystemRuleUnavailableError`。
- 新增 repository 与 `/api/system-rule` malformed timestamp 测试，稳定返回 `503` 和 `SYSTEM_RULE_UNAVAILABLE`。

### 已关闭：Task05 global 门禁基线

- 未绑定原文 `记住多条` 的 classifier global 建议不再自动写 global memory，测试改为断言 `pending_confirmation` 且 global memory 为空；原文授权门禁未被放宽。

## 上一轮 P1 阻塞项（已关闭）

### P1-1：跨上下文直接依赖破坏 Spec017 模块边界

证据：

- `backend/app/article_assistant/infrastructure/article_download.py:11-20` 直接导入 `backend.app.paper_discovery.domain.paper_download_security` 的 `validate_url`、`validate_redirect_target`、`validate_peer_ip` 等内部实现。
- `tests/test_api_module_boundaries.py:149-175` 明确规定：业务上下文不得 import 其它上下文的 `domain` / `infrastructure`；跨上下文协作只能经对方 `application` 入口或已定义 port。
- 上一轮复核曾得到 **77 passed, 1 skipped, 1 failed**，失败为 `test_contexts_do_not_import_other_contexts_internals`，报告 `article_download.py:11:backend.app.paper_discovery.domain.paper_download_security`；本轮该 import 已移除。

影响（上一轮）：虽然当时的复用关闭了 SSRF 功能缺口，但把 Article Assistant 绑到 Paper Discovery 的 domain 内部，破坏了已冻结的上下文依赖方向。该失败是现有架构合同的确定性回归；当前已通过共享 core 抽取关闭。

建议（已执行）：将纯 URL/peer 安全原语抽取到共享基础层 `backend/app/core/url_security.py`，由各上下文直接依赖 core；Paper Discovery domain 保留兼容重导出以维持旧测试/调用方兼容。

## 评审范围与依据

- `docs/sdd/specs/022-project-conversation-memory.md`
- `docs/sdd/plans/022/task-08-review-regression-deploy.md`
- Task02–Task07、Task09、Task10 的计划及后端实现/评审/测试交接报告
- 当前候选基线 HEAD：`ab3e872`（`feature/spec-022-memory-mvp`）+ 当前工作树 Task08 后端修复 diff（尚未提交）
- 当前 `backend/**` 相对 `main` 的既有变更，加上本轮未提交的共享安全 core、Article Assistant、Paper Discovery 和 MemoryRepository 修复；工作树还包含父会话的 SDD/前端/测试修改，本报告只核对 backend 与相关后端测试

## 首轮 P1 记录（已关闭，保留审计轨迹）

### P1-1：旧 Article Assistant 下载/探测链路绕过 SSRF 防护

证据：

- `backend/app/article_assistant/infrastructure/article_download.py:32-72` 的 `probe_pdf_url()` 直接对候选或配置 URL 调用 `httpx.stream(..., follow_redirects=True, trust_env=False)`；HTML 中的 `href` 经过 `urljoin()` 后在 `:56-61` 递归探测，没有 allowlist、DNS 公网 IP 校验、重定向逐跳校验或对端 IP 复核。
- `article_download.py:75-107` 的 `download_article()` 对候选 URL 直接跟随重定向下载，同样没有目标/对端校验。
- `backend/app/platform/settings/article_assistant_settings.py:32-38` 只检查字符串以 `http://` 或 `https://` 开头，因此 `127.0.0.1`、RFC1918、link-local 或任意内网域名均可进入配置。
- `backend/app/api/routes_article.py:222-307` 将上述探测和下载暴露给现有 `/api/agent/articles/*` 入口；`PUT /api/agent/settings`（`:58-74`）接受并持久化下载来源。

对照：`backend/app/paper_discovery/infrastructure/paper_download.py:186-309` 已有 allowlist、DNS/公网 IP、重定向和 peer 校验，相关 `tests/test_paper_download.py`、`tests/test_paper_download_security.py` 通过；但该安全实现未被旧 Article Assistant 路径复用，所以不能覆盖上述入口。

影响：攻击者只需提交/配置一个 HTTP(S) URL，服务端即可探测或请求本机及内网地址，并可通过重定向改变最终目标；这违反 Spec022 对“现有论文/文章下载接口兼容且 SSRF 安全”的要求。需要在旧入口统一复用安全下载器或引入等价的逐跳 URL/解析/peer 校验，并补充私网、IPv6、DNS rebinding 和重定向测试。

### P1-2：损坏的 SystemRule 时间戳未转换为稳定 fail-closed 错误

证据：

- `backend/app/memory/repository.py:910-919` 只把 SQLite 连接/查询异常包装成 `SystemRuleUnavailableError`，随后在 try 块外调用 `_system_rule(row)`。
- `_system_rule()`（`:906-908`）调用 `_dt(row["updated_at"])`；存储值损坏时会直接抛出 `ValueError`。
- 临时 SQLite 行为探针：先写入合法规则，再把 `system_rules.updated_at` 改为 `not-a-timestamp`，`get_system_rule('owner-a')` 得到 `ValueError: Invalid isoformat string: 'not-a-timestamp'`，不是 `SystemRuleUnavailableError`。
- `/api/conversations/system-rule`（`routes_conversations.py:68-74`）只捕获 `SystemRuleUnavailableError`，因此该损坏状态返回 500 而不是稳定 `503 SYSTEM_RULE_UNAVAILABLE`；写入后回读路径同样可能泄漏解析异常。

影响：Spec022 要求规则读取无法确定时 fail-closed、无模型调用并返回稳定错误。当前聊天 SSE 的宽异常分支可覆盖部分解析错误，但 repository/API 的公开契约仍不稳定，且不是所有调用方都走同一宽异常边界。应把行形状/时间解析/布尔值验证纳入受保护读取，并统一转换为 `SystemRuleUnavailableError`；同时增加损坏时间、NULL、错误 enabled 值的 API/SSE 断言。

### P1-3：受影响后端回归未全绿，现有测试与冻结 global 门禁冲突

定向综合命令：

```text
./.venv/bin/python -m pytest -q \
  tests/test_task05_memory_analysis_repair.py \
  tests/test_task05_backend.py tests/test_task07_backend.py \
  tests/test_task10_backend.py tests/test_memory_repositories.py \
  tests/test_conversations_api.py tests/test_chat_route.py \
  tests/test_kb_ask_trace.py --tb=short
```

结果：**87 passed, 1 failed，退出码 1**。失败为 `tests/test_task05_memory_analysis_repair.py::test_analysis_supports_multiple_items_pagination_and_idempotency`：测试打桩 classifier 返回 global 建议，并期待两项 `auto_saved`；当前 `conversation_service.py` 的 `has_explicit_global_intent()` 按 Spec022 原文授权门禁判断源文本 `记住多条` 未明确要求 global，因此正确产生 `pending_confirmation`。

该失败看起来是历史测试 fixture/断言未随 Task10 global 门禁更新，而不是将 classifier 建议当授权的理由；但在最终候选中它仍是可重复的受影响回归失败。架构师必须在收口前更新测试以匹配已确认规范，或明确重新冻结语义并修复实现，然后重新运行同一集合；不能把它记为全绿。

## P2 非阻塞项

### P2-1：v4/v5 migration validator 未完整校验分析表 FK/index

`repository.py:429-459` 的 `_is_schema_v4()` 检查分析表存在、列集合及 processing-step 唯一索引，未检查 `memory_analysis_jobs.user_message_id`、`memory_analysis_items.analysis_id/memory_id` 的外键，也未检查 `idx_analysis_jobs_work`、`idx_analysis_items_page`；v5 只追加 lease 字段检查。正常迁移路径创建的 DDL 是完整的，但被错误标记为 v4/v5 的部分损坏库可能通过启动检查。建议后续用 `PRAGMA foreign_key_list/index_list` 增加 fail-closed 校验和损坏迁移测试。

### P2-2：跨 analysis job 及人工决策仍存在重复记忆读后写竞态

worker 的 `_find_duplicate()` 在事务外扫描，之后才在 `create_analysis_memory()` 中插入；不同 analysis job 并发时可同时通过检查并各插入一条相同 active memory。人工决策 `routes_conversations.py:535-563` 也先事务外查重，再独立创建 memory、更新冲突和 CAS item，两个并发请求可能留下一个已失去 item 归属的重复 memory。建议增加规范化 statement digest 的 owner/scope/project 唯一约束，或在单事务中执行原子 insert-or-existing，并补并发测试。

### P2-3：analysis worker 生命周期/模型 fallback 的历史硬化项仍保留

Task04/Task05 交接中仍记录：进程重启后的 worker 需要下一次请求才会被唤醒，以及分类模型没有配置化的小模型 fallback。当前失败语义可见且不会阻断聊天，属于可靠性/可用性增强，不改变本轮 P1 结论。

### P2-4：SystemRule/后台隔离矩阵仍有少量自动测试空白

Task10 第二轮已覆盖 direct role、无规则会话、KB、观测脱敏和损坏 schema 的主要路径；仍建议补齐四个用户可见入口分别模拟读取失败，以及 classifier/摘要/embedding/reranker 明确不注入 SystemRule 的自动矩阵。静态核对未发现当前实现把规则传给后台模型。

## 已通过核对项

- **迁移/WAL/事务：** `MemoryRepository.connection()` 设置 `busy_timeout`、`foreign_keys=ON`、`journal_mode=WAL`；写入通过短事务和 `BEGIN IMMEDIATE`，初始化迁移失败会回滚并 fail-closed。正常 v1→v6 路径及 Task07 additive schema 已存在。
- **外键与删除：** memory evidence 对消息/会话使用 `ON DELETE SET NULL`，项目/会话关联使用既有删除语义；Task07 proposal 的 project/source-memory FK、CHECK 和索引由 `_is_task07_schema()` 精确核对。
- **并发/CAS：** analysis job lease token/version、processing step 稳定 identity/terminal 不 reopen、proposal 状态条件更新均有事务/CAS；未发现旧租约可写入新 memory/item 的 P1。
- **owner/project 隔离：** repository 查询、项目快照、RAG 项目 allowlist、KB sidecar association 均携带服务端 owner；未发现跨 owner 或跨项目召回/写入。
- **SystemRule 主契约：** 规则使用独立表和 `SystemRule` 数据类；启用空内容、长度边界、服务端 owner、真正 system role 注入、后台分类不注入规则以及本轮损坏行异常转换均通过当前候选核对。公开 API 对 malformed row 稳定返回 503。
- **Task07：** capability method 要求 evidence、source 校验和重复检查；proposal 只允许 proposed→accepted/rejected→applied，applied 需要外部确认、protected hash 相等且使用 CAS；未发现新的 schema/状态机回归。
- **旧聊天/RAG：** `routes_conversations.py` 的 sources 在回答 token 后、最多 5 个；`routes_kb.py` 保持现有 citations 顺序；普通 chat、KB ask、observability redaction 和 paper-discovery 安全下载器的定向合同未见回退。

## 本轮修复候选定向验证

| 检查 | 命令/探针 | 结果 |
|---|---|---|
| 受影响后端集合 | `./.venv/bin/python -m pytest -q tests/test_task05_memory_analysis_repair.py tests/test_task05_backend.py tests/test_task07_backend.py tests/test_task10_backend.py tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_chat_route.py tests/test_kb_ask_trace.py tests/test_article_download_probe.py tests/test_article_html_probe.py tests/test_article_services.py tests/test_kb_upload_closure_matrix.py --tb=short` | 退出码 0；**103 passed** |
| 论文安全/兼容集合 | `./.venv/bin/python -m pytest -q tests/test_paper_download_security.py tests/test_paper_download.py tests/test_api_routes_coverage.py tests/test_task05_memory_analysis_repair.py tests/test_task10_backend.py --tb=short` | 退出码 0；**95 passed，5 warnings** |
| 架构合同集合 | `./.venv/bin/python -m pytest -q tests/test_task09_conversation_filters.py tests/test_task09_project_activity.py tests/test_api_module_boundaries.py tests/test_kb_application_boundary.py tests/test_paper_download_security.py tests/test_ollama_direct.py tests/test_observability.py --tb=short` | 退出码 1；**77 passed，1 skipped，1 failed**；唯一失败为跨上下文 import 边界（P1-1） |
| SystemRule 损坏行 | `tests/test_task10_backend.py::test_malformed_system_rule_row_returns_stable_unavailable_error` | 通过；repository/API 均稳定返回 unavailable/503 |
| 全 backend 语法 | `./.venv/bin/python -m py_compile $(find backend -name '*.py' -type f)` | 退出码 0 |
| backend 冲突标记 | `git grep -n -E '^<<<<<<<|^=======|^>>>>>>>' -- backend` | none |
| scoped diff 空白 | `git diff --check -- backend tests/test_article_download_probe.py tests/test_article_html_probe.py tests/test_article_services.py tests/test_task05_memory_analysis_repair.py tests/test_task10_backend.py tests/test_kb_upload_closure_matrix.py` | 退出码 0 |

本轮未运行全量 pytest、前端测试或部署 smoke；backend boundary 的唯一失败足以阻塞本报告 GO。

## 首轮验证记录（修复前）

| 检查 | 命令/探针 | 结果 |
|---|---|---|
| 受影响后端综合回归 | 上述 Task05/07/10、memory、conversation、chat、KB 集合 | 退出码 1；87 passed / 1 failed（P1-3） |
| 文章助手/旧 KB 论文相关合同 | `./.venv/bin/python -m pytest -q tests/test_article_download_probe.py tests/test_article_html_probe.py tests/test_article_services.py tests/test_kb_ask_trace.py --tb=short` | 退出码 0；13 passed |
| 论文下载/SSRF/路由/仓储边界 | `./.venv/bin/python -m pytest -q tests/test_paper_download.py tests/test_paper_download_security.py tests/test_api_routes_coverage.py tests/test_memory_repositories.py tests/test_api_module_boundaries.py tests/test_kb_application_boundary.py --tb=short` | 退出码 0；109 passed，5 warnings |
| 其他后端架构合同 | Task09 filters/activity、API module boundary、KB boundary、paper security、ollama direct、observability | 78 passed，1 skipped |
| 语法 | `./.venv/bin/python -m py_compile`（当前候选所有 `backend/**` Python 变更文件） | 退出码 0 |
| 冲突标记 | `git grep -n -E '^<<<<<<<|^=======|^>>>>>>>' -- backend` | none |
| SystemRule 损坏行探针 | 临时 SQLite 将 `updated_at` 改为 `not-a-timestamp` 后读取 | 复现 `ValueError`，未转换为 `SystemRuleUnavailableError` |

上述测试均未运行前端、全量 pytest 或部署 smoke；本报告不能替代 Task08 的单端 tester/跨端 tester 全量验收。

## 收口动作

1. 共享安全原语迁移已完成；保持 `paper_download_security` 兼容重导出，避免历史 paper-security 调用方回归。
2. 本轮架构合同与受影响后端集合均为 0 failures，backend reviewer 放行；仍由 backend-tester/tester 处理全量 pytest、部署 smoke 和跨端验收。
3. P2-1～P2-4 可在后续硬化中处理，不阻塞当前 backend reviewer GO；Spec022 只有在 Task08 全部 tester/部署门禁通过后才能标记完成。

## 评审元数据

- 评审角色：backend-reviewer（临时 Luna high）
- 评审时间：2026-09-11（Asia/Shanghai；共享安全原语复核 19:40）
- 评审日志：`.codebuddy/agent-logs/spec-022/task-08/backend-reviewer/20260911-185739.md`
- 业务代码改动：无
- 最终签字：backend-reviewer **GO**（P0=0、P1=0、P2=4）
