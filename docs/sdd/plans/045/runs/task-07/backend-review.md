# Spec045 Task07 后端评审报告

- 角色：`backend-reviewer`（只读评审）
- 分支：`feature/spec-045-evaluation-observability-hardening`（改动全部未提交，staged 为空）
- 范围：仅 `backend/**` 与后端测试；`frontend/**` 不在本角色评审范围（仅读取核对契约，未评改动）
- 日期：2026-11-08
- 依据：spec-045「数据模型/端点接口/边界/明确不做」+ 第 06/10 项 + 实施阶段裁决回填；task-07 全文（A/B 裁决 5 条硬约束、边界与明确不做）；`backend-patterns` / `regression-guard` 第 5–9 条 / `ROLE-ONBOARDING:78-84`；4 个必读技能文件
- 总评结论：**通过**（P0 = 0，P1 = 0）

## 评审方法与独立取证

| 手段 | 结果 |
|---|---|
| `git diff` 全量 + 新增文件全文 Read | 10 改 + 2 新增模块 + 3 新增测试，与任务书清单一致 |
| 独立重跑定向集（`.venv/bin/python -m pytest ... -q`，6 文件） | `38 passed`，EXIT=0 |
| 矩阵 `inventory_digest` 按测试算法重算 | `MATCH=True`，8 个 inventory 文件 sha256 全匹配 |
| 只读实测（临时库/内存，不写仓库） | 并列 started_at 分页、非法 cursor、脱敏凭据绕过、全局白名单未放宽 |
| 真实产物核对 | `benchmark-real.json` / `benchmark-summary.json` / `benchmark-summary.event.json` / `benchmark-card-browser.txt` |

---

## 必查点逐项结论

### 1. 无参兼容性 —— 通过

- `backend/app/api/routes_conversations.py:2457-2467`：`if cursor is None and limit is None` 分支**原样保留**既有逻辑（`_repo().list_processing_steps(...)` + 404 判定 + `return {"steps": [s.to_dict() for s in steps]}`），与改动前 diff 前镜像逐字一致；未追加任何键。
- `backend/app/memory/repository.py:1691-1694`：无参读取 `list_processing_steps` 的 SQL 与返回形状一字未改。
- 前端拉取点 `frontend/app.js:2611`（`hydrateConversationProcessing`，本轮实测行号；任务书标注 `:2482` 为行号漂移）为 `conversationFetch('/api/messages/${...}/processing-steps')`，**不带查询参数**，仅消费 `data.steps`（`:2613`），与扁平形状一致。
- 契约测试 `tests/conversation/test_processing_steps_pagination.py:48-58` 断言 `set(body) == {"steps"}` 且逐字段等于 `repo.list_processing_steps(...)`。
- 带参分支独立：`:2469-2497` 仅在显式带 `cursor`/`limit` 时进入，返回 `{steps, next_cursor, has_more}`；两分支互不污染。
- 结论：无参仍返回且仅返回扁平 `{"steps": [...]}`，与前端及既有契约一致。

### 2. 分页正确性 —— 通过（含 1 条需如实记录的边界，见残留项 R1）

