# Spec-023 后端评审报告（Skill 与 Tool 管理模块）

> 评审角色：backend-reviewer ｜ 范围：`backend/**` + 后端测试（`tests/test_skill_registry.py`、`test_tool_registry.py`、`test_skill_intent.py`、`test_tool_executor.py`）
> 依据：`docs/sdd/specs/023-skill-tool-management.md`、`docs/sdd/plans/023/task-02-toolcall-feasibility/RESULT.md`（R1–R5）、`.codebuddy/skills/{backend-patterns,regression-guard,coding-standards}/SKILL.md`
> 工作区基线：分支 `fix/spec-020-empty-index-generation-bootstrap`，改动未提交
> 不在范围：`backend/app/knowledge_base/infrastructure/manifest_store.py`、`backend/app/api/routes_kb.py`（属 spec-020 BUG-05，已单独评审）；`frontend/**`（属 frontend-reviewer）
> 纪律声明：本报告全部结论基于真实文件与实跑证据（含 3 个临时复现脚本），未修改任何业务代码、测试、spec。

## 一、结论

**通过（附强制约束清单）** — 阻塞项 P0 数量：**0**。

判定理由简述：
1. **无安全阻塞**：Tool 执行无任意 URL / SSRF / 路径穿越入口，直接复用既有服务端固定白名单 `_paper_candidate_hosts`；新增代码无硬编码地址/模型名/机器绝对路径。
2. **R1 硬约束已落地**：`tool_executor._check_tool` 独立校验"工具名 ∈ 注册表且 enabled + 参数过 schema 白名单"，不依赖 Ollama 端校验（对应 RESULT.md 的"非法 tools 被静默忽略"结论）。
3. **不回归**：未点名 Skill 的链路事件序列与改动前一致（无新增事件、不额外调用 LLM），`chat_direct_stream` / `ollama_direct` 的新参数均为默认 None/空的无损扩展。
4. **无重复实现**：复用 `chat_direct_stream`、`_document_error`、`_atomic_bytes`、`MODEL_NAME`、`_paper_candidate_hosts`、`import_candidate`、`hybrid_search`，未造第二套 HTTP 客户端 / 原子写 / 错误体 / 状态存储 / 下载器。
5. 定向测试实跑 **91 passed + 6 subtests passed**（`.venv/bin/python -m pytest tests/test_skill_registry.py tests/test_tool_registry.py tests/test_skill_intent.py tests/test_tool_executor.py -q`），`import backend.app.main` 冒烟通过。

**放行条件**：P1-1、P1-2 为功能性缺陷（会导致 Tool 真实可用性下降 / 模型端消息协议不合法），必须在 spec-023 转 `已完成` 前修复或书面降级说明；其余 P2 建议同批或紧随修复。若坚持"不改代码即转完成"，则须在 spec 变更日志中显式记录两条 P1 为"已知限制"。

## 二、ECC Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 2     | warn   |
| MEDIUM   | 3     | info   |
| LOW      | 2     | note   |

Verdict: **WARNING** — 无 CRITICAL/HIGH 安全项；2 条 HIGH 为功能性问题，建议合并前修复。

> 说明：本表按 ECC 口径映射（本报告正文用 P0/P1/P2；HIGH ≈ P1，MEDIUM ≈ P2 中偏影响面，LOW ≈ P2 中偏整洁性）。

## 三、问题清单

### P1（HIGH / 需合并前处理）

#### P1-1　`search_paper_catalog` 的 `source` 选择逻辑把 `all`/`dblp` 都导向同源会议，且与对外声明语义不符

