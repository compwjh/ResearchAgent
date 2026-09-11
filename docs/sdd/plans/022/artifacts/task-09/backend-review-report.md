# Spec022 Task09 后端评审报告

## 结论

**最终复审 GO（P0=0、P1=0）**。第三轮 v3 cursor scope kind 已修复上一轮发现的项目筛选 cursor 隔离问题；本报告末尾“第三轮最终复审”记录最新证据。pytest 仍受本机依赖环境阻塞，需在可用环境补跑后端精确测试，但未发现实现级 P0/P1。

但本机无法完成 pytest 收集：项目 `.venv/bin/pytest` 的 shebang 指向已不存在的 `/Users/wjh/PyCharmMiscProject/.venv/bin/python`，系统 Python 又缺少 `fastapi`。因此本报告不能替代依赖修复后的定向 pytest 验收；主 Agent 收口前必须在可用项目环境重跑该测试。

## 评审范围与时间

- 角色：backend-reviewer；范围仅 `backend/**` 与 Task09 后端定向测试。
- 对照：`docs/sdd/specs/022-project-conversation-memory.md` 的项目模型/API，`docs/sdd/plans/022/task-09-desktop-project-tree-sidebar.md`，`docs/sdd/reviews/022-task09-tech-review.md`，以及后端实现/测试交接报告。
- 改动：`backend/app/memory/models.py`、`backend/app/memory/repository.py`、`backend/app/api/routes_conversations.py`、`tests/test_task09_project_activity.py`。
- 时间：2026-09-11；只读评审，未修改业务代码。

## 逐项核对

### 1. `last_activity_at` 语义与边界：通过

- `backend/app/memory/repository.py:520-531` 使用单条 CTE 聚合项目及会话；`LEFT JOIN` 条件包含 `c.owner_id = p.owner_id`，并过滤 `c.status != 'deleted'`，因此 owner 隔离正确、deleted 会话不参与、archived 会话仍参与。
- `backend/app/memory/repository.py:522-524` 以 `MAX(c.updated_at)` 与项目 `p.updated_at` 取较新值；无会话或仅 deleted 会话时回退项目自身时间。
- `backend/app/memory/repository.py:525-531` 过滤 `p.owner_id=? AND p.status!='deleted'`，不会将 deleted 项目列入普通列表。
- `backend/app/memory/models.py:15-17` 仅增加非持久化 read-model 字段；未新增 schema 列或迁移。
- `tests/test_task09_project_activity.py:24-53` 覆盖无会话、active、archived、deleted-only 和 foreign owner 情形。

### 2. 单 SQL 聚合与 N+1：通过

- `backend/app/memory/repository.py:517-539` 项目列表只执行一条 CTE/聚合查询，没有按项目逐个查询会话。
- `tests/test_task09_project_activity.py:78-95` 通过 monkeypatch 统计 `repo.connection()` 仅调用一次，直接覆盖 N+1 约束。

### 3. 排序、cursor 键集、编码和错误处理：通过

- `backend/app/memory/repository.py:515-516,535-536` 页内过滤和排序均使用 `last_activity_at DESC, project_id DESC`；续页条件是严格小于时间或同时间 `project_id < ?`，与排序方向一致。
- `backend/app/memory/repository.py:514,541` 使用独立 cursor kind `projects_activity`，编码的时间值来自查询返回的 `last_activity_at`，不会把旧 `projects`/`updated_at` cursor 混入新 keyset。
- `backend/app/memory/repository.py:72-80` 的 `decode_cursor` 对版本、kind、时间键和 ID 做结构校验并统一抛出 `ValueError("invalid cursor")`；`backend/app/api/routes_conversations.py:79-84` 将其映射为 400 `INVALID_CURSOR`。
- `tests/test_task09_project_activity.py:56-75` 覆盖并列时间的 `project_id DESC`、跨页无重复/遗漏和旧 kind 拒绝。

### 4. API payload 与旧客户端兼容：通过

- `backend/app/api/routes_conversations.py:42-43` 保留既有 `project_id/owner_id/name/instructions/status/created_at/updated_at` 字段，并始终增加 `last_activity_at`；point read 没有聚合列时安全回退 `updated_at`。
- `backend/app/api/routes_conversations.py:78-84` 仍复用原 `/api/projects` endpoint、`cursor`/`limit` 参数和 `projects`/`next_cursor` 响应结构；新增字段为兼容性追加。
- 旧 cursor 不会静默产生错序数据，而是以稳定 400 拒绝，符合技术评审冻结的“不混用旧 updated_at cursor”要求。
- `tests/test_task09_project_activity.py:98-117` 覆盖创建响应与列表响应均含字段，并验证会话活动时间可见。