- **owner 隔离**：`repository.py:1712-1716` 与无参读取（`:1693`）同为 `JOIN messages m ON m.message_id=s.message_id WHERE s.message_id=? AND m.owner_id=?`；`decode_cursor(..., STEP_CURSOR_KIND)`（`:1711`）校验游标命名空间，防止跨列表游标。测试 `tests/conversation/test_processing_steps_pagination.py:110-127`（越权消息 404）、`:130-141`（仓储层 owner 不匹配返回空页）双覆盖。
- **不重不漏**：keyset 游标为 `(started_at, step_id)`，`step_id` 是主键（`backend/app/memory/migration.py:98`），唯一稳定；`repository.py:1718-1721` 条件 `(s.started_at > ? OR (s.started_at = ? AND s.step_id > ?))` 与 `ORDER BY s.started_at, s.step_id` 自洽；多取一行判 `has_more`（`:1724`）。实测并列 `started_at` 下逐页拼接与全集「集合一致（无重复无遗漏）」。测试 `:61-89` 断言逐页拼接 == 无参全量、`pages == 4`。
- **越界/非法统一 400 + 稳定错误体**：`routes_conversations.py:2469-2484` 用 `str` 手工校验 `limit`（规避 FastAPI 422），非整数 / `0` / `>200` 均 400 `{code:"INVALID_LIMIT", message, retryable}`；`:2490-2494` 捕获 `decode_cursor` 的 `ValueError` → 400 `{code:"INVALID_CURSOR", ...}`。实测 4 类非法 cursor 稳定抛 `ValueError("invalid cursor")`，`binascii.Error` 为 `ValueError` 子类不会漏成 500。测试 `:92-107` 参数化 5 例覆盖。
- **`started_at` 并列已知边界**：无参排序 `ORDER BY started_at, logical_sequence`（`repository.py:1693`），分页排序 `ORDER BY started_at, step_id`（`:1720`）。实测证实并列时两者**集合一致但行序不同**（无参按 `logical_sequence`、分页按 `step_id`）。代码 docstring（`:1704-1709`）与 spec 数据模型（spec:173）未显式点明该差异；测试 `:88` 用互异时间戳种子断言 `seen == flat`，掩盖了该差异。分页本身正确、稳定、不重不漏，故不判缺陷，作为如实记录与测试覆盖缺口列入残留项 R1。

### 3. retention 安全性 —— 通过

- **默认阈值保守**：`backend/app/platform/config.py:234-239` 实测 `EVENT_RETENTION_ENABLED=True`（可 env 关）/ `MAX_AGE_DAYS=90` / `MAX_ROWS=100_000` / `VACUUM=True`；相对现状 12/74/66 行极保守。测试 `tests/memory/test_event_retention.py:122-127` 断言 `>=90` / `>=1000`。
- **不迁移 / 不删现有历史数据 / F15 未夸大**：`config.py:229-233` 明确「面向未来增长的保守清理，非现有故障」「不迁移、不主动删除现有历史数据」；`retention.py:3-12`、`test_event_retention.py:2-6`、task-07:27-29 措辞一致，**未夸大**为现有故障。无 DDL、无 migration、无历史回填；默认阈值下现有数据全部在保留期内，`LIMIT 0` 不删行。清理后业务读取 200 正常（`test_event_retention.py:61-81`、`:100-119`）。
- **fail-open**：`retention.py:70-102` 对组合根解析、两库各自 prune、两库各自 VACUUM 全部独立 `try/except`，异常只记日志/写入 `errors`，不外抛；`main.py:102-107` 再包一层。测试 `test_event_retention.py:130-151` 模拟 `database is locked` 验证一库失败另一库照常、`errors == ["research"]`。
- **VACUUM 在事务外**：`retention.py:32-38` 用独立 `sqlite3.connect(..., isolation_level=None)` autocommit 连接执行 `VACUUM`；两库 prune 事务（`repository.py:1756 with self.transaction()`、`research_store.py:4827-4845 BEGIN IMMEDIATE + commit/rollback`）均在 VACUUM 之前结束。`should_vacuum` 门控（`:90-95`）仅对确实删过行的库 VACUUM。
- **不与长跑任务争锁**：`_VACUUM_TIMEOUT_SECONDS=5.0`（`retention.py:29`，与 `repository.py:205 busy_timeout=5000` 同量级）、research 连接 30s（`config.py:233`）、启动期低峰未接流量（lifespan `yield` 之前）、fail-open。测试 `test_event_retention.py:154-175` 验证「无删除不 VACUUM」。
- **`main.py` 既有 `try/finally` 收尾语义未变**：`main.py:99-108` 新增块位于 `try: yield / finally:`（`:109-128`）**之前**，是独立的启动 try/except；`yield` 与 `finally`（`stop_capability_scheduler` / paper_browser 会话清理 / manager.close）一行未改（diff 仅在 `:99` 前增 10 行）。
- 外键 RESTRICT：processing_steps 自引用 `ON DELETE RESTRICT`（`migration.py:101`），`repository.py:1768-1787` 用 `NOT EXISTS(子引用)` 规避并如实记录收敛策略；research_events 的 `REFERENCES research_tasks RESTRICT`（`research_store.py:588`）不因删除 event 行触发。所有 DELETE/SELECT 全 `?` 参数化，无 f-string 拼接。

