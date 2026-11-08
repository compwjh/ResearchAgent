# 后端评审报告：2026-11-09 本轮后端改动（假数据清理 / 任务耗时字段 / 项目记忆列表接口）

- 角色：`backend-reviewer`（只读评审）
- 评审时间：2026-11-09 05:38 CST
- 归属：`spec-regression / task-demo-data-cleanup`（本轮为用户裁决的回归批次，与同目录 `backend-dev` 日志对齐）
- 基线：`git diff`（working tree，未 staged）+ `HEAD=1b26c76c` 基线对比
- **文件边界**：只评 `backend/**` 与后端测试 `tests/research/`、`tests/memory/`；`frontend/**` 改动交 `frontend-reviewer`，本次未越界评审。`docs/sdd/specs/043-*.md` 为 spec 文档，不在后端评审范围。
- **只读声明**：本次仅新增 2 份评审产出文档（本文件 + 进展日志），未修改任何业务代码 / 测试 / spec / 数据 / 既有文档，未执行任何 git 写操作（无 add/commit/push/merge/reset/stash/clean）。所有验证命令均为只读或 pytest 运行。
- 命名说明：模板路径 `015-backend-review.md` 已被 spec-015 的历史报告占用，按「编号按当前 spec 替换」原则改用本批次日期+任务名，**绝不覆盖历史报告**。

---

## 一、结论

**通过（附意见） / Approve with comments。**

无 CRITICAL、无 HIGH。三条用户裁决逐条满足；spec-038 冻结的 GET/PUT 契约与 OCC revision 经 `git diff` 证实零改动；13 个新增用例真实通过；ruff 零新增；数据清理实况与描述完全吻合且可回滚。

2 个 MEDIUM 均属健壮性 / 测试覆盖缺口，**不阻塞本轮合并**，但按项目规则「通过（附意见）须把意见沉淀为强制约束清单」，已列入第七节，建议下批次落实。

> 升级条件（透明交付给用户裁决）：若产品要求「即使个别项目的 md 文件损坏，其余 active 项目的记忆仍必须可见」为硬指标，则 MEDIUM-1 应升为 HIGH、结论改判「需修改」。按当前裁决文字（「所有 active 项目的记忆一次性全部列出」）与既有 fail-closed 稳定 503 语义，我判定其不阻塞。

---

## 二、需求符合性（三条裁决逐条核验，基于代码事实）

### 裁决① 清掉凌晨种子脚本造的深度研究假数据 —— 满足

- `scripts/seed_demo_research_reports.py:278-298` 的 `clean()` 以 `conversation_id LIKE 'seed-demo-%'` 定位，删 research 库 5 表（artifacts/agent_runs/reports/sessions/tasks）+ memory 库 conversations；删除按 task_id 精确关联，前缀为固定字面量 `seed-demo-`（不含 `_` 通配符、无字符串拼接、参数化绑定），真实会话 id 为 32 位 uuid hex 不可能误匹配。
- **只读实况核对**（`sqlite3 mode=ro` 查询两库）：
  - research：备份 `tasks=5(seed=2)/reports=2/artifacts=9/sessions=7/agent_runs=16` → 当前 `tasks=3(seed=0)/reports=0/artifacts=3/sessions=5/agent_runs=14`，差值 -2/-2/-6/-2/-2，与「2 任务 / 2 会话 / 2 agent_run / 2 报告 / 6 产物」完全吻合。
  - memory：`conversations 11→9`、`seed_convs 2→0`。
  - 3 个真实任务（`0cc210cb…cancelled`、`81241f3f…partial`、`d21317d8…partial`，均 2026-09-18）完好；`projects=2` 未动；文献地图库未动；孤儿 md 未动。
- 备份 `data/backup/20261109-cleanup/` 含两库清理前快照（可读出 `seed=2`），可回滚；`.gitignore:50-51` 新增 `data/backup/` 防止 1.6MB 运行期数据入库，合理。

### 裁决② 后端补研究任务耗时字段 —— 满足（诚实性达标）