### 5. 不越界语义：通过

- diff 仅触及 Project read model、项目列表 projection/cursor、项目 payload 和定向测试；未新增表、列或迁移。
- 未修改 `update_conversation()` 的 owner/active 校验、`confirm_move`、memory binding/evidence 清理；未修改项目删除、会话删除、RAG 或记忆 worker 路径。
- `git diff --check` 对评审范围通过。

## 问题分级

| 级别 | 数量 | 条目 |
|---|---:|---|
| P0 | 0 | 未发现数据泄漏、跨 owner 访问或不可逆语义回退 |
| P1 | 0 | 未发现聚合、排序/cursor、分页或 API 字段契约缺陷 |
| P2 | 1 | 定向 pytest 受本机依赖环境阻塞，需在可用环境补跑；另有测试覆盖增强建议 |

### P2-1：pytest 环境阻塞与覆盖增强

实际执行 `.venv/bin/pytest -q tests/test_task09_project_activity.py` 退出码 **127**（失效 shebang）；执行 `python -m pytest -q tests/test_task09_project_activity.py` 退出码 **2**（`ModuleNotFoundError: No module named 'fastapi'`）。这不是业务代码缺陷，但 API payload 测试和既有会话回归尚未取得真实 pytest 绿灯。建议主 Agent 在安装/恢复项目依赖后重跑：

```text
pytest -q tests/test_task09_project_activity.py
```

可选增强测试：补充“项目 `updated_at` 晚于会话时间”的回退分支，以及通过 HTTP endpoint 发送 malformed cursor 并断言 400 `INVALID_CURSOR`；当前 repository/route 实现已沿用既有 cursor 错误语义。

## 定向验证

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| Python 语法 | `python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/api/routes_conversations.py tests/test_task09_project_activity.py` | 0 | 通过 |
| 精确 pytest（项目 venv） | `.venv/bin/pytest -q tests/test_task09_project_activity.py` | 127 | 阻塞：shebang 指向不存在解释器 |
| 精确 pytest（系统 Python） | `python -m pytest -q tests/test_task09_project_activity.py` | 2 | 阻塞：缺少 `fastapi` |
| 代码风格/冲突检查 | `git diff --check -- backend/app/memory/models.py backend/app/memory/repository.py backend/app/api/routes_conversations.py tests/test_task09_project_activity.py` | 0 | 通过 |
| 行为探针 | 临时 SQLite 验证 malformed cursor 返回 `ValueError("invalid cursor")` | 0 | 通过 |

未运行全量 pytest、前端测试、部署或服务 smoke，符合 Task09 后端 reviewer 的单端范围。

## 主 Agent 动作与签字

1. 在可用项目依赖环境重跑 Task09 后端精确 pytest；若失败，先按失败用例修复并重新评审。
2. 合并前保留本报告的测试环境阻塞说明，不将 `py_compile`/行为探针误记为 pytest 通过。
3. 定向 pytest 通过且前端 reviewer/tester 通过后，继续跨端验收；本后端评审不批准全量回归或部署收口。

签字：backend-reviewer（GO；无 P0/P1）

---

## 最终复审：会话筛选与 cursor 隔离（2026-09-11）

### 结论

**NO-GO（P1=1，P0=0，P2=1）**。`status=active|archived`、`unbound_only=true`、非法组合校验、默认无筛选兼容、绑定项目 archived 会话可见性及 owner SQL 过滤均正确；但 `project_id` 筛选在 `status=None` 时仍使用旧通用 cursor kind，导致不同项目（以及项目列表与默认未绑定列表）可以互相复用 cursor，违反本轮明确的“筛选签名与 cursor 隔离”要求，可能造成跨页遗漏或错误空页。

### 通过项