- **依据（代码事实）**
  - `backend/app/skills/registry.py:36-40`：Schema 声明 `source` 的 `enum=["usenix","dblp","all"]`，描述为"会议来源"。
  - `backend/app/skills/tool_dispatch.py:43-65`：`source_hint == "dblp"` 时在 `short_name` / `venue_aliases` 里找含 `"dblp"` 的会议；找不到就 `chosen = conferences[0]`；`source_hint == "all"` 时**完全不参与匹配**，同样落 `conferences[0]`。
  - 实跑 `/tmp/repro_search_tool.py`（真实配置，只读）输出：
    ```
    configured conferences: 4
      conf_id='ccs' short='CCS' ... / 'ieee-sp' short='IEEE S&P' ... / 'ndss' short='NDSS' ...
      conf_id='usenix-security' short='USENIX Security' ... aliases=['USENIX Security Symposium','USENIX Security']
    source='all'    -> chosen='CCS'
    source='dblp'   -> chosen='CCS'
    source='usenix' -> chosen='USENIX Security'
    ```
    即当前数据集中**不存在任何名字含 `dblp` 的会议**，`dblp` 与 `all` 双双静默退化为 **CCS**。
  - `backend/app/skills/tool_dispatch.py:76` 汇报文本为 `来源={getattr(chosen,'short_name','?')}`，会向模型回灌 `来源=CCS`，与模型传入的 `source="usenix"` 意图冲突。
  - **且选择被静默吞掉**：`PaperDiscoverySearchService.search` 内部 `_validate`（`paper_discovery_search.py:166-195`）会因 conference 不匹配抛 `PaperDiscoverySearchError`，被 `tool_dispatch.py:152` 的 `except Exception` 收敛为 `ok=False` + 通用 error，用户只会看到"执行失败：PaperDiscoverySearchError"，**不知道是"来源不可用"还是别的问题**。
  - 对照既有实现：`backend/app/api/routes_paper.py:167-197` 的 `search_paper_conferences` 用 `source.name / source.short_name / source.conference_id` 三字段叠加做大小写无关匹配；本适配器只匹配 `short_name` 子串 + `venue_aliases`，粒度更粗。
- **影响**：USENIX 场景下模型很可能按 Schema 传 `source="all"`（Schema 把 all 描述为"两者并行"），实际检索落到 CCS，**结果与 Skill 语义不符**，且错误信息不可诊断。属 spec 边界"Tool 调用必须过注册表白名单与参数校验"能过校验、但业务语义错的一类缺陷。
- **建议改法（任选其一，推荐 a+b）**
  - a. 让 `source` 语义与实现对齐：对 `all` 明确"USENIX 优先"（显式 `chosen = usenix_conference or conferences[0]`），对 `dblp` 找不到时**不要静默退化**，直接 `DispatchResult(ok=False, error="当前服务端未配置 dblp 来源")`。
  - b. `tool_dispatch.py:76` 的汇报文本改为回显**模型传入的 source 意图**与**实际选中的会议**两个字段，例如 `来源(请求)=all 来源(实际)=USENIX Security`，让模型能自我纠正。
  - c. 复用 `routes_paper.py` 的三字段匹配逻辑（或抽公共函数），不要维护第二套匹配规则。

#### P1-2　原生路径一次返回多个 `tool_calls` 时，消息历史被复制成多条 assistant 消息

- **依据（代码事实）**
  - `backend/app/skills/tool_executor.py:269-291`：`for tc in tool_calls:` 循环内，每个 `tc` 都调用一次 `self._append_tool_turn(messages, content, tool.name, norm_or_err, result)`。
  - `backend/app/skills/tool_executor.py:226-239`：`_append_tool_turn` 每调用一次就 append **一条** `role="assistant"`（其 `tool_calls` 只含**单个** tool_call）+ 一条 `role="tool"`。
  - 实跑 `/tmp/repro_multi_tc.py`（一轮返回 2 个 tool_calls），第二次模型调用看到的消息为：
    ```
    [2] role=assistant tool_calls=[{... 'kb_search' 'question':'a'}]
    [3] role=tool      name=kb_search content='ok'
    [4] role=assistant tool_calls=[{... 'kb_search' 'question':'b'}]
    [5] role=tool      name=kb_search content='ok'
    === 带 tool_calls 的 assistant 消息数： 2
    ```
    即模型原始的一条 assistant 消息（原生返回 2 个 tool_calls）被拆成 2 条，且两条的 `content` 都被写成**同一个** `content` 变量（若模型同轮既输出文本又输出多个 tool_calls，该文本会被**重复**）。
- **影响**：Ollama 并行 tool call 时消息协议不合法（assistant 消息数与原始轮次不符、id 与 message 不配对），可能导致下一轮模型输出异常或复述工具结果；同时 `content` 重复会污染上下文。当前测试 `test_native_executes_then_synthesizes`（`tests/test_tool_executor.py:120-139`）只覆盖**单** tool_call，故未被发现。
- **建议改法**：把一轮内所有 tool_call 聚合成**一条** assistant 消息（`tool_calls` 为列表，每个元素保留各自的 `id`），再 append 对应的 `role="tool"` 消息（`tool_call_id` 与 assistant 的 id 严格配对）；`content` 只在第一条（或整轮唯一那条）写入。
- **补充**：`tool_executor.py:276-280` 在 `tool is None` 时 `return`，会**丢弃同一轮中尚未处理的合法 tool_call**——这是可接受的"拒绝即停"策略，但建议在报告中明确为有意设计（当前无注释说明，且无测试覆盖"混合合法+非法多 tool_call"）。

