# spec-038「记忆层改造」后端代码审查报告

- **审查对象**：分支 `feature/spec-038-memory-layer`，工作区未提交改动（22 改 + 16 新）
- **审查范围**：`backend/**` 与后端测试；不含 `frontend/**`
- **审查方式**：只读审查 + 可复现实证（venv 解释器 `./.venv/bin/python`）
- **审查者**：backend-reviewer
- **结论**：**Block（打回）** —— 3 条阻塞项，均有可复现证据

---

## 一、验证基线（可信）

| 项目 | 命令 | 结果 |
|------|------|------|
| 全量测试 | `./.venv/bin/python -m pytest tests/ -q` | **2 failed, 1970 passed, 1 skipped, 62 subtests passed**（755.9s） |
| 失败项 | — | 仅 `test_chat_route.py::test_prompt_never_contains_secrets`、`test_record_generation_called_once_with_route`（任务书已列明的**基线既有失败**，非本次回归） |
| spec-038 相关用例 | 6 个文件（markdown_store / session_search / injection_chain / memory_repositories / system_rule_backend / compaction_summary） | **128 passed** |
| ruff（4 个新增文件 + context_compaction） | `ruff check markdown_store.py session_search.py migration.py preserve.py context_compaction.py` | **All checks passed** |
| ruff（repository.py） | — | 13 项（F401 `chars_for_tokens` 未使用 + 11×SIM118 + 1×SIM102），多为基线既有风格项，**不计入本报告严重级别** |

> **关键观察**：测试与 lint 全绿，但**绿是假象** —— 下面 B2/B3 两条阻塞项之所以未被测试发现，是因为用例绕开了生产路径（详见每条证据）。

---

## 二、阻塞项（必须修复后才能合入）

### [BLOCK B1] 并发 `resolve_pending` 会丢条目：read-modify-write 窗口跨锁

- **文件**：`backend/app/memory/markdown_store.py:347-365`（`resolve_pending`），关联 `:215-224`（`_append_entry` 持 `memory_path` 锁）、`:196-213`（`_atomic_write` 持 `pending_path` 锁）
- **问题**：`resolve_pending` 的读改写跨越了**三把不同粒度的锁**：
  1. `self.list_pending()`（:352）在**无任何锁**的情况下读 PENDING.md 快照；
  2. `self.append_memory(...)`（:357）持的是 **`memory_path` 的锁**（`_append_entry` 内部 `_lock_for(path)`）；
  3. `self._atomic_write(self.pending_path, text)`（:365）持 **`pending_path` 的锁**，但写入内容 `text` 是**第 1 步读到的旧快照**减去被 resolve 的那一条。
  第 1→3 步之间存在窗口。并发的 `add_pending`（每消息 `MemoryAnalysisWorker` 的 pending 分支、`flush_memories`）会在第 1 步之后、第 3 步之前写入新条目，随后被第 3 步的**整体覆盖**抹掉。
- **实证**（脚本：1 线程 `resolve_pending` + 1 线程并发 `add_pending` ×20）：
  ```
  pending after concurrent resolve+add: expect 24 got 15
  ```
  丢 9 条，且该结果稳定可复现。
- **为什么是问题**：这不是理论竞态 —— `add_pending` 与 `resolve_pending` 都是本次改造引入的真实生产路径（分析 worker 写 pending、Agents 侧确认后 resolve），`resolve_pending` 又与「压缩前的 flush」共享同一 PENDING.md。丢掉的恰恰是**用户待确认的记忆条目**，即 L1 真相源里的用户数据；且丢得静默，无任何日志。
- **建议修法**（择一）：
  1. 重构成「锁内读-改-写」：把 `list_pending` 的读取与 `_atomic_write(pending_path, ...)` 放进**同一把 `pending_path` 锁**之内（新增 `_mutate_locked(path, fn)` 辅助函数，`_append_entry` 与 `resolve_pending` 共用），并且把 `append_memory` 的落定动作放在锁**之外**（避免跨文件锁嵌套造成死锁）。
  2. 或改为「追加式删除」：不重写整个 PENDING.md，而是给被 resolve 的条目追加 `- [<id>] <content> @RESOLVED` 标记，读取时过滤（append-only，天然无覆盖窗口）。
- **另需补测试**：现有 `tests/test_memory_markdown_store.py:162` 只做「并发 `append_memory`」，应补 resolve×add 混跑用例。

---

### [BLOCK B2] L2 索引未接到生产主路径：`create_message_pair` 从不写索引

