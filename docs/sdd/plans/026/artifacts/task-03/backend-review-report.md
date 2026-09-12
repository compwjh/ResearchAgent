# Spec 026 后端评审报告（Task 02 / Task 03 改动）

- 评审角色：backend-reviewer（只读评审）
- 评审时间：2026-09-12
- 评审对象：`backend/app/platform/ollama.py`、`backend/app/api/routes_conversations.py`、新增测试 `tests/test_spec026_capabilities.py`、`tests/test_spec026_options_endpoint.py`
- 评审依据：`docs/sdd/specs/026-reasoning-effort-feedback-fixes.md`、`docs/sdd/plans/026/task-02-backend-capability-semantics.md`、`docs/sdd/plans/026/task-03-backend-options-endpoint.md`、`docs/sdd/specs/024-visible-reasoning-controls.md` §能力接口请求与错误体
- 环境：`.venv/bin/python`（Python 3.11）；`OLLAMA_BASE_URL=http://192.168.31.180:11434`（LAN 主机可达，`/api/tags` 200，`/api/chat` 对任意测试模型名返回 404 → 等价于「探测全失败」），本机未安装 Ollama

## 结论

**通过。**

无 P0 / P1。3 条 P2（1 条为本次引入的重复探测，1 条为死代码隐患，1 条为复用/可读性）。10 条核实项全部为「符合」，其中 8 条有实测证据；未验证项已在文末单列，未编造结论。

## 一、评审范围与改动确认

`git diff` 显示后端改动仅 2 个文件（未越界到 `frontend/**`，前端交 `frontend-reviewer`）：

| 文件 | 改动 |
|---|---|
| `backend/app/platform/ollama.py` | `ReasoningCapabilities.default_effort` 改为 `Optional[str]`；新增 `_highest_supported()`；`probe_reasoning_capabilities` 全档失败不再 raise，返回 `unknown`；`get_reasoning_capabilities` 增加 `stale` 复用且不写缓存 |
| `backend/app/api/routes_conversations.py` | `_resolve_request_effort` 去掉 `RuntimeError` 分支、新增 `unknown`/`stale` 分流；新增 `_reasoning_options_payload`；`reasoning_options` 增加 `refresh` 参数、去掉 503、改为 200+`stale`/`unknown` 与 404 |

`git status`：`tests/test_conversations_api.py`、`tests/test_spec024_backend.py` **未被修改**（作为回归基线有效）。

## 二、逐条核实结果（10 条）

### 1. `probe_reasoning_capabilities` 不再抛异常；全档失败三字段成立；无路径伪造 `('off',)` —— 符合

- 证据：`backend/app/platform/ollama.py:111-112` 全空时 `return ReasoningCapabilities(model, (), None, "unknown", "", {})`；函数体内已无 `raise`（`ollama.py:83-113`）。异常仅在 `ollama.py:109` 被 `except (httpx.HTTPError, ValueError, TypeError): continue` 吸收。
- 实测（monkeypatch `httpx.post` 抛 `httpx.ConnectError`）：

```
(a) probe all-fail -> unknown () None ''
(a) get(no cache)  -> unknown () None
(a) cache untouched: True
```

- 关于「伪造 `('off',)`」：唯一会产出 `('off',)` 的是 `ollama.py:67-68` 的 `_capabilities_for_model()`。全仓库 grep 确认它**只有定义、无任何调用点**（`grep -rn "_capabilities_for_model"` 仅命中定义处与两份文档），故**无活跃路径伪造支持集**；该函数为死代码隐患，见 P2-2。

### 2. `default_effort` 取序位最高 —— 符合

- 证据：`ollama.py:71-80` `_highest_supported()` 先按 `REASONING_EFFORTS` 过滤再取 `[-1]`，空集返回 `None`；调用点 `ollama.py:113`。
- 实测（直接 import 真实实现，11 组用例）：

```
REASONING_EFFORTS = ('off', 'low', 'medium', 'high', 'xhigh')
['off', 'low', 'medium']                      -> 'medium'   expected 'medium'   OK
['off', 'xhigh']                              -> 'xhigh'    expected 'xhigh'    OK
['off']                                       -> 'off'      expected 'off'      OK
[]                                            -> None       expected None       OK
('medium', 'off', 'low')                      -> 'medium'   expected 'medium'   OK   # 乱序输入
('xhigh', 'off')                              -> 'xhigh'    expected 'xhigh'    OK   # 乱序输入
['off', 'low', 'medium', 'high', 'xhigh']     -> 'xhigh'    expected 'xhigh'    OK
{'off', 'high'}                               -> 'high'     expected 'high'     OK   # set 输入
['xhigh']                                     -> 'xhigh'    expected 'xhigh'    OK
['medium']                                    -> 'medium'   expected 'medium'   OK
('off', 'off')                                -> 'off'      expected 'off'      OK
```