### P2（MEDIUM / 建议修复）

#### P2-1　`registry.py` 中 `search_paper_catalog.entry` 指向不存在的代码路径，且测试无法拦截

- **依据**：`backend/app/skills/registry.py:29-32` 的 `entry` 字符串为
  `"backend.app.paper_discovery.application.paper_discovery_search.PaperDiscoverySearchService.search"`。
  实跑 `/tmp/repro_schema.py`（`importlib.import_module` 逐段解析）：
  ```
  [ENTRY-IMPORT-FAIL] search_paper_catalog: ... -> ModuleNotFoundError:
      No module named '...paper_discovery_search.PaperDiscoverySearchService';
      '...paper_discovery_search' is not a package
  [OK] download_and_import_paper: ...paper_import.import_candidate -> FOUND
  [OK] kb_search: ...retrieve.hybrid_search -> FOUND
  [OK] kb_ask: ...api.routes_kb.kb_ask -> FOUND
  ```
  而 `tests/test_tool_registry.py:63` 的断言仅为 `self.assertTrue(tool.entry)`，**任何非空字符串都能通过**。
  同时 `backend/app/skills/registry.py:125-131` 的 `kb_ask.entry = "backend.app.api.routes_kb.kb_ask"` 指向的是 HTTP 路由函数（`inspect.signature` 实测为 `(request: KBAskRequest)`），不是可复用的业务入口——与 `tool_dispatch.py:129-132` 实际用 `_kb_search`（即 `hybrid_search`）实现的行为不一致。
- **影响**：`ToolEntry.entry` 是模块自定的"必须指向真实可定位的代码入口（模块.函数）"审计字段（`models.py:44-45`、`registry.py:3-5`），当前 1/4 错、1/4 语义不符；审计与后续复用会误导。
- **建议改法**：① 修正 `search_paper_catalog` 为 `backend.app.paper_discovery.application.paper_discovery_search.PaperDiscoverySearchService.search` 对应的**可导入形式**（模块 `...paper_discovery_search` + 属性 `PaperDiscoverySearchService.search`，字段拆分为 `module` + `attr`，或改成 `backend.app.api.common._build_paper_search_service` 这类真实可导入符号）；② `kb_ask` 改为与实现一致的 `backend.app.knowledge_base.infrastructure.retrieve.hybrid_search` 或注明"经编排器合成"；③ 测试改为**真的去 import 并 getattr**（把 `test_tool_registry.py:63` 升级为导入校验），否则同类错误仍会静默通过。

#### P2-2　普通对话也会构造 Tool 注册表并读状态文件（无缓存，逐请求磁盘 I/O）

- **依据**：`backend/app/api/routes_chat.py:104-106` 在**任何**请求（含 `decision.status == "none"` 的普通对话）都执行
  `enabled_tools = [t for t in _tool_routes.get_tool_registry().list_tools() if t.enabled]`；
  `backend/app/skills/tool_service.py:54-55` 的 `list_tools()` → `_to_tool` → `_enabled_for` → `state_store.py:42-46 load_tool_states()` → `load()` → **每次重新读盘 + `json.loads`**（`state_store.py:25-34`，无 TTL / 无 mtime 缓存）。
- **影响**：普通对话每轮多出 1 次状态文件读取 + 4 次 `ToolEntry` 构造；虽不影响正确性，但把"与改动前完全一致"的普通链路从"零额外 I/O"变成"每轮一次磁盘读"，与 spec"未点名 Skill 时行为与今天完全一致"的表述存在偏差（行为表现一致，成本不完全一致）。
- **建议改法**：把 `enabled_tools` 的求值移到 `if decision.is_usable()` 分支内部（即用 `if decision.is_usable() and (enabled_tools := ...)` 短路，或先判 `is_usable()` 再取），或给 `SkillStateStore` 加基于 `st_mtime_ns` 的轻量缓存。

#### P2-3　计划 JSON 降级路径与 `system_prompt=None` 回退存在测试缺口