- **文件**：`backend/app/memory/repository.py:666-709`（`create_message_pair`，**全文无 `_sync_message_index` 调用**）；生产调用点 `backend/app/api/routes_conversations.py:760`
- **问题**：`_sync_message_index` 只挂在 `create_message`（:903）与 `update_message`（:953）。但**真实聊天主链路**用的是 `create_message_pair` —— 它在一个事务里直接 `INSERT INTO messages ...`（:706-707）并 `return`，**没有任何索引钩子**。因此线上新写入的用户消息与 assistant 占位消息**永远不会进入 FTS5 索引**。
- **实证**（排除库串台干扰，先把索引工厂 monkeypatch 成本用例临时 index，再走生产路径）：
  ```
  create_message_pair（生产路径）→ 检索命中: 0
  索引行数: 0
  ```
- **为什么是问题**：L2「会话检索」的核心卖点是让 Agent 能翻旧账（`session_search` 工具）。索引只覆盖 `create_message` 这条**非生产路径**，等于 P2 的收尾接线在生产上**完全失效**：用户聊了几百轮，`session_search` 仍搜不到任何历史消息，只能命中 MD 笔记。这是功能性缺陷而非优化缺失。
- **建议修法**：
  1. 在 `create_message_pair` 事务提交后（与 `create_message` 一致，必须在写事务**之外**）对 `user_id` 与 `assistant_id` 各调一次 `self._sync_message_index(...)`；
  2. 或把索引钩子下沉到「消息终态」统一收口点（例如 `_sync_message_index` 在 `update_message` 进入终态时已覆盖 assistant 侧，则只需补 user 侧）。
  3. **测试必须走生产路径**：`tests/test_session_search_wiring.py:63` 目前只测 `repo.create_message`，应改为（或增加）`repo.create_message_pair`。

---

### [BLOCK B3] `build_default_index()` 吞掉真实 repository → 钩子写入**生产库**，跨库污染

- **文件**：`backend/app/memory/session_search.py:327-341`
- **问题**：函数签名只接收 `memory_dir`，内部**无条件** `MemoryRepository()` 无参构造（:337），完全忽略调用方真实的 repository（数据库路径）。
  ```python
  def build_default_index(memory_dir=None) -> SessionSearchIndex:
      from backend.app.memory.repository import MemoryRepository
      ...
      repository = MemoryRepository()      # ← 永远连 MEMORY_DIR/memory.sqlite3
  ```
- **实证**：
  ```
  build_default_index()._repo.database_path == '/Users/.../ResearchAgent/data/memory/memory.sqlite3'
  临时库建消息后：index_message -> False；索引 0 行
  ```
  而显式注入 `SessionSearchIndex(repository=repo, memory_dir=d)` 时 `index_message -> True`、命中 1 条 —— 证明**只有参数化入口是对的**。
- **后果（两重，均已发生）**：
  1. **跨库污染**：任何以非默认库运行的进程（测试、多库部署、其它 workspace）在写消息/记忆时会去**改写生产记忆库**的 `session_search_index`。我在做本次审查的探针时，生产库 `data/memory/memory.sqlite3` 的 `session_search_index` **从 0 行变成了 10 行** —— 这是本次审查实际制造出的污染，可作为证据。
  2. **索引内容串台**：`session_search` 会召回**生产库里别的 owner/别的会话**的索引行。`search` 的 owner 过滤（`session_search.py:282-285`）对 `owner_id IS NULL` 的 MD 行是刻意放行的，跨库时这条放行规则会让 A 库的检索读到 B 库的 MD 笔记。
- **为什么是问题**：记忆库是用户隐私数据（`.gitignore` 已把 `data/memory/` 整套排除，说明团队明确视其为敏感）。一个「写消息顺手更新索引」的优化路径把数据写到**生产库**，是数据边界被击穿，属于 CRITICAL 级。
- **建议修法**：
  1. `build_default_index` 增加 `repository` 参数，由调用方（`repository._sync_message_index` / `MarkdownMemoryStore._sync_memory_index`）传入 `self`（或 `self.repository`），**禁止**在钩子路径上无参构造 `MemoryRepository()`；
  2. `MarkdownMemoryStore` 也需要拿到 repository（或改为「索引由 repository 侧统一负责，MD 写入只发信号」，避免 store 侧再持一个库连接）；
  3. 加测试：**不 monkeypatch 工厂**，断言写入只落在当前 repo 的库，且生产库行数不变。

> **补充说明（B3 的测试反证）**：`tests/test_session_search_wiring.py:51-60` 的 `wired` fixture 用
> `monkeypatch.setattr(session_search_module, "build_default_index", lambda *_a, **_k: index)`
> **把整个工厂替换掉**，于是 B3 的真实构造被完全绕过；同时用例只走 `create_message`，
> 又绕开 B2。两条阻塞项都被测试基建「善意地」掩盖了。