### 4. 安全豁免（本轮最需独立复核点）—— 通过

结论：`research_store.py` 新增分支**只放行**「`benchmark_summary` 键 + warm/cold 两 phase × 四项有限数值」，**未放宽**全局脱敏规则，凭据与其它敏感字段**无法绕过**脱敏；spec 第 09 项 / Task 06 成果未被破坏。

- **精确分支**：`research_store.py:178-182` 为 `if key_text == "benchmark_summary":` 精确等值匹配（大小写敏感、非子串、非前缀），调用 `_safe_benchmark_summary(item)` 后 `continue`；`continue` 仅跳过该键的通用处理，不触碰其它键。
- **结构白名单**：`research_store.py:140-168` `_safe_benchmark_summary` 只接受 `dict`、只遍历 `BENCHMARK_SUMMARY_PHASES`（`("warm","cold")`）、每 phase 只取 `BENCHMARK_SUMMARY_METRICS`（`median_ttft_ms` / `throughput_completion_tokens_per_s` / `peak_memory_bytes` / `failure_rate`），值必须 `int/float`（排除 `bool`）且 `math.isfinite`，`result or None`。
- **全局规则未放宽**：`_EVENT_SAFE_KEYS`（`:123-136`）与 `_EVENT_SENSITIVE_PARTS`（`:137`）在 diff 中为未改动上下文；实测 `"token" in _EVENT_SENSITIVE_PARTS == True`、`"benchmark_summary" not in _EVENT_SAFE_KEYS == True`。值级 `[REDACTED]` scrub（`:197-204`，spec 第 09 项 / Task 06 成果）一字未动。
- **凭据绕过实测（独立复核）**：构造在 `benchmark_summary` 子树夹带 `password/prompt/token/nested.api_key/evil_phase/credential/字符串值/额外键/多余指标` 的恶意 payload，经 `_safe_event_payload` 后仅剩 `{'warm':{'median_ttft_ms':100.0,'peak_memory_bytes':999},'cold':{'failure_rate':0.5},'status':'completed'}`，所有敏感串、嵌套对象、多余 phase、非数值全部剔除，零泄露。回归测试 `tests/system/test_benchmark_summary_card.py:226-242` 亦断言 `prompt`/`token` 不在、`Authorization: Bearer` 被 `[REDACTED]`、`status` 保留。
- **未绕过深度限制**：`benchmark_summary` 分支以独立清洗函数（固定 2 层）替代 `_safe_event_value` 的递归，`depth > 3` 保护（`:172`）对其余键仍生效；属收紧而非放宽。
- 说明：原规则下 `benchmark_summary` 整个键会被丢弃（因不在白名单）；本次改用更严格的「结构 + 数值」白名单放行，等价或更严于原规则，非规则松动。唯一可收紧点见残留项 R3（分支未限定 event_type/来源）。

### 5. A 打通真实性 —— 通过