- **依据**
  - `backend/app/skills/intent.py:293`（`format_skill_hint`）与 `backend/app/api/routes_chat.py:96-99`：`disabled/not_found/ambiguous` 走"不调模型 + 提示 + 结束"，此处**发送了 SSE `result` 事件**。行为与既有前端契约一致（`frontend/app.js:230` 消费 `eventData.type === 'result' && eventData.message` 并 `addMessage`），判**无回归**；但**缺测试**：`tests/test_skill_intent.py:293-318` 仅断言响应文本含提示语，未断言事件类型与字段名，字段一旦改名会静默失效。
  - `backend/app/api/routes_chat.py:80-84`：`prompt` 仅在 `detail is not None` 且 `is_usable()` 时构造。`tests/test_skill_intent.py:270-291` 的 `matched` 用例依赖 `patch("backend.app.api.routes_chat.get_available_models")` 与真实 `demo-skill`，未覆盖"命中 Skill 但 `get_skill` 返回 None（目录竞态/被删）→ `prompt=None` → ToolLoop 以 `system_prompt=None` 运行"这一退化路径。
  - `backend/app/skills/tool_executor.py:248-252`：`system_prompt=None` 时消息列表**没有 system 消息**，Skill 正文完全丢失，模型只靠 user question 与 tool schema 决策——静默降级，无日志。
- **建议改法**：① 补路由断言 `result` 事件的 `type/message` 字段；② `get_skill` 返回 None 时记 `logger.warning` 并按 `not_found` 提示（而非静默无技能正文继续跑 Tool 循环）。

### P2 / LOW（整洁性与一致性）

#### LOW-1　`search_paper_catalog` 描述与实现细节不符（`all=两者并行`）
- 依据：`registry.py:39` 描述 `"all=两者并行"`，但 `tool_dispatch.py:53-65` 是单会议（`chosen` 单个）实现，不存在并行。与 P1-1 同源，建议一并修正文案，避免模型被误导。

#### LOW-2　`ruff check` 命中 1 处 `E402`（存量，非本次引入）
- 依据：`.venv/bin/python -m ruff check backend/app/skills/ backend/app/api/routes_skills.py backend/app/api/routes_tools.py backend/app/api/routes_chat.py` → `E402 backend/app/api/routes_chat.py:44:1 from backend.app.api.common import *`。`git show HEAD:backend/app/api/routes_chat.py` 第 32 行**已存在**该 `import *`，属存量问题，本次未恶化（新增 import 均在文件头）。判为 note，不阻塞。

## 四、重点核对项逐条结论（任务书 6 项）

| # | 核对项 | 结论 | 关键依据 |
|---|---|---|---|
| 1 | 安全：SSRF / 任意 URL / 路径穿越；白名单有效性；R1 后端自校验 | **通过（R1 有效，无 P0 安全项）** | `tool_dispatch.py:106-112` 复用固定白名单 `_paper_candidate_hosts`（`common.py:174-194`，含注释"不从候选 pdf_url 推导主机名"）；`tool_executor.py:204-215 _check_tool` 校验 name/enabled/参数白名单（required、未知参数拒绝、类型、enum、数组元素），`tool_executor.py:217-224 _safe_dispatch` 双保险；无 `validate_url` 绕过、无 `urllib`/`httpx` 直连用户输入 URL |
| 2 | 不回归：普通对话行为与改动前一致 | **通过（有 1 处成本偏差，见 P2-2）** | `intent.py:130-132` 未点名即 `none` 且**不调 LLM**（`tests/test_skill_intent.py:87-96` 用 `side_effect=AssertionError` 强证）；`routes_chat.py:89-92` `none` 时 `to_intent_event` 返回 None→不额外发事件；`ollama_direct.py:55-56,82-83,202-204` 新参数默认 None 时**不改请求体**；`chat_runner.run_chat` 的 `prompt` 参数为既有（`git diff backend/app/chat/application/chat_runner.py` 为空），`routes_chat.py:129` `prompt=None` 时行为等价于旧的 `run_chat(question, selected_model)`（HEAD 第 56 行） |
| 3 | 降级与容错：LLM 超时/报错降级为不执行；重试与轮次；状态文件缺失/损坏回退 enabled=true | **通过** | `tool_executor.py:260-264` 模型异常→`return`（不中断）；`tool_executor.py:346-368` `retry+1` 次后返回空 `ModelResponse`；`intent.py:180-184` 1 次重试后降级；`intent.py:156-158` 与 `routes_chat.py:77-78` 捕获后**降级为 none 并记 warning**；轮次上限 `tool_executor.py:41,198,258,319-325`；状态回退 `state_store.py:26-34` + `service.py:25-29` + `tool_service.py:39-43`，有测试 `test_skill_registry.py:141-148` / `test_tool_registry.py:65-74` |
| 4 | 禁止重复实现：是否复用既有符号 | **通过** | 复用 `chat_direct_stream`（`tool_executor.py:39,349`；`intent.py:27,168`）、`_document_error`（`routes_skills.py:19,49/56/59/62`；`routes_tools.py:19,50/57/60/63`）、`_atomic_bytes`（`state_store.py:16,65,87`，注释声明）、`MODEL_NAME`（`intent.py:26,170`）、`_paper_candidate_hosts`/`import_candidate`/`safe_import_error_message`（`tool_dispatch.py:99-126`）、`hybrid_search`（`tool_dispatch.py:83-88`）。**无**第二套 HTTP 客户端 / 原子写 / 错误体 / 状态存储 / 下载器 |
| 5 | 边界覆盖：spec 每条边界是否有测试；空目录、损坏 frontmatter、未注册/已禁用 Tool、参数非法 | **基本覆盖（缺口见 P2-3）** | 空目录/不存在 → `test_skill_registry.py:85-92,268-276`；损坏 frontmatter/无 frontmatter/缺 name → `test_skill_registry.py:105-131`；不存在 Skill → `:228-251` + `routes_chat.py:94-100` + `test_skill_intent.py:293-302`；已禁用 Skill → `test_skill_intent.py:304-311`；计划 JSON 未注册/已禁用 Tool → `test_tool_executor.py:157-236`；参数非法 → `:185-213`；降级/超时 → `:238-244,277-302`；轮次上限 → `:247-264`。**缺口**：`think=false`（spec 边界第 6 条）无直接断言；`result` 事件字段无断言；`prompt=None` 退化路径无测试 |
| 6 | 硬编码：地址、模型名、机器相关绝对路径 | **通过** | grep `192.168.`/`localhost`/`127.0.0.1`/`/Users/`/`http://` 在 `backend/app/skills/**`、`routes_skills.py`、`routes_tools.py` 仅命中 `__pycache__` 二进制；模型名统一 `MODEL_NAME`；`download_paper_skill.py` 的 `/Users/wjh/.codex/skills/download-paper` 已改为 `BASE_DIR/".agents"/"skills"/"download-paper"`（与注册表同一事实源） |