- `routes_research.py:668-695` 新增纯函数 `_task_duration_ms()`，`routes_research.py:703-704,720-722` 在 `_task_summary` 白名单增加 `started_at`/`completed_at`/`duration_ms`。
- 领域模型 `ResearchTask`（`models.py:15-35`）**确实没有** `started_at`（只有 created_at/updated_at/completed_at）；`routes_research.py:703` 用 `getattr(task, "started_at", None)` 诚实返回 `None`，未引用不存在属性、未造值、未落库、未改 schema。
- `duration_ms` 边界（`routes_research.py:675-693`）：时间缺失（`None`/空串）、非法（`fromisoformat` ValueError）、倒挂（`delta_ms < 0`）、超长（>64 字符）全部返回 `None` 而非造 `0`。`tests/research/test_task_summary_timing.py:68-84` 用 6 组参数化逐字断言 `is None` 且 `!= 0`。
- **语义澄清（避免照抄措辞）**：合法「带时区」时间戳不应返回 `None`，正确行为是归一到 UTC 后算出真实墙钟差 —— `routes_research.py:681-684` 把 naive 补 UTC、aware 转 UTC 后相减，实现正确；只有无法解析/倒挂/缺失才返回 `None`。用户要点中的「时区返回 None」应理解为「异常时区不得算出错误的 0」，实现满足。
- 影响面：`_task_summary` 复用 4 处（`routes_research.py:1173,1333,1538,1561`），新增 3 字段会出现在这 4 个端点响应中（增量兼容，字段属任务摘要）。域回归 `tests/research -k "summary or list or timing or task_detail or notification"` = **78 passed**，无既有严格键集合断言被破坏。

### 裁决③ 新增项目记忆列表接口 —— 满足

- `routes_conversations.py:687-721` 新增 `GET /api/memory-documents/projects`；`repository.py:647-660` 新增 `list_active_projects()`。
- **只返回 active 且未删除**：`repository.py:656` SQL `WHERE owner_id=? AND status='active' AND status!='deleted'`，参数化占位符，严格等于 `active`；`NULL` status 被正确排除。与 `_memory_document_context`（`routes_conversations.py:639-669`）对单文档的 `status != "active"` 判定语义一致。测试 `tests/memory/test_memory_documents_projects_api.py:25-58` 明确断言 deleted / archived 均不出现。
- **一次性全部列出**：无分页、无 cursor、无 LIMIT（`repository.py:656`），是用户裁决「所有 active 项目一次性全部列出」的直接实现，不判 unbounded query 缺陷（残余规模风险见第六节）。
- **排除孤儿 md**：`list_active_projects()` 以 `projects` 表为唯一数据源，**不扫描目录**（`repository.py:654-659`），孤儿 md 天然不进入结果；测试 `tests/memory/test_memory_documents_projects_api.py:44-58` 放入 `proj-alpha.md`/`proj-beta.md` 两个孤儿并用 `set(ids) == {p1,p2,p3}` 精确断言排除。
- **active 但无 md 文件仍列出**：复用 `read_document` → `_strict_read_path` 对 `FileNotFoundError` 返回空串、revision=`sha256(b"")`（`markdown_store.py:287-318,250-252`），符合 spec-038「缺失文件 = 空文档」，测试 `tests/...:81-84` 覆盖。
- 路由注册顺序：`/memory-documents/projects`（:687）在 `/memory-documents`（:724）之前，两者均为精确路径、无动态 `{id}` 吞并，无冲突。

### spec-038 冻结合同「零改动」核验 —— 属实

- `git diff -- backend/app/api/routes_conversations.py` 仅含 `+40` 行（常量 240 + 新端点），**`_memory_document_context`（:571-670）、`GET /memory-documents`（:724-742）、`PUT /memory-documents`（:745-840）逐字未出现在 diff 中**，即零改动。
- OCC revision：PUT 的 `_MEMORY_DOCUMENT_REVISION` 校验（:782）、`write_document` CAS 与 `MemoryDocumentConflictError` 分支（:800-817）全部未动；新接口只读复用 `read_document` 的 `revision`（`sha256(content)`，`markdown_store.py:250-252`），与 OCC 同源，**未造第二套文档读取/哈希实现**。
- 新增测试 `tests/...:119-134` 验证 archived 项目单文档 GET 仍返回 `409 PROJECT_NOT_ACTIVE`，active 校验未放宽。未显式新增「PUT OCC 冲突」冻结锁，但 PUT 代码零改动 + 既有 `tests/memory/test_memory_document_store.py` 已覆盖 `MEMORY_DOCUMENT_CONFLICT`，风险低（见 LOW-4 建议）。

---

## 三、技术正确性核验