- **四项指标全部真实测量，无占位/伪造**：`backend/app/platform/benchmark_summary.py:154` `median_ttft_ms ← statistics.median(样本 ttft_ms)`；`:141,157-159` `throughput_completion_tokens_per_s ← statistics.median(样本 tokens_per_sec)`（**实名映射**：脚本原名不在前端别名表，显式改名，task-07 裁决第 2 条）；`:44-58` `peak_memory_bytes ← resource.getrusage(RUSAGE_SELF).ru_maxrss`，按 `sys.platform` 换算（darwin bytes / linux ×1024），不取 `size_vram`；`:162` `failure_rate ← failures/rounds`。`_within_bounds`（`:89-92`）越界直接不输出（不钳制、不用 0 冒充，`:10-11`），`_as_number` 拒 bool/NaN/Inf（`:61-69`）。真实产物 `benchmark-summary.json` 四项 `38478.927 / 19.735 / 106070016 / 0.0` 均为真实测量。
- **`diff = langchain - direct` 口径 / `derive_metrics` 语义未变**：`scripts/bench_ollama_routes.py` 的 `_diff`（`:56-68`）、`DIFF_KEYS`（`:36`）、`run_benchmark`、`derive_metrics` 全未在 diff 中出现；`tests/system/test_bench_routes.py:91-181` 锁定口径，`test_benchmark_summary_card.py:205-208` 断言 `diff.ttft_ms == -12204.638` 且 report 结构逐字段不变。
- **默认 `--json` 输出逐字节不变**：`bench_ollama_routes.py:203-211` 仅当 `args.summary_output or args.task_id` 时进入新分支，默认两者 `None` 完全不执行；`:197` 的 `print(json.dumps(report, ...))` 一字未改。测试 `test_benchmark_summary_card.py:193-204` 用 capsys 断言 `baseline == with_summary == with_event == json.dumps(report,...) + "\n"`。
- **事件类型复用既有白名单、无新增端点/SSE 类型/前端改动**：`:176-186` `append_event(task_id, "task", ...)`；`"task"` 在后端 `EVENT_TYPES`（`contracts.py:173`）与前端 `EVENT_TYPES`（`research-tasks.js:12`）内。`append_event`（`research_store.py:4761-4762,4768`）校验白名单、仅 `UPDATE last_event_seq/updated_at` **不改 status**；测试 `test_benchmark_summary_card.py:245-271` 断言 status 不变、`event_type=="task"`、payload 完整。真实回执 `benchmark-summary.event.json`：seq 40、`status_before/after=completed`。git status 无 `frontend/**` 改动；无新路由、无新 SSE 类型。真实 Chromium 取证 `benchmark-card-browser.txt`：四项指标可见、`eventsLoaded=40`、`sectionHidden=false`。

### 6. 范围纪律 —— 通过

- **P2 三项未碰**：无人工标注 gold 集 / `quality_score` 口径统一 / 在线实时评测相关改动。
- **`frontend/**` 未改**：git status 中无前端文件（仅读取核对 `app.js` / `research-tasks.js` 契约）。
- **未 push / 未合 main / 未 commit**：改动全部在工作树（staged 为空），分支仍为 feature 分支；git log 最近提交 `440d9e33` 等为既有提交。本评审全程只读。
- **测试文件命名不含编号**：新增 `test_event_retention.py` / `test_processing_steps_pagination.py` / `test_benchmark_summary_card.py` 均按能力命名、无 `spec\d+`/`task\d+` 编号子串（符合 spec-044 的 S4-1 约定）。既有含编号测试（如 `test_task03_*`）为历史文件，非本轮改动。

---

## 附加核查

- **矩阵哈希同步**：`docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` 的 `inventory_digest` 与 `main.py` / `routes_kb.py` sha256 与真实文件逐一比对一致；按 `tests/kb/test_kb_upload_closure_matrix.py:83-88` 算法重算 `MATCH=True`。3 字段同步成因合理（main.py 本轮改动 + Task05 遗留 `routes_kb.py` 失配）。
- **patch 适配**：`tests/system/test_legacy_kb_integration.py:209` 由 `flush` 改 `enqueue_flush`；实测 `routes_kb.py:58,1097,1113` 确为 `enqueue_flush`（Task05 把 flush 移出 SSE 后的合理适配）。
- **分层 / 时间 / 复用**：`benchmark_summary.py`、`retention.py` 位于 `platform/`，纯函数/编排，未向 `domain/` 引入 FastAPI/HTTP/Playwright/env 依赖；UTC 时间戳（`datetime.now(timezone.utc)`、`_utcnow()` Z 格式、cutoff 按库格式分别构造，注释明确两格式不可混用）；retention 复用既有两 store 的 prune、benchmark 复用 `append_event` 与 `encode_cursor/decode_cursor`，无第二套实现（regression-guard 第 9 条）。