- 端到端：`tests/test_spec026_capabilities.py:100-120` 断言 `supported == ('off','low','medium')` 时 `default_effort == 'medium'`（旧实现会给最低档 `off`），28 passed 中含此用例。

### 3. `stale` 返回旧 `supported_efforts` 与旧 `cached_at` —— 符合

- 证据：`ollama.py:124-131`，`replace(cached[1], source="stale")` 只改 `source`，`cached_at` 原样保留；`ollama.py:132` 的写缓存在 `return` 之后，`stale` 路径不可达。
- 实测（注入 `cached_at="2026-09-01T00:00:00+00:00"` 的过期条目 + 探测全失败）：

```
(b) stale -> stale ('off', 'low', 'medium') medium 2026-09-01T00:00:00+00:00
(b) refresh=True + fail -> stale 2026-09-01T00:00:00+00:00
```

- `cached_at` 未被刷新成当前时间。端到端另有 `tests/test_spec026_options_endpoint.py:122-137` 断言响应体 `cached_at == "2026-09-01T00:00:00+00:00"`。

### 4. 探测失败不污染/删除已有有效缓存（B16） —— 符合

- 证据：`ollama.py:124-131` 在 `unknown` 分支内**只 return、不写** `_capability_cache`；`cached is None` 时也不写。
- 实测（先写入有效条目，再让探测全失败，含 `refresh=True`）：

```
(b) cache entry identity preserved: True
(c) after refresh-fail, entry still old: True
(c) subsequent get -> stale
```

- 对象身份（`is`）与时间戳均未变；随后普通调用仍能命中旧条目。与 `tests/test_spec026_capabilities.py:170-183` 一致。

### 5. `reasoning_options` 四态输出符合 spec 表格；`unknown` 时 `[]` / `null` —— 符合

- 证据：`routes_conversations.py:216-222` `list(capabilities.supported_efforts)` → `()` 序列化为 `[]`；`default_effort` 直传 `None` → JSON `null`（`ollama.py:112` 保证 `unknown` 时 `default_effort=None`，`supported_efforts=()`）。
- 四态来源与 spec 表格一致：`ollama_probe`（`ollama.py:113`）/`cache`（`ollama.py:122`）/`stale`（`ollama.py:130`）/`unknown`（`ollama.py:112`、`ollama.py:131`）。
- 实测（端点级，`get_available_models` 抛 `httpx.ConnectError`）：

```
tests/test_spec026_options_endpoint.py::test_options_ollama_unreachable_returns_unknown_200
  -> 200, source=unknown, supported_efforts=[], default_effort=None, cached_at 非空
tests/test_spec026_options_endpoint.py::test_options_ollama_unreachable_with_expired_cache_returns_stale_200
  -> 200, source=stale, supported_efforts=['off','low'], default_effort='low', cached_at=旧值
```

- 无任何分支把 `unknown` 写成 `["off"]`。`unknown` 时 `cached_at` 由 `routes_conversations.py:219-221` 用 `utc_now().isoformat()` 补「本次尝试时间」，符合 task-03 表格；`utc_now()` 实测为 UTC 感知时间（`2026-09-11T21:26:17.196706+00:00`，`tzinfo=UTC`），符合本项目 UTC 约定。

### 6. `refresh=1` 真正绕过缓存（B4） —— 符合

- 证据：`routes_conversations.py:226` 新增 `refresh: int = 0`，`:236`/`:239` 透传 `refresh=bool(refresh)`；`ollama.py:121` 的 `cached and not refresh and ...` 保证 `refresh=True` 跳过缓存分支。
- 实测（`tests/test_spec026_options_endpoint.py:161-179`）：首次 `ollama_probe` → 第二次 `cache` → 第三次 `refresh=1` 为 `ollama_probe`，且断言真实探测发生 2 次（`probed == ["m", "m"]`）。

### 7. 发消息路径档位分流 —— 符合（与主会话裁决一致）

- 证据：`routes_conversations.py:191-213`。