- **状态筛选与归档可见：通过。** `backend/app/memory/repository.py:644-661` 只接受 `active|archived`；显式 status 且未指定 project 时不追加 `project_id IS NULL`，所以 `status=archived` 能看到绑定项目和未绑定的 archived 会话，同时排除 deleted。
- **未绑定筛选与非法组合：通过。** `backend/app/memory/repository.py:646-647,652-654` 使 `unbound_only=true` 只返回 `project_id IS NULL`，与任何 `project_id` 组合抛出稳定 `ValueError`；`routes_conversations.py:344-346` 映射为 400 `INVALID_CONVERSATION_FILTER`。
- **默认兼容：通过。** 无 `status` 且无 `unbound_only` 时仍走 `project_id IS NULL AND status!='deleted'`，cursor kind 仍为 `conversations`，保持旧未绑定列表行为。
- **绑定项目 archived 会话/恢复路径：通过。** `project_id` 仍先经 `get_project(project_id, owner_id)` 校验且仅排除 deleted 项目；项目过滤再按 `status` 筛选，因此绑定 archived 会话可见。`update_conversation()`/restore 逻辑未被本增量修改，仍按 owner 及既有状态语义恢复。
- **owner 隔离：通过。** `backend/app/memory/repository.py:668` 继续以 `owner_id=?` 作为查询条件，项目存在性也在 `:655-656` 使用同 owner 校验；未发现跨 owner 返回数据。
- **范围边界：通过。** 增量只改 `list_conversations()` 和 GET route 参数/错误映射；未改 schema、PATCH、删除、memory binding、RAG 或 worker。

### P1-1：`project_id` 无 status 时 cursor kind 未签名隔离

证据：`backend/app/memory/repository.py:662-664` 仅在 `status is not None or unbound_only` 时生成 v2 kind；因此以下请求均使用旧通用 kind `conversations`：

```text
list_conversations(owner, project_id="project-a", status=None, unbound_only=False)
list_conversations(owner, project_id="project-b", status=None, unbound_only=False)
list_conversations(owner, project_id=None, status=None, unbound_only=False)
```

在定向探针中，项目 A 首页产生的 cursor 被项目 B 接受并返回 B 的数据，也被默认未绑定列表接受并返回空页，而不是 400 `invalid cursor`：

```text
p1_page ['a1'] cursor? True
p2_reuse_ACCEPTED ['b1']
default_reuse_ACCEPTED []
```

这不是数据越权（查询仍有 owner/project 条件），但会造成 cursor 语义跨筛选复用，导致分页遗漏/空页，直接违反筛选签名隔离契约。修复应让所有非默认筛选（至少 `project_id`、`status`、`unbound_only`）进入稳定 cursor kind；同时保留无筛选默认 `conversations` kind 以维持默认兼容。修复后补充项目 A/B 和 project/default 互换 cursor 的拒绝测试。

### P2-1：owner 未进入 cursor 签名（非 HTTP 阻塞）

HTTP route 固定 `OWNER_ID`，因此当前不会形成跨用户 API 复用；repository 级调用若将 owner A 的 cursor 传给 owner B，仍可能合法解析并造成分页截断。建议修复 P1 时一并把 owner 纳入 cursor kind 或增加 cursor owner 绑定校验，作为仓储层硬化项。

### 最终复审验证

| 检查 | 命令/探针 | 退出码 | 结果 |
|---|---|---:|---|
| Python 语法 | `python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/api/routes_conversations.py tests/test_task09_conversation_filters.py tests/test_task09_project_activity.py` | 0 | 通过 |
| 精确 pytest | `.venv/bin/pytest -q tests/test_task09_conversation_filters.py tests/test_task09_project_activity.py` | 127 | 阻塞：venv shebang 指向不存在解释器 |
| 代码风格/冲突检查 | `git diff --check -- backend/app/memory/models.py backend/app/memory/repository.py backend/app/api/routes_conversations.py tests/test_task09_conversation_filters.py tests/test_task09_project_activity.py` | 0 | 通过 |
| 归档绑定/恢复与 owner 探针 | 临时 SQLite：绑定 archived 会话可按项目列出、可恢复为 active，owner B 返回空 | 0 | 通过 |
| cursor 隔离行为探针 | 临时 SQLite：项目 A cursor 复用于项目 B/默认未绑定列表 | 0 | **失败性证据：当前实现错误接受复用** |

### 主 Agent 动作与签字

1. 修复 `list_conversations()` 的 cursor kind，使 `project_id` 参与非默认筛选签名；保留默认无筛选 `conversations` kind 的兼容行为。
2. 增加项目 A/B、项目/默认列表互换 cursor 的拒绝测试，并保留现有 status/unbound_only 筛选测试。
3. 在可用依赖环境重跑两项 Task09 后端精确 pytest、py_compile 和 diff check；修复后由 backend reviewer 重新复审。

最终签字：backend-reviewer（NO-GO；P1-1 未修复）

---

## 第三轮最终复审：v3 conversations cursor scope kind（2026-09-11）

### 最终结论

**GO（P0=0、P1=0；P2=2）**。`list_conversations()` 现在对 `project_id/status/unbound_only` 的完整组合生成稳定 v3 scope kind，cursor 过滤条件和查询过滤条件一致；默认、项目 A、项目 B、status、unbound 等 scope 之间的 cursor 互换均拒绝，同一 scope 的 keyset 分页无重复/遗漏。未发现 schema、PATCH、RAG 或删除语义改动。