## 五、放行后强制约束清单（沉淀为后续 spec 的硬规则）

1. **Tool 执行三层校验不可省**：注册表成员资格 → `enabled` → schema 参数白名单；新增 Tool 时必须同时补 `_ADAPTERS` 条目与 `parameters.required`，并保证二者名字逐字一致（已由 `/tmp/repro_schema.py` 式校验验证，建议固化为测试）。
2. **`ToolEntry.entry` 必须是可 `import` + `getattr` 的真实符号**，测试须真的去导入（禁止 `assertTrue(tool.entry)` 这类弱断言）。
3. **禁止静默退化**：任何"找不到匹配来源/找不到 Skill 正文"的分支必须返回可读错误或写 warning 日志，不得仅依赖 `except Exception` 收敛成通用错误。
4. **原生 function calling 的多 `tool_calls` 必须聚合为单条 assistant 消息**（`id` 与 `role="tool"` 严格配对），新增用例覆盖"同轮多 tool_call"与"合法+非法混合"。
5. **未点名 Skill 的链路保持"零额外事件 + 零额外 LLM 调用"**；额外 I/O（状态文件读取）应置于 `is_usable()` 分支内或加缓存。
6. **新增 SSE 事件类型必须同时补前端消费断言与后端事件契约测试**（`result` / `intent` 的字段改名必须被测试拦截）。

## 六、评审方法可复现证据

| 命令 / 脚本 | 用途 | 结果 |
|---|---|---|
| `.venv/bin/python -m pytest tests/test_skill_registry.py tests/test_tool_registry.py tests/test_skill_intent.py tests/test_tool_executor.py -q` | 定向回归 | 91 passed, 6 subtests passed（4.04s） |
| `.venv/bin/python -c "import backend.app.main"` | 导入冒烟 | OK |
| `.venv/bin/python -m ruff check backend/app/skills/ .../routes_*.py` | 静态检查 | 仅 1 处存量 E402（`routes_chat.py:44`） |
| `/tmp/repro_multi_tc.py` | 复现 P1-2 | 2 个 tool_calls → 2 条 assistant 消息 |
| `/tmp/repro_schema.py` | 复现 P2-1 | `search_paper_catalog.entry` import 失败 |
| `/tmp/repro_search_tool.py` | 复现 P1-1 | `all`/`dblp` → 选中 CCS（真实 4 会议配置） |