| 场景 | 期望 | 代码 | 实测 |
|---|---|---|---|
| `unknown` + 非 off | 503 `MODEL_CAPABILITIES_UNAVAILABLE`（非 409） | `:213` | `(e) unknown + xhigh -> 503 MODEL_CAPABILITIES_UNAVAILABLE` |
| `unknown` + off | 放行 | `:209-212` | `tests/test_spec026_options_endpoint.py:224-237` 5 档参数化，仅 off 放行且 `provider_value is False` |
| `stale` 不在旧支持集 | 409 | `:207-208` | `(e) stale + xhigh -> 409 REASONING_EFFORT_UNSUPPORTED` |
| `stale` 在旧支持集 | 放行 | `:207-208`（`supported_efforts` 非空 → 409 分支跳过前已由 `resolve_reasoning_effort` 放行） | `tests/test_spec026_options_endpoint.py:259-270` |
| `known` 不在支持集 | 409 `REASONING_EFFORT_UNSUPPORTED` | `:207-208` | `tests/test_spec026_options_endpoint.py:276-285` |
| 非法档位 | 400 `INVALID_REASONING_EFFORT` | `:200-201` | `tests/test_spec026_options_endpoint.py:248-253` |

- 不建空会话、不调用模型：`_validate_model` 在 `:650`，`_resolve_request_effort` 在 `:659`/`:662`，`create_conversation_messages` 在 `:663`——能力校验全部发生在任何持久化写入之前；`run_chat` 只在 `_message_stream` 内被调用。实测 `tests/test_spec026_options_endpoint.py:206-221` 断言 503 后 `GET /api/conversations` 为空列表。
- 说明：task-03 计划 `task-03-backend-options-endpoint.md:40` 写的是「`unknown` 时任何非 off 请求**必须**返回 409」，与主会话裁决 B（503）不一致。按「主会话裁决优先」处理，**不作为缺陷**；建议后续把该计划文字同步为 503，避免第三份口径。

### 8. 红线：无静默换档 —— 符合

- 证据：`ollama.py:148-159` `resolve_reasoning_effort` 不做任何档位改写，`requested` 原样返回（`resolution.effort == requested`）；`routes_conversations.py:212` 的手工构造分支只在 `requested_effort == "off"` 时可达，返回的也是 `"off"`，不构成换档。
- `routes_conversations.py:329` 的 `selected_effort = reasoning_effort or getattr(conversation, "reasoning_effort", "medium")` 为**存量**代码，且 `resolution.effort` 恒为非空字符串（`ollama.py:149-152` 已保证取值属于 `REASONING_EFFORTS`），该兜底不可达。
- 全后端 grep 未发现任何 `resolution.effort = ...` 式的改写点；`create_conversation_messages`/`create_message_pair` 收到的都是 `resolution.effort`。

### 9. 统一错误体结构保持不变 —— 符合（并说明一处存量偏差）

- 证据：改动前后所有错误均以 `HTTPException(detail={"code", "message", "retryable"})` 抛出（`routes_conversations.py:200-213`），与 HEAD 版本逐字段一致（`git show HEAD:...` 对比：503 那条只是从 `RuntimeError` 分支移到 `unknown` 分支，字段未变）；`reasoning_options` 新增的 404 也复用同一形状（`:237-238`）。
- 存量偏差（非本次引入，`git diff` 未触碰）：线上实际 wire format 是 `{"detail": {...}}`，而 024/026 spec 文字写的是 `{"error": {...}}`。前端以 `data?.detail?.code ?? data?.code` 兼容（`frontend/app.js:702`、`:704`、`:2087`），故不构成缺陷；本 spec §明确不做 亦声明不改错误体结构。

### 10. 无第二套实现；`_validate_model` 的 503 `MODEL_UNAVAILABLE` 语义未被破坏 —— 符合

- 证据：`routes_conversations.py:182-188` 的 `_validate_model` 与 HEAD 逐字节一致（不在 `git diff` 内），发消息路径仍在 `:650` 调用它，Ollama 不可达时依旧 503 `MODEL_UNAVAILABLE`。
- 能力探测只有一套：全仓库 `api/chat` 出现点为 `ollama.py:98`（能力探针）、`ollama_direct.py:76`（聊天流式传输）、`chunkers.py:498`（切分用 LLM 调用），职责互不重叠；`api/tags` 仅 `ollama.py:164`。未发现重复实现。
- 注意：`reasoning_options` 现在**不调用** `_validate_model`，而是内联 `get_available_models()` 并自行给 404（`routes_conversations.py:231-238`）。这是主会话裁决 A 的必然结果（需在 Ollama 不可达时返回 200 而非 503），非缺陷；复用性问题见 P2-3。

## 三、问题清单

### P0（阻塞）：0 条

### P1（须修）：0 条

### P2（建议修，不阻塞）

**P2-1｜`unknown`/`stale` 错误路径重复探测一轮（本次引入的性能回退）**