| 核验点 | 结论 | 依据 |
|---|---|---|
| `duration_ms` 时间缺失/非法/倒挂/超长 | 全返回 `None`，不造 0 | `routes_research.py:675-693`；测试 6 组参数化 |
| 时区 / naive UTC 归一 | 实现正确（统一 UTC 后相减，规避 naive/aware 相减 TypeError） | `routes_research.py:681-684`；**但零测试覆盖，见 MEDIUM-2** |
| `started_at` 领域模型不存在 | 诚实 `None` | `routes_research.py:703`；`models.py:15-35` |
| 新接口 503 稳定错误体 | `except HTTPException: raise` + 三类异常 + 兜底 `except Exception` 全部映射到 `_memory_document_unavailable`（503 + `MEMORY_DOCUMENT_UNAVAILABLE`），符合回归清单第 11 条 | `routes_conversations.py:715-721`；测试 `tests/...:103-116` |
| `project_id` 路径安全 | 新接口 project_id 来自 DB 的 `Project` 对象（非用户输入）；`read_document`→`document_path`→`_project_path` 仍有三道防线（非空/长度/白名单正则/realpath 越界），即便 DB 被注入恶意 id 也会拦截 | `routes_conversations.py:703`；`markdown_store.py:169-207,254-284` |
| 多项目逐个读文件（N+1） | N 次磁盘读是「一次性列全」需求固有，非 DB N+1；但**异常隔离缺失**，见 MEDIUM-1 | `routes_conversations.py:702-713` |
| `list_active_projects()` 过滤条件 | 严谨（严格 `active` + 参数化 + 不扫目录），仅有一处冗余条件，见 LOW-2 | `repository.py:647-660` |
| `content_excerpt` / `content_length` | `content[:240]` 按 Unicode 字符切分（中文安全）；`content_length=len(content)` 为全文长度而非截断后长度；revision 仍基于全文 | `routes_conversations.py:709-711`；测试 `:87-100,:68-84` |

---

## 四、测试诚实性

- **13 个用例真实通过**：`.venv/bin/python -m pytest tests/research/test_task_summary_timing.py tests/memory/test_memory_documents_projects_api.py -q` → `13 passed`。
- **无 skip / xfail / TODO / 裸 pass / 恒真断言**：grep 确认；断言为逐字值（`90000`/`5000` ms、`is None` 且 `!= 0`、`set(item) == expected_fields` 精确集合、`sha256` 逐字、`content.startswith(excerpt)`、稳定码 `MEMORY_DOCUMENT_UNAVAILABLE` / `PROJECT_NOT_ACTIVE`）。`assert summary["duration_ms"] != 0` 位于 `is None` 之后属冗余但非「恒真蒙混」（真值已被前一条锁死），不构成回归清单第 12 条所禁的「同响应读出再自比」。
- **RED→GREEN 诚实性**：`backend-dev` 日志记载 RED = `12 failed / 1 passed`（唯一通过的是既有 archived 守卫），GREEN = `13 passed`。我用 `git show HEAD:` 独立佐证：`_task_duration_ms` / `list_active_projects` / `memory-documents/projects` / `"started_at"|"duration_ms"` 在 HEAD 中计数**全为 0**（功能确实不存在），配合上述非恒真断言可推出 RED 必然成立。**如实标注：具体的 12/1 数字采信 dev 日志，本次为只读评审未亲自 revert 复跑 RED**，但已用 HEAD 基线做了独立交叉验证，非凭回传摘要下结论。
- **放宽断言**：存在 1 处，见 LOW-3。
- **隔离性**：`conftest.py:40-46` 的 autouse fixture 把 `markdown_store.MEMORY_DIR` 隔离到 `tmp_path/memory`，测试写入真实临时 md 文件并真实读取，非纯 mock 空跑。

---

## 五、代码质量 / 分层 / lint