### v3 scope 隔离核对

- `backend/app/memory/repository.py:662-669` 无条件构造 `conversations:v3:project={...}:status={...}:unbound={0|1}`，覆盖默认 scope（`project=*;status=*;unbound=0`）、项目 scope、全局 status scope、unbound scope 及其组合。
- cursor 解码使用当前完整 `cursor_kind`（`:665-666`），不同 scope 的 token 会统一抛出 `ValueError("invalid cursor")`，不会执行跨筛选 keyset。
- 查询参数仍按 owner、project、status 过滤（`:643-661,668`）；`status` 仅允许 active/archived，`unbound_only` 与 project_id 组合仍稳定拒绝。

### 行为证据

临时 SQLite 建立 owner-a 下的未绑定、项目 A、项目 B，各自 active/archived 会话，并验证以下 scope：

```text
default              6 unique, pages complete
project-a            6 unique, pages complete
project-b            6 unique, pages complete
status=active        9 unique, pages complete
status=archived      9 unique, pages complete
unbound              6 unique, pages complete
unbound+archived     3 unique, pages complete
project-a+archived   3 unique, pages complete
cross_scope_failures []
legacy_default_rejected invalid cursor
owner_b_archived_count 0
```

上一轮项目 A cursor 被项目 B/default 接受的问题已消失；v3 对默认 scope 也使用独立 kind，因此旧 `conversations` cursor 会被拒绝，不会静默错分页。默认无筛选的**数据行为**仍保持 `project_id IS NULL AND status!='deleted'`（`:648-660`）。

### 范围与兼容性核对

- **schema：通过。** 当前 diff 只改变 dataclass read model、项目 activity projection、会话列表过滤/cursor 和 GET route 参数；`SCHEMA_VERSION`、DDL、迁移文件均未改动。
- **PATCH/恢复：通过。** `update_conversation()`、`restore_conversation()` 未在本增量 diff 中修改；既有绑定、owner、历史策略与恢复语义保持不变。
- **RAG/删除：通过。** 未修改 RAG、memory worker、`delete_conversation()`、`delete_project()` 或文档关联路径。
- **owner：通过。** owner-a 查询只返回 owner-a；owner-b 的 archived 列表探针返回 0 条。owner 未编码进 v3 kind，但 HTTP route 使用固定 `OWNER_ID`，当前不构成跨用户 API 数据泄漏。

### P2 风险

1. 项目 venv 仍不可用，定向 pytest 尚未取得真实退出码 0；需恢复依赖后补跑。
2. v3 scope 全矩阵目前由评审 SQLite 探针覆盖，自动化测试尚未逐一断言默认/项目 A/项目 B/status/unbound 的所有互换拒绝；建议将该矩阵固化为测试，避免未来 cursor kind 回退。

### 第三轮最终验证

| 检查 | 命令/探针 | 退出码 | 结果 |
|---|---|---:|---|
| Python 语法 | `python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/api/routes_conversations.py tests/test_task09_conversation_filters.py tests/test_task09_project_activity.py` | 0 | 通过 |
| 精确 pytest | `.venv/bin/pytest -q tests/test_task09_conversation_filters.py tests/test_task09_project_activity.py` | 127 | 阻塞：venv shebang 指向不存在解释器 |
| 代码风格/冲突检查 | `git diff --check -- backend/app/memory/models.py backend/app/memory/repository.py backend/app/api/routes_conversations.py tests/test_task09_conversation_filters.py tests/test_task09_project_activity.py` | 0 | 通过 |
| v3 scope 全矩阵探针 | 默认/项目 A/项目 B/status/unbound 互换 + 同 scope 完整分页 | 0 | 通过；所有互换均 `invalid cursor`，各 scope 无重复 |
| owner/归档边界探针 | archived 绑定会话可列出/恢复；owner-b 无 owner-a 数据 | 0 | 通过 |

### 主 Agent 动作与签字

1. 保留 v3 scope kind，不回退到旧通用 `conversations` kind；将评审矩阵补入定向 pytest。
2. 恢复项目 Python 依赖并运行 `pytest -q tests/test_task09_conversation_filters.py tests/test_task09_project_activity.py`；pytest 通过后再进入跨端验收。
3. 不因本报告 GO 跳过依赖修复、后端测试或前端/集成验收。

最终签字：backend-reviewer（GO；无 P0/P1）