- 位置：`backend/app/api/routes_conversations.py:206`（`capabilities = get_reasoning_capabilities(model)`）
- 为什么是问题：`resolve_reasoning_effort`（`ollama.py:147`）内部已经调用过一次 `get_reasoning_capabilities`；探测失败时**不会写入缓存**（`ollama.py:124-131`），因此 `:206` 的第二次调用必然再跑一整轮 5 档串行探测。实测探测轮数：
  ```
  (e) unknown + xhigh -> 503 MODEL_CAPABILITIES_UNAVAILABLE | probe rounds = 2
  (e) stale   + xhigh -> 409 REASONING_EFFORT_UNSUPPORTED  | probe rounds = 2
  ```
  对照 HEAD：`git show HEAD:...` 的 `RuntimeError` 分支直接 raise 503，**不做**第二次能力读取，故 HEAD 为 1 轮。每轮最坏 5 × `timeout=5` = 25s（`ollama.py:98`），黑洞路由下用户可感知延迟由 ~25s 变为 ~50s，恰好落在本 spec 要修的「首屏响应」痛点上（对端「连接被拒」时影响可忽略）。
- 附带一致性风险：第二次读取发生在第一次失败之后，若期间有并发成功探测写入缓存，同一次请求可能由 503 翻转为 409；两者都「可解释」，但不该在同一次请求内取决于时序。
- 建议改法（任选其一，均不违反 spec §明确不做「不改探测性能」）：
  1. 让 `resolve_reasoning_effort` 抛出携带能力对象的自定义异常（如 `UnsupportedEffortError(capabilities=...)`），`_resolve_request_effort` 直接复用，不再二次调用；或
  2. 把 `_resolve_request_effort` 改为先调一次 `get_reasoning_capabilities(model)`，据其结果自行判定 400/409/503/放行，只让 `resolve_reasoning_effort` 负责 provider 值映射。

**P2-2｜死代码 `_capabilities_for_model()` 仍会伪造 `('off',)`，是 B1 的潜在复发点**

- 位置：`backend/app/platform/ollama.py:67-68`
- 为什么是问题：它返回 `supported_efforts=("off",)`、`default_effort="off"`、`source="unavailable"`，正是 spec 026 B1 明令禁止的「伪造支持集」。当前全仓库无调用点（已 grep 确认），所以**不是活跃缺陷**；但 spec 026 §数据模型与 task-02 步骤 5 都要求「保持不变」，等于把一个与 B1 冲突的构造器留在能力模块里，后续任何一次「兜底复用」都会静默复活缺陷 C。
- 建议改法：在本 spec 范围内**最小改动**——给该函数加显式注释/断言说明「不得用于对外能力输出，仅兼容 `unavailable` 语义」，或直接把 `supported_efforts` 改为 `()`+`default_effort=None` 并单独保留 `source="unavailable"`；若要按 spec 原样保留，则应在 task-02 产出物中登记该风险，避免后续误用。

**P2-3｜复用与可读性（3 处合并）**

- 位置与理由：
  1. `routes_conversations.py:212`：`ReasoningResolution(str(model), "off", False, capabilities, {"think": False})` 手工复制了 `ollama.py:157-158` 的 provider 映射（`off → False` + `{"think": False}`）。一旦 provider 映射调整，两处会漂移。
  2. `routes_conversations.py:216` `_reasoning_options_payload(capabilities)` 缺少类型注解（应为 `ReasoningCapabilities`），且承担了「补 `unknown` 的 `cached_at`」这一业务语义——建议注解 + 一句 why 注释。
  3. `ollama.py:104`：`if effort == "off" and not thinking or effort != "off" and isinstance(thinking, str) and thinking:` 混用 `and`/`or` 未加括号。语义与改动前的 `if/elif` 等价（`and` 优先级高于 `or`），ruff 默认规则集不报，但可读性明显下降，建议补括号。
- 建议改法：把 provider 映射抽成 `_provider_value(effort)` 供两处复用；补类型注解与括号。均为小改动，不涉及行为。

## 四、未验证项（明确声明，不编造结论）

1. **真实 Ollama smoke 未执行**。本机未安装 Ollama（`which ollama` 无输出），`OLLAMA_BASE_URL` 指向 LAN 主机 `192.168.31.180:11434`：`/api/tags` 200，但 `/api/chat` 对测试模型名返回 404（`{"error":"model 'model' not found"}`）。因此 spec §验收方式 要求的「真实 xhigh/low/off 能力探测」与真实 409 路径**未验证**，本次所有能力结论均基于「探测全失败/可控 mock」的确定性路径。
2. **HEAD 复跑对照未执行**。评审约束禁止 `git stash`/`reset`，故未回退代码复跑 `tests/test_conversations_api.py`。P2-1 的「HEAD 为 1 轮」结论来自 `git show HEAD:backend/app/api/routes_conversations.py` 的源码比对，而非运行对照。
3. **`test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse` 失败的最终机制未完全定位**（已证明与本次改动无关，见下节）。未逐线程抓取其后台 worker 的阻塞栈。