---

## 三、建议项（应修复，不阻塞合入）

### [SUGGEST S1] `project_id` 白名单缺长度上限，超长合法 id 在写入时抛 `OSError`

- **文件**：`backend/app/memory/markdown_store.py:47`（`_PROJECT_ID_PATTERN`）、`:114-124`（`_project_path`）、`:202`（临时文件名）
- **问题**：正则只约束字符集，**无长度上限**。`"x"*250` 能通过 `_project_path` 校验，但 `_atomic_write` 的临时文件名构造成 `.tmp-<32位hex>-<name>.md`（:202），把可用文件名长度压缩到约一半，实测：
  ```
  250-char project_id write FAILED: OSError [Errno 63] File name too long
  ```
- **为什么是问题**：抛的是 `OSError` 而非契约声明的 `ValueError`。调用方按文档只预期 `ValueError`（见 docstring :110），`append_memory` 的 `except Exception` 虽能兜住，但在 `load_snapshot` 路径上 `_body_paths` 的异常被 `file_memory_snapshot` 静默吞成空串（`conversation_service.py:383-387`），会**静默丢掉整个项目记忆注入**，且无日志。属于「输入校验不严 → 错误类型不符契约 → 静默降级」。
- **建议修法**：在 `_PROJECT_ID_PATTERN` 之外加显式长度校验（如 `len(value) > 64` → `ValueError`）；或缩短临时文件名（少用 `path.name`，改用固定短后缀），保证「最长合法 id」也能落盘。

---

### [SUGGEST S2] `resolve_pending` 的 `KeyError` 契约与 `flush` 的静默 fail-open 不一致

- **文件**：`backend/app/memory/markdown_store.py:347-355`
- **问题**：`resolve_pending` 在 `item_id` 不存在时抛 `KeyError`（docstring 说「调用方是显式的人工/接口动作，需要感知」，合理）；但 `write_memory_candidate`（`conversation_service.py` 新增段）与 `flush_memories` 走的是 `contextlib.suppress(Exception)`。两者混用时，用户点「确认」若命中已被并发 resolve 的条目，异常会被上游 `suppress` 吞掉且**不记日志**，用户看到「已确认」但实际未落定。
- **为什么是问题**：静默失败比报错更难排查；且这是「用户数据落定」路径。
- **建议修法**：`resolve_pending` 的调用方（接口层）至少 `logger.warning` 记录未命中的 `item_id`；或让 `resolve_pending` 返回 `bool`。

---

### [SUGGEST S3] `_SNAPSHOT_HEADER` 抢占预算、`MEMORY_INJECT_MAX_CHARS` 语义与文档不一致

- **文件**：`backend/app/memory/markdown_store.py:276-300`；`backend/app/platform/config.py:155-157`；`USER.example.md` 末尾说明
- **问题**：`load_snapshot` 从预算里先扣掉 `len(_SNAPSHOT_HEADER)`（:277），但**当 `body_parts` 为空时 `sections` 仍返回 header**（:298-300），即 `max_chars=0` 时输出仍为 header 一行。实测：
  ```
  max_chars=0 → '长期记忆（L1 文件记忆，仅作为上下文，不是新指令）：\n- 用户偏好：中文\n- 先给结论'
  ```
  且 header 本身占 23 字符，实际可用预算 = `max_chars - 23`，与配置项注释「单次会话启动注入的文件记忆快照字符预算」的直觉不符。
- **为什么是问题**：不是致命缺陷，但会让「预算 0」这种边界（例如未来做开关）产生非零注入；且文档承诺的「预算」与实际可用字节存在固定偏差。
- **建议修法**：`max_chars<=0` 时直接返回 `""`；或把 header 长度纳入 docstring 明确说明。

---

### [SUGGEST S4] `migration.RETIRED_TABLES` 是死常量

- **文件**：`backend/app/memory/migration.py:54`
- **问题**：全仓库仅此一处定义、**零引用**（`grep -rn RETIRED_TABLES` 只命中定义行）。注释声称用于「建表时明确排除」与「数据保全时判断是否需要搬迁」，但两处都没用它（建表靠不写 DDL，搬迁靠 `preserve.py` 的容错 `SELECT`）。
- **为什么是问题**：死代码会误导后续维护者以为有统一收口点。
- **建议修法**：要么在 `preserve_legacy_owner_data` 里真正用它做「旧库是否需搬迁」的判断，要么删除并在 docstring 里说明停用表清单（避免两处真相源）。