---

## P0 / P1 缺陷列表

**无。**

六个必查点全部通过；无 CRITICAL / HIGH 问题。安全豁免分支经独立实测确认无凭据绕过；分页 owner 隔离、不重不漏、400 稳定错误体均成立；retention 保守、fail-open、VACUUM 在事务外；A 打通四项真实测量；范围纪律无越界。

---

## Review Summary（ECC Summary Format）

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | info   |
| LOW      | 5     | note   |

Verdict: **通过（Approve）** — 无 CRITICAL/HIGH 缺陷，可进入 Spec 收口；5 条 LOW 为文档记录/可选加固/收口残留，不阻塞合并。

---

## 总评结论

**通过。**（P0 = 0，P1 = 0）

判定纪律：以上每条结论均基于 `git diff` / Read / 只读实测的真实代码事实，附 `文件:行`；不凭 spec 描述或回传摘要下结论。无「应该没问题」式结论。

---

## 需在 Spec045 收口前补的残留项（强制约束清单，不阻塞本次合并）

- **R1（LOW，最需处理）** 分页「`started_at` 并列」排序键差异未如实显式记录：无参 `ORDER BY started_at, logical_sequence`（`repository.py:1693`）vs 分页 `ORDER BY started_at, step_id`（`:1720`），并列时集合一致但行序不同（本报告实测证实）。`test_processing_steps_pagination.py:88` 以互异时间戳种子断言 `seen == flat`，掩盖了该差异。要求：在 `list_processing_steps_page` docstring / task-07 变更日志显式写明该边界，补一条并列 `started_at` 的测试（断言集合一致而非顺序一致），或明确「分页与无参不保证同序」的契约。
- **R2（LOW）** `EVENT_RETENTION_ENABLED` 默认 `True`（`config.py:234`）意味着每次启动同步执行清理事务；当前默认阈值下不删行（依赖「现有数据均在保留期内」前提）。要求：把该前提写入 task-07 验收记录、注明 env 可关闭；并记录演进点——未来若真触发大规模删除 + VACUUM，启动期同步 VACUUM 应改为后台异步，避免延长启动。
- **R3（LOW，可选加固）** `_safe_benchmark_summary` 分支对**所有**事件 payload 生效（`research_store.py:178`），未限定 `event_type`/来源；虽输出被限死为四项有限数值、实测零泄露，建议收口时评估是否进一步收紧为仅 `task` 事件可用。
- **R4（LOW，文档收口）** task-07 文档 `:150-151`「待回填」清单（红绿测试输出、清理前后行数、分页样例、四项实测值、浏览器截图路径、`spec-status-changelog.md` 条目）尚未消除；spec 任务计划表 `spec:316` 中 Task07 状态仍「待执行」、spec 状态「实施中」。要求：收口前用 `runs/task-07/` 既有产物回填正文并更新状态/台账（不改代码）。
- **R5（LOW，溯源说明）** `upload-closure-matrix.json` 的 `inventory_git_revision` 仍为旧冻结基线 `8b0cde1`，而 3 个哈希/digest 已按当前内容重算。要求：在 task-07 变更日志注明「`inventory_git_revision` 保留为历史冻结基线标识，哈希按当前文件内容重算」，消除溯源歧义。

---

## 只读声明与产物

- 本评审除本评审报告与系统强制进展日志外，未写入任何文件；未修改任何业务代码 / 测试 / spec / 前端；未 `git commit` / `push` / 合 main / `reset` / `stash` / `clean`。
- 评审报告：`docs/sdd/plans/045/runs/task-07/backend-review.md`（本文件，按本任务指定路径落盘）
- 进展日志：`.codebuddy/agent-logs/spec-045/task-07/backend-reviewer/20261108-162752.md`