- **分层**：新接口在 api 层组合 `_repo()` + `MarkdownMemoryStore` + `list_active_projects()`，与既有 `_memory_document_context`（`routes_conversations.py:606-608`）完全同构；数据访问落在 repository 层，md 读写经既有 store，未越过 service 直写裸 SQL 到业务文件，未引入新分层越界。
- **禁止重复实现**：复用 `read_document`（文档读取 + revision）、`_memory_document_unavailable`（稳定 503）、`OWNER_ID`、`_project` 行映射；未出现第二套下载/安全/导入/批任务/身份/embedding/文档哈希实现。`list_active_projects` 与 `list_projects` 虽同查 projects 表，但语义不同（全量 active vs 分页按活跃度），复用同一行映射，不构成第二套。
- **ruff 零新增 —— 属实**：工作区三文件 16 errors；用 `git show HEAD:<f> | .venv/bin/python -m ruff check --stdin-filename ... -` 做基线对比，`routes_research.py HEAD=1/WORKTREE=1`、`routes_conversations.py 0/0`、`repository.py 15/15`，集合完全一致（仅行号因新增下移）。本轮新增 92 行未引入任何新 lint。
- **命名/注释**：`_MEMORY_DOCUMENT_EXCERPT_CHARS=240` 为命名常量（非裸 magic number）；docstring 解释了「为何用 created_at」「为何不扫目录」「spec-038 契约不变」等 WHY，清晰。唯 `_task_duration_ms` 形参命名与语义不符，见 LOW-1。
- **域回归**：`tests/memory/` = 136 passed；research 相关 78 passed；无既有契约回归。

---

## 六、风险（逐条回答用户要点 5）

- **数据清理误删**：前缀固定 + 参数化 + 精确 task_id 关联 + 实况逐表比对，误删真实数据风险极低；3 个真实任务、2 个项目、文献地图库均完好。
- **备份是否足够**：两库清理前快照可读、可回滚，已验证含 `seed=2`；`.gitignore` 已排除入库。残余项：备份为单文件 cp、未含 `-wal/-shm`（LOW-4），但实况主库已含完整清理前数据，回滚可用。
- **跨库原子性**：`clean()` 用两个独立 `sqlite3.connect` 事务（research 库 / memory 库），非单事务；若第二步失败会残留 seed 会话。本轮已执行成功且实况一致，属一次性脚本的残余风险（LOW-4）。
- **鉴权 / 限流**：项目为单用户本地应用（`OWNER_ID` 常量），既有 `GET/PUT /memory-documents` 及全部 memory 端点均无鉴权/限流；新接口沿用同一威胁模型，**不引入新的鉴权缺口**。但新接口一次性读取全部 active 项目文档，单次代价高于单文档端点，若将来服务暴露公网会成为更明显的放大面 —— 建议纳入「公网暴露前统一补鉴权/限流」的架构待办，非本轮缺陷。
- **无 LIMIT 规模风险**：用户裁决明确要求一次性全量，属产品决策；当前 `projects` 表仅 2 条 active，无现实压力。建议在项目数可能增长时评估响应体积 / 超时上限。

---

## 七、问题清单（按严重度排序）

> 统计：CRITICAL 0 / HIGH 0 / MEDIUM 2 / LOW 4。Verdict: **APPROVE（通过，附意见）**。以下 MEDIUM/LOW 沉淀为**强制约束清单**，建议下批次落实。

### [MEDIUM-1] 循环内无单项目异常隔离：一个坏文档 → 整个列表 503

- 文件：`backend/app/api/routes_conversations.py:702-721`（另见 `backend/app/memory/repository.py:264-269`）
- 问题：`for project in repo.list_active_projects(OWNER_ID)` 循环整体包在**一个** `try` 内（:698-721）。任一项目的 `store.read_document` 抛出（`_strict_read_path` 对 `PermissionError`/`UnicodeDecodeError` 抛 `MemoryDocumentUnavailableError`，`markdown_store.py:293-298`；或路径越界 `MemoryDocumentPathError`），以及 `:712` 的 `project.updated_at.isoformat()` 在历史行 `updated_at IS NULL` 时（`_dt` 返回 `None`，`repository.py:113-114`）抛 `AttributeError`，都会被 `except Exception`（:719）统一转成**整表 503**，所有其余正常 active 项目的记忆一条都列不出来，且响应不指出是哪个项目失败。这与裁决③「所有 active 项目的记忆一次性全部列出」的可用性目标冲突，也是用户要点 2 点名的「异常隔离问题」。
- 触发条件需至少一个 active 项目的 md 损坏（用户手工写入非法 UTF-8 / 权限问题），本地单用户概率不高，且失败是 fail-closed 稳定 503（不返回错误数据），故判 MEDIUM 而非 HIGH。
- 建议：在循环内对每个项目单独 `try/except`，单项目失败降级（该条目置 `content_excerpt=""` + 稳定 `error` 标记，或跳过并在响应聚合 `unavailable` 列表），保证其余 active 项目仍全部列出；`updated_at` 用 `(project.updated_at or project.created_at).isoformat()` 或显式判空。补一条「其中一个项目读取抛异常，其余项目仍 200 且列出」的回归用例。