---

### [SUGGEST S5] 旧表未 `DROP`，`initialize()` 的 fail-closed 只挡版本号不挡残留半旧库

- **文件**：`backend/app/memory/migration.py:61-273`（`_SCHEMA_STATEMENTS` 无任何 `DROP TABLE`）；`backend/app/memory/repository.py:207-216`
- **问题**：新基线**不删**旧表。`initialize()` 靠 `schema_version` 校验（:210-214）区分新旧库。但若旧库恰好处于「`schema_version` 行已丢 / 表损坏」状态（`current_schema_version` 返回 0，见 `migration.py:295-304`），`initialize()` 会把一个仍带 `memories`/`system_rules` 物理表的库**当作新库建基线**，不报错。
- **为什么是问题**：与 `docstring` 声称的「老库残留一律拒绝，避免在半旧 schema 上写入」不完全一致 —— 版本号丢失的残留库会被静默接受。考虑到 spec 已明确「无生产数据、可删库重建」，风险低，但「数据保全 + 新基线」这套设计在降级路径上不自洽。
- **建议修法**：在 `initialize()` 建基线前，显式 `DROP TABLE IF EXISTS` 三个 retired 表（用上 S4 的 `RETIRED_TABLES`），从物理层面保证「停用即不存在」，也让版本号不再是唯一防线。

---

### [SUGGEST S6] `flush_memories` 与压缩并行，且「压缩前 flush」语义被削弱

- **文件**：`backend/app/chat/application/context_compaction.py:596-601`（`_dispatch_flush` 后再 `build_compaction_summary`）；`:548-571`
- **问题**：`_process` 里 `flush` 只**派发**到独立 daemon 线程（:600 → :571），**不等待**结果，紧接着就生成摘要（:601）。因此：
  1. 「压缩前把重要信息写入 L1」变成「压缩与写 L1 并行」——如果摘要这一步本该看到 flush 落定的记忆，顺序没有保证；
  2. flush 线程与 `MemoryAnalysisWorker`（每消息）、`MemoryEvolutionWorker`（每轮）**并发写同一 MD**，正是把 B1 的竞态暴露在最高频的场景。
- **为什么是问题**：设计意图（注释 :596-599）与实现（不等待）存在偏差；结合 B1，这条路径是丢条目的主要放大器。
- **建议修法**：若「压缩前」是硬语义，应 `join(timeout=COMPACTION_FLUSH_TIMEOUT)`（有界等待，仍 fail-open）；若确实只要「并行地给一次机会」，应在 docstring/配置注释里改掉「压缩前」的表述。**无论哪种，都应先修 B1**。

---

### [SUGGEST S7] `decide_memory_write` 的 scope 决策丢弃了分类器信号，可能落错库

- **文件**：`backend/app/chat/application/conversation_service.py`（新增段 `decide_memory_write`，约 :180-225；调用点 `MemoryAnalysisWorker.process`）
- **问题**：函数用 `has_explicit_global_intent(source_text)` 决定 global，否则**只要 `project_id` 非空就落项目**，完全不看 `candidate.scope`。而 `MemoryAnalysisWorker` 传入的是 `job.project_id_snapshot`（入队时刻的快照），注释里旧实现特意强调「The conversation may have moved while this job was queued」——现在这个防护没了。
- **为什么是问题**：会话在 job 入队后被移动/解绑到别的项目时，记忆会被写进**快照里的旧项目**（或被写进当前项目而非用户意图的项目）。相较于旧实现的 `_decide_candidate`（会校验 `repository.get_project(project_id, owner_id)` 存在性，:753 附近被删），新实现**丢掉了项目存在性校验**，`append_memory` 会直接创建 `projects/<不存在的id>.md`。
- **建议修法**：在写入前校验 `project_id` 对应的项目仍存在（复用 `repository.get_project`）；并让 `candidate.scope` 参与决策（至少在 `candidate.scope == "global"` 时不要因为存在 `project_id` 就落项目）。

---

### [SUGGEST S8] 注入点复核结论：无遗漏；但 `/api/system-rule` 的语义已名不副实

- **文件**：`backend/app/api/routes_conversations.py:167-171`（`GET /system-rule` 仍调 `repo.get_system_rule(OWNER_ID)`）
- **复核过程（任务书第 3 条）**：grep 全仓库 `get_system_rule` / `read_user_memory_or_empty`：
  - `routes_chat.py:80`、`routes_article.py:131`、`routes_kb.py:1022`、`routes_conversations.py:432` 均已改为 `read_user_memory_or_empty()` ✔
  - `routes_conversations.py:170` 保留 `repo.get_system_rule(OWNER_ID)` —— 但该方法（`repository.py:419-422`）**底层已改为读 USER.md**，语义等价 ✔
  - 结论：**4 处注入点无遗漏**。