## 五、回归命令与真实输出

```
$ .venv/bin/python -m pytest tests/test_spec026_capabilities.py tests/test_spec026_options_endpoint.py -q --basetemp=.pytest-tmp-review
............................                                             [100%]
28 passed in 0.98s

$ .venv/bin/python -m pytest tests/test_conversations_api.py tests/test_spec024_backend.py -q --basetemp=.pytest-tmp-review2
FAILED tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse
1 failed, 29 passed in 2.54s

$ .venv/bin/python -m ruff check backend/app/platform/ollama.py
All checks passed!          # exit=0

$ .venv/bin/python -m ruff check backend/app/api/routes_conversations.py
Found 33 errors.            # HEAD 版本（git show HEAD:... | ruff check --stdin-filename ... -）为 Found 34 errors.
                            # 规则码逐项比对：旧 19×E701 / 5×SIM105 / 5×F841 / 1×I001 / 3×F401 / 1×E702
                            #                新 19×E701 / 5×SIM105 / 5×F841 / 0×I001 / 3×F401 / 1×E702
                            # 本次仅消除了存量 I001（import 重排），**未引入任何新规则码**。
```

### 关于那 1 个失败用例：非本次改动引入（附证据）

- `tests/test_conversations_api.py` **未被本次改动修改**（`git status` 无该文件）。
- 该文件有 autouse fixture（`tests/test_conversations_api.py:16-20`）把 `probe_reasoning_capabilities` 打成 `('off','low','medium','high','xhigh')` 且 `xhigh` 受支持，因此 `_resolve_request_effort` 走的是与 HEAD **完全相同**的 `return resolve_reasoning_effort(...)` 出口；本次新增代码只存在于 `except ValueError` 分支（`routes_conversations.py:198-213`），该分支在此用例中**不可达**。
- 失败断言是「后台记忆分析任务须在 2s 内进入终态」（`tests/test_conversations_api.py:362`），其耗时由 `classify_memory_intent` → 真实 LLM（`conversation_service.py:711`，模型 `qwen3.5:9b`）+ 记忆写入决定，本次改动未触碰这条链路。
- 独立 harness 复刻（同样注入全档 caps、同样只等 evolution checkpoint 再读 analysis job）3/3 复现同一失败：

```
trial 0: checkpoint=completed analysis=running -> test_assert FAIL
trial 1: checkpoint=completed analysis=running -> test_assert FAIL
trial 2: checkpoint=completed analysis=running -> test_assert FAIL
```

  即该用例存在自身竞态（checkpoint 先完成、analysis job 后完成），对 LLM 环境快慢敏感；`classify_memory_intent` 在本环境单次实测 0.98s（返回 `CLASSIFIER_FAILED`），环境退化时即超 2s 窗口。
- 因此判定为**存量/环境相关失败**，不计入本次改动的回归。

## 六、通过后沉淀的强制约束清单

1. 后续任何 spec 若要复用能力对象，**必须**继续遵守：`unknown` ⇒ `supported_efforts=()`、`default_effort=None`，禁止回退 `('off',)`；`_capabilities_for_model()` 在修复 P2-2 之前不得被任何对外能力输出路径调用。
2. 单次请求内**最多探测一轮**：新增任何「先 `resolve_reasoning_effort` 再读 `get_reasoning_capabilities`」的代码前，必须先修掉 P2-1 的重复探测模式。
3. 错误码口径以主会话裁决为准：`GET /chat/reasoning-options` **永不返回 503**；发消息路径 `unknown` + 非 `off` ⇒ 503 `MODEL_CAPABILITIES_UNAVAILABLE`，`stale`/`known` 不支持 ⇒ 409 `REASONING_EFFORT_UNSUPPORTED`。task-03 文档中「unknown ⇒ 409」的表述需同步修正，避免第三份口径。
4. 能力相关错误体统一 `{"code","message","retryable"}` 三字段；新增分支不得省略 `retryable`。
5. `stale` 必须透出**旧** `cached_at`；探测失败路径**不得**写缓存（B16），新增代码需补一条对应的缓存不变性断言。
6. 时间字段一律 UTC（`utc_now()`），不得引入本地时间。
7. 评审范围内禁止在 `backend/**` 出现第二套能力探测/档位映射实现（复用 `ollama.py`）。