### [MEDIUM-2] `duration_ms` 的时区 / naive UTC 归一逻辑零测试覆盖

- 文件：`backend/app/api/routes_research.py:675-686`；`tests/research/test_task_summary_timing.py:45-84`
- 问题：`_parse` 专门写了「naive 补 UTC、aware 转 UTC、再 `astimezone(utc)`」这段最易出错的兼容逻辑（注释明确指向「历史行可能是 naive UTC」），但 13 个用例中**没有任何一个**覆盖：带 `+08:00` 等时区偏移、naive UTC 无后缀、或两种形态混合相减。用户评审要点 2 明确把「时区」列为必验边界，而测试实际只用了 `Z` 结尾的 UTC 与非法/缺失值，「关键边界全覆盖」名不副实。此分支若回归（例如 naive/aware 相减抛 `TypeError` 冒泡成裸 500），现有测试无法拦截。
- 建议：补 3 组逐字断言 —— `created_at` 带 `+08:00` 与 `completed_at` 带 `Z` 算出的墙钟差正确（非 `None`、非 0）、naive UTC 与 aware UTC 混合不抛异常、以及「同一时刻不同时区」结果为 `0` 但属合法（不是造 0）。此条与 LOW-1 一并纳入 TDD 约束。

### [LOW-1] `_task_duration_ms` 形参名与实际语义自相矛盾

- 文件：`backend/app/api/routes_research.py:668`（形参 `started_at`）、`:722`（实参 `task.created_at`）
- 问题：签名 `_task_duration_ms(started_at, completed_at)`、docstring 首行却写「completed_at − created_at 的毫秒差」，调用处传的是 `created_at`。而 summary 的 `started_at` 字段恒为 `None`（:703）。于是响应会出现 `started_at: null` 与 `duration_ms: 291000` 并存，前端易误读为「有开始耗时」。`duration_ms` 实为 created→completed 的墙钟时长（含排队/等待），并非真正「执行耗时」。
- 建议：形参重命名为 `created_at`（或 `interval_start`），docstring 明确「领域模型无 started_at，duration 以 created_at 起算，含等待时间」；不改行为、不改契约。

### [LOW-2] `list_active_projects` 冗余过滤条件

- 文件：`backend/app/memory/repository.py:656`
- 问题：`status='active' AND status!='deleted'` 中后半条件在 `status='active'` 下恒真，属冗余（不影响结果严谨性，无漏/多行）。另 `SELECT *` 无 LIMIT 已确认是裁决「一次性全量」的要求，不判缺陷。
- 建议：删除冗余条件或加注释说明其防御意图；无行为变更。

### [LOW-3] excerpt 上限常量 240 未被测试精确锁定（放宽断言）

- 文件：`tests/memory/test_memory_documents_projects_api.py:99`；`backend/app/api/routes_conversations.py:684`
- 问题：`test_long_content_excerpt_is_a_bounded_prefix` 仅断言 `0 < len(content_excerpt) < 300` 且是正文前缀。把 `_MEMORY_DOCUMENT_EXCERPT_CHARS` 从 240 改成 1 或 299，该测试仍全绿。用户要点 3 明确要求查「放宽断言」，这是唯一一处。另 `assert "proj-alpha" not in str(body)`（:58）为字符串弱断言，但已被 `set(ids) == {p1,p2,p3}` 精确集合断言兜底，不构成实质漏洞。
- 建议：加 `assert len(item["content_excerpt"]) == _MEMORY_DOCUMENT_EXCERPT_CHARS`（或直接 `== 240`），并补一条正文恰好 240 字符「不截断」的边界用例。

### [LOW-4] 数据清理的非原子性与备份形态（残余风险，非本轮代码缺陷）