- **建议**：`/system-rule` 端点与 `get_system_rule/upsert_system_rule/set_system_rule_enabled/clear_system_rule` 这一套命名已与 MD 模型不符（`enabled` 靠「内容是否为空」派生），且 `upsert_system_rule` 的 `len(content) > 12000` 上限对 USER.md 而言缺少与 `MEMORY_INJECT_MAX_CHARS` 的一致性说明。建议在路由注释或后续 spec 里统一改名（如 `/user-memory`），避免长期双重语义。

---

## 四、审查重点逐条结论

| # | 审查重点 | 结论 | 依据 |
|---|---------|------|------|
| 1 | 并发写 MD 原子性 / 锁粒度 | **不通过** | `resolve_pending` 读改写跨锁，实证丢 9/24 条（B1）；`append_memory` 单路径锁粒度正确（40 线程实测 40/40 条）；无 `.tmp` 残留（实测 `leftover tmp: []`） |
| 2 | 预算截断正确性 | **通过（附意见）** | 条目按行边界整条保留，无半截条目；USER.md 不参与截断（实测超长 USER.md 仍全量）；边界意见见 S3 |
| 3 | 注入点是否遗漏 | **通过** | 4 处已改；`routes_conversations.py:170` 保留但底层已切 USER.md；附 S8 |
| 4 | 路径遍历 | **通过（附意见）** | `_PROJECT_ID_PATTERN` 拒绝 `..`/`../etc/passwd`/`a/../b`/`proj.a`/`.hidden`/全角/零宽（实测全部 rejected）；realpath 双重校验到位；**但缺长度上限**见 S1 |
| 5 | 循环依赖与 fail-open | **通过** | 延迟导入均在方法内（`repository.py:890`、`markdown_store.py:189`、`context_compaction.py:387`）；`safe_call` 覆盖写消息/写记忆/压缩三处钩子；无钩子失败阻断主链路 |
| 6 | 隐私 | **通过** | `git check-ignore` 实测 `data/memory/USER.md`、`MEMORY.md`、`PENDING.md`、`projects/abc.md`、`projects/sub/x.md` **全部命中 `data/memory/`**；`USER.example.md`/`MEMORY.example.md` 通读为纯模板说明，无敏感内容 |
| 7 | 停用表残留引用 | **通过（附意见）** | `memories`/`memory_evidence`/`system_rules`/`capability_methods` 无运行时 SQL 引用；`system_rules` 仅在 `preserve.py:38` 容错读取（捕获 `OperationalError`）与测试中出现；无指向已删表的死调用；`RETIRED_TABLES` 死常量见 S4；旧表未 DROP 见 S5 |
| 8 | L2 索引一致性 | **不通过** | 生产主路径 `create_message_pair` 无索引（B2，实证 0 行）；`build_default_index` 连生产库造成跨库污染（B3，实证生产库被写入 10 行）；「消息被删除」场景当前无硬删路径（`delete_conversation` 为软删，`repository.py:816-825`），风险可控 |

---

## 五、总体结论

**Block —— 不可以合入。**

P1（L1 文件化）与 P3（压缩联动）的整体设计方向正确，fail-open 纪律落实到位，隐私隔离（gitignore）经实测有效，注入点无遗漏，迁移链瘦身（−800 行）收益明确。但在**三条最关键的接线点上存在问题，且都能稳定复现**：

1. **B1 并发丢用户数据**：`resolve_pending` 的 read-modify-write 跨锁，实测丢 9/24 条待确认记忆；
2. **B2 生产路径索引完全未生效**：真实聊天走 `create_message_pair`，该路径无索引钩子，`session_search` 在生产上搜不到任何历史消息；
3. **B3 数据边界被击穿**：`build_default_index()` 忽略真实 repository、永远连生产库，非默认库场景会**改写生产记忆库**（本次审查已实际造成 10 行污染）。

三者叠加的严重性在于：**「测试全绿 + lint 全绿」是由测试基建自身绕过生产路径造成的**（`test_session_search_wiring.py` 的 `wired` fixture 替换掉索引工厂，且只测 `create_message`），因此不能以 CI 绿作为放行依据。

**放行条件**：修复 B1/B2/B3，并为每条补上**走生产路径、不做工厂替换**的回归测试；建议项 S1、S4、S5、S7 建议同期处理（改动量小、同属数据正确性），S2/S3/S6/S8 可在后续 spec 收敛。