- 文件：`scripts/seed_demo_research_reports.py:278-298`（既有脚本，本轮未改）；`data/backup/20261109-cleanup/`
- 问题：`clean()` 用两个独立连接/事务分别删 research 库与 memory 库，跨库非原子；备份为两库单文件 cp，未含 `-wal/-shm`。本轮已执行成功、实况一致、备份可读出清理前数据可回滚，风险已释放。另建议补一条 PUT OCC revision 冻结锁（`tests/memory/test_memory_documents_projects_api.py` 现仅锁 GET 的 active 守卫）。
- 建议：后续把清理纳入单事务/带前置 checkpoint 的备份流程（`sqlite3 .backup` 或 `PRAGMA wal_checkpoint` 后再 cp），并将 OCC PUT 冻结锁纳入 TDD 约束；本轮不要求改动。

---

## 八、值得肯定的点

1. **诚实性设计**：`started_at` 用 `getattr` 在领域模型无此字段时返回 `None` 而非编造；`duration_ms` 对缺失/非法/倒挂一律 `None` 而非造 `0`（`0` 会被前端渲染成「瞬间完成」的误导数据）。这正面回应了「清掉伪造三同时间戳假数据」的根因，未改 schema、未落库、未污染领域模型。
2. **冻结契约守得住**：spec-038 的 GET/PUT 与 `_memory_document_context` 逐字零改动，新接口只读复用 `read_document` 的 OCC revision，没有为「列表」另造第二套文档读取/哈希/路径实现，符合项目「禁止重复实现」硬约束。
3. **安全复用而非重写**：project_id 来自服务端 DB 且仍经过 `_project_path` 三道路径防线；SQL 全部参数化占位符；孤儿 md 靠「以表为唯一数据源、不扫目录」天然排除，而非靠黑名单过滤，思路正确且难以绕过。
4. **回归清单第 11 条落实到位**：端点内新增的 `list_active_projects` / `read_document` 全部纳入 `try`，`except HTTPException: raise` 保证业务错误原样透传，任何依赖故障统一 503 + 稳定 `code`，并有专门 monkeypatch 用例（`tests/...:103-116`）逐字断言，不是裸 500。
5. **测试非恒真、非静默失效**：13 例用逐字值/精确集合/`sha256` 逐字断言，autouse fixture 真实隔离 MEMORY_DIR 并读写临时 md 文件；RED 由 HEAD 基线独立佐证（新增符号在 HEAD 全为 0），非「先写实现再补恒真测试」。
6. **ruff 零新增可复核**：用 `git show HEAD` 经 stdin 做基线对比（16→16 集合一致），声称属实、方法可复现，不是口头结论。
7. **数据清理克制且可回滚**：严格限定 `seed-demo-` 前缀、复用既有 `--clean` 入口而非新写删除脚本、清理前后逐表计数留痕、备份保留并正确加入 `.gitignore`；3 个真实任务与文献地图演示数据完好。
8. **路由与兼容细节**：新静态路由注册在既有精确路由之前无冲突；`_task_summary` 新增字段为增量兼容，5 处复用点经域回归（memory 136 / research 78 passed）确认零破坏。

---

## 九、验证命令与结果（均为只读或 pytest 运行）

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/research/test_task_summary_timing.py tests/memory/test_memory_documents_projects_api.py -q` | `13 passed` |
| `.venv/bin/python -m pytest tests/memory/ -q -p no:cacheprovider` | `136 passed` |
| `.venv/bin/python -m pytest tests/research/ -q -k "summary or list or timing or task_detail or notification"` | `78 passed / 1090 deselected` |
| `.venv/bin/python -m ruff check --output-format=concise <3 后端文件>` | 16 errors（全部既有） |
| `git show HEAD:<f> \| ruff check --stdin-filename ... -` | HEAD=16 / WORKTREE=16，集合一致 → 零新增 |
| `git show HEAD:<f> \| grep ...` | 4 个新增符号在 HEAD 计数全 0 → RED 佐证 |
| `git --no-pager diff -- <4 后端文件>` | 冻结 GET/PUT/context 零改动 |
| `sqlite3 mode=ro` 只读查询两库 + 备份 | 清理前后逐表差值与描述吻合，备份可回滚 |
| `grep -nE "skip\|xfail\|TODO\|assert True" <2 测试文件>` | 无命中 |

---

## 十、评审产出路径

- 评审报告：`docs/sdd/reviews/20261109-demo-data-cleanup-backend-review.md`（本文件）
- 进展日志：`.codebuddy/agent-logs/spec-regression/task-demo-data-cleanup/backend-reviewer/20261109-053843.md`
