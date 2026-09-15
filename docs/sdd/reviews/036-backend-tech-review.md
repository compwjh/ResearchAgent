# 036 后端技术评审 — `GET /api/tools/{name}/code`

| 项 | 内容 |
|---|---|
| **评审者** | backend-reviewer 子代理（本会话，独立于实现者视角复核） |
| **角色** | 后端评审（Backend Reviewer）—— 只评 `backend/**` 与后端测试 |
| **模型** | 自身（当前执行任务的 Agent，不写死模型代号）；spec「执行配置」登记为 `qwen3.8:27b-mlx` |
| **分派方式** | `Task(backend-reviewer)` |

**被评审对象（spec-036 task-02，已实现）**

- `backend/app/api/routes_tools.py`（新增路由 `get_tool_code` + 固定文案常量）
- `backend/app/skills/tool_service.py`（新增 `_REPO_ROOT` / `_SourceUnavailable` / `_import_entry_object` / `resolve_tool_source` / `ToolRegistryService.get_tool_entry`）
- `tests/test_tool_registry.py`（新增 `ToolCodeApiTests`，17 个用例）
- 约束依据：`docs/sdd/specs/036-tool-source-code-viewer.md`、`docs/sdd/reviews/036-requirement-review.md`（M-01～M-08）、`docs/sdd/plans/036/task-02-backend-tool-code-api.md`

**评审方式**：不采信文档与回传摘要，逐条回源码复核 + 自写 3 组探针 + 对运行中服务做只读 curl 核对。

---

## 0. 复核证据（本次实测原始输出摘要）

| 复核项 | 命令 | 结果 |
|---|---|---|
| 定向 pytest | `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_tool_registry.py -q --basetemp=/tmp/br036_run1` | **38 passed, 18 subtests passed, 1 warning in 4.50s** |
| 新增用例数 | `pytest ... --collect-only \| grep -c ToolCodeApiTests` | **17**（与 task-02 声明的 17 一致） |
| 改动文件 lint | `env -u PYTHONPATH .venv/bin/python -m ruff check backend/app/api/routes_tools.py backend/app/skills/tool_service.py` | **All checks passed!**（exit=0，零告警） |
| M-01 探针 | 自写 `/tmp/br036_probe.py`（`resolve_tool_source` 逐 entry 取 `file:lineno` 并回读该行） | 5/5：`94 def search(` / `398 def import_candidate(` / `994 def fetch_paper_detail(` / `139 def hybrid_search(` / **`953 @router.post("/kb/ask")`** |
| M-03 探针 | `/tmp/br036_probe.py` + `/tmp/br036_probe2.py`（模块/包/类/实例/属性链终点为模块/stdlib） | 上述 11 类终点**全部返回 None**；对照项 `ToolEntry.to_dict` 只返回 2 行函数体、`resolve_tool_source` 返回 35 行（**均非整文件/整类体**） |
| 异常收敛探针 | `/tmp/br036_probe3.py`（`TestClient(raise_server_exceptions=False)` + patch `inspect.getsourcelines` / `getsourcefile` 抛异常） | 两种 patch 均 **HTTP 404**（非 500），body 固定文案，未出现异常里的 `/Users/secret` |
| 无缓存探针 | 同上 E 段（统计两次请求中 `inspect.getsourcelines` 调用次数） | **2 次请求 → 2 次调用**（无缓存） |
| 运行时核对 | `curl http://127.0.0.1:8000/api/tools/{5 个 name}/code`（服务未重启） | 5/5 **HTTP=200**，字段集 `{name,entry,file,lineno,language,code}` |
| 路径安全（运行时） | `curl` 各响应体 `grep -c "/Users\|/private\|\.venv"` | 6/6 **0 命中** |
| 只读（运行时） | 调用前后 `stat -f "%m %z" data/kb/skill-state.json` | `1789205008 418` → `1789205008 418`，**未写状态文件** |
| 重复实现检查 | `grep -rn "isfunction\|ismethod\|getsource" backend/app/`；`grep -rn "resolve_tool_source\|_import_entry_object"` | 除 `tool_service.py` 外**零命中**；调用点唯一（`routes_tools.py:90` 调 `resolve_tool_source`；`tool_service.py:84` 调 `_import_entry_object`） |

---

## 1. 强制约束逐条判定

### M-01 `lineno` 语义（源码块首行 / 装饰器行）—— **PASS**

- 依据（代码）：`backend/app/skills/tool_service.py:90` `lines, lineno = inspect.getsourcelines(obj)`，直接把 `getsourcelines` 的第 2 个返回值作为 `lineno` 返回（`:94`），**没有任何 `+1`/`-1` 修正**。
- 依据（实测，探针1）：`kb_ask` → `lineno=953`，回读 `backend/app/api/routes_kb.py:953` = `@router.post("/kb/ask")`，`def kb_ask` 在 954；`code` 首行即装饰器行。其余 4 个 Tool 的 `lineno` 落在 `def` 行。
- 依据（运行时）：`curl /api/tools/kb_ask/code` → `lineno=953`，`code` 首行 `@router.post("/kb/ask")`。
- 依据（测试）：`tests/test_tool_registry.py` 的 `_assert_m01_lineno` 用 `ast` 解析 `code` 并断言「首行为装饰器时 `decorator_list[0].lineno == 1` 且 `def` 行在 `lineno` 之后」，`test_decorated_route_function_returns_decorator_line` 另断言该行**不含** `def kb_ask` —— **未**使用「必须含 `def`」这一被禁止的判据。
- 说明：spec/plan/需求评审三处写死「`routes_kb.py:952`」，实测当前工作区为 **953**。`git show HEAD:backend/app/api/routes_kb.py | sed -n '952p'` = `@router.post("/kb/ask")`，说明漂移来自 spec-035 在途改动在 `routes_kb.py` 上方新增 1 行 import（**非本任务改动**）。实现与测试均为动态取值，**不受影响**；台账数字见问题清单 M-036-01。

### M-03 解析终点类型约束（最关键）—— **PASS**

- 依据（代码）：`tool_service.py:85` `if not attrs or not (inspect.isfunction(obj) or inspect.ismethod(obj)): raise _SourceUnavailable(...)`；该判断位于 `inspect.getsourcefile`（`:87`）/ `inspect.getsourcelines`（`:90`）/ `inspect.getsource` 之前，**任何整文件读取都发生在类型校验之后**。
- **算法层面的准确结论（不附和）**：「从长到短尝试 import」这个循环本身**不提供任何终点保护** —— 当 `entry` 是纯模块路径时，循环返回的 `obj` 恰恰就是**最长可导入模块**，`attrs=[]`。真正的封堵点是紧随其后的 `not attrs` + `isfunction/ismethod` 类型闸门。该分工在 `_import_entry_object` 的 docstring（`:46-48`）中已显式声明「调用方必须做类型校验（M-03）」，且**调用点唯一**（`tool_service.py:84`），闸门不会被绕过。故结论是：保护成立，但依赖调用方；若未来新增第二个调用点而忘记加闸门，会立即退化为整文件泄漏（见问题清单 L-036-01 的加固建议）。
- 依据（实测，探针1/2，11 类终点全覆盖）：

| 构造的 entry | `attrs` | 终点类型 | 结果 |
|---|---|---|---|
| `backend.app.knowledge_base.infrastructure.retrieve`（模块，无属性链） | `[]` | module | **None（不可用）** |
| `backend.app.api.routes_kb`（模块） | `[]` | module | **None** |
| `backend.app.skills`（包） | `[]` | module | **None** |
| `os.path` / `collections.abc`（stdlib 模块） | `[]` | module | **None** |
| `backend.app.skills.models.ToolEntry`（类） | `['ToolEntry']` | class | **None** |
| `backend.app.skills.tool_service.ToolRegistryService`（类） | `[...]` | class | **None** |
| `backend.app.skills.tool_service.inspect`（**属性链终点 = 模块**） | `['inspect']` | module | **None** |
| `backend.app.skills.tool_service.logging`（同上） | `['logging']` | module | **None** |
| `backend.app.skills.tool_service.logger`（实例） | `['logger']` | Logger 实例 | **None** |
| `backend.app.skills.tool_service.logger.warning`（绑定方法，repo 外） | `['logger','warning']` | method | **None**（越界守卫拦下） |
| `json.dumps`（`isfunction=True` 但仓库外） | `['dumps']` | function | **None**（`relative_to` 拦下） |
| 对照：`ToolEntry.to_dict` | `['ToolEntry','to_dict']` | function | OK，`models.py:62`，**2 行**（非整类体） |
| 对照：`resolve_tool_source` | `[...]` | function | OK，`tool_service.py:66`，**35 行**（非整文件） |

- 依据（测试）：`test_module_entry_is_unavailable_and_not_whole_file`（并断言 `"import " not in resp.text` 且响应体 < 1000 字节）、`test_class_entry_is_unavailable_and_not_class_body`（并断言 `"def to_dict" not in resp.text`）——负例断言方向正确。

### M-04 错误文案固定（无 `str(exc)` / 绝对路径）—— **PASS**

- 依据（代码）：`routes_tools.py:31` `_TOOL_CODE_UNAVAILABLE_MESSAGE = "该 Tool 的入口源码不可用"`；`routes_tools.py:92-94` 把该常量原样交给 `_document_error`，**未拼接任何变量**。`TOOL_NOT_FOUND` 沿用既有固定文案 `"Tool 不存在"`（`:89`）。
- 依据（`_document_error`）：`backend/app/api/routes_kb.py:194-198` 只输出 `error_code / message / retryable / request_id`，`request_id` 来自 `X-Request-ID` 头或随机 uuid，**不含路径**。
- 依据（实测，探针3 A/B）：patch `inspect.getsourcelines` / `getsourcefile` 抛出**含 `/Users/secret` 的异常消息**后，响应体仍为固定文案，**未出现该路径片段**。
- 依据（运行时）：6 个响应体（含 5 个 200 与 1 个 404）`grep -c "/Users\|/private\|\.venv"` 全为 **0**。
- 依据（日志面）：`tool_service.py:99` `logger.warning("tool source unavailable for entry %r", entry, exc_info=True)` —— 日志只含注册表 `entry`（非请求方输入）与 stack，符合 M-04「异常详情只进服务端日志」。仅 `entry` 会被记录，请求参数不入日志。

### M-06 名称精确匹配 / 不接受请求方点分路径 —— **PASS**

- 依据（代码）：`tool_service.py:152-155` `for template in self._registry: if template.name == name: return template` —— **`==` 精确相等**，无前缀/模糊/大小写归一化，无文件系统回退。
- 依据（代码）：`routes_tools.py:87` `registered = get_tool_registry().get_tool_entry(name)`，`routes_tools.py:90` `resolve_tool_source(registered.entry)` —— `entry` **只来自注册表对象**，请求对象（`name` / `Request`）不参与任何路径解析。
- 依据（运行时，逐条 curl）：
  - `backend.app.api.routes_kb`、`backend.app.api.routes_kb.kb_ask`、`KB_SEARCH`、`kb`、`kb_search%20`、`.`、`%00kb_search` → **404 `TOOL_NOT_FOUND`**（无任何模糊兜底）；
  - `..%2F..%2Fetc%2Fpasswd`、`%2e%2e%2fbackend%2fapp`、`kb_search%2Fcode`、`..` → **404**（路径含 `/` 时未命中本路由，返回框架 `{"detail":"Not Found"}`，**未泄漏任何路径或文件内容**）；
  - `?entry=backend.app.api.routes_kb&name=kb_ask` 与 `X-Entry: ...` 头 → 响应与基线**逐字一致**（`file`/`lineno`/`code` 均未改变）。
- 依据（测试）：`test_dotted_path_as_name_is_rejected`（5 种变体）、`test_request_cannot_override_entry`（query + header 全字段比对）已固化。

### M-07 只读 / 回归冻结 / 禁用可查看 / 不加缓存 —— **PASS**

- **只读**：新增代码路径中无 `open(...,"w")`、无状态写入、无 eval/exec。`get_tool_entry`（`tool_service.py:144-155`）**不读状态文件**（对比 `get_tool` 走 `_enabled_for`）。运行时 `data/kb/skill-state.json` 的 mtime+size 调用前后完全一致（`1789205008 418`）；单测 `test_code_endpoint_does_not_touch_state_file` 断言状态文件**不存在**（端点未创建它）。
- **既有三接口结构逐字不变**：`ToolEntry.to_dict()` 未被改动（`models.py:64` 仍只返回 `name/description/enabled`；本次 `git status` 中 `models.py` **无改动**）；`routes_tools.py` 的 `list_tools` / `get_tool` / `update_tool` 三个函数体在 diff 中**零改动**。运行时 `GET /api/tools` 的 tool keys = `description/enabled/name`（5 个）、`GET /api/tools/{name}` keys 同上；单测 `test_existing_endpoints_response_shape_unchanged` 断言三个接口 keys 恒等于 `{name,description,enabled}` 且详情体**不含** `entry`。
- **禁用 Tool 仍可查看**：`get_tool_entry` 不掺入 `enabled`，路由不做状态过滤；单测 `test_disabled_tool_still_returns_code` 先由 `GET /api/tools/kb_search` 确认 `enabled=false`，再断言 `/code` 返回 200 + 非空 `code`。（本项**未**在运行中服务上做 PATCH 复核，以免向线上实例写入状态文件；以单测 + 代码路径为准。）
- **不加缓存**：`resolve_tool_source` 无 `lru_cache` / 无模块级 memo；探针实测两次请求触发 `inspect.getsourcelines` **2 次**。进程级缓存的是注册表对象（`routes_tools.py:36-44`，**既有实现**），不缓存源码，行号不会漂移。

---

## 2. 两项专项结论

### 2.1 异常收敛（无 500）—— **成立**

- `resolve_tool_source` 的 `try`（`tool_service.py:83`）覆盖了**全部**解析动作：`_import_entry_object`（含 `entry.split`、`importlib.import_module`、`getattr` 链）、M-03 类型校验、`inspect.getsourcefile`、`inspect.getsourcelines`、`Path(...).resolve().relative_to(_REPO_ROOT)`、`"".join(lines)`；`except Exception`（`:98`）统一 `return None` → 路由转 `TOOL_CODE_UNAVAILABLE` 404。
- 路由侧其余语句只有 `get_tool_registry()`（懒加载，与既有三接口同一路径）、`get_tool_entry`（纯遍历，不会抛）、字典读取（键恒在）。
- 实测（探针3）：A) `getsourcelines` 抛 `OSError` → 404；B) `getsourcefile` 抛 `TypeError` → 404；C) `entry` 为 `None` / `123` / `["a","b"]` → 404；D) 模块/类/包/stdlib entry 走完整 HTTP 栈 → 404。**未观察到任何 500。**
- 残留风险（**既有、非本任务引入**）：`get_tool_registry()` 内部 `build_default_tool_registry()` 若抛异常，本路由与既有三接口**同样**会 500。本次未新增该面。

### 2.2 路径安全（仓库根推导 / 越界 / 泄漏）—— **成立**

- **未硬编码 `/Users/...`**：`tool_service.py:33` `_REPO_ROOT = BASE_DIR`，`BASE_DIR` 定义于 `backend/app/platform/config.py:10` = `Path(__file__).resolve().parents[3]`（已 `resolve()`，实测 = `/Users/wjh/work/ResearchAgent-2/ResearchAgent`）。仓库根随部署位置自适应。
- **越界拒绝**：`tool_service.py:91` `Path(source_file).resolve().relative_to(_REPO_ROOT)` —— `resolve()` 会跟随软链（软链指向仓库外 → 越界 → `ValueError` → 404）；`relative_to` 是**路径分量级**比较（`/repo` 与 `/repo2` 不会误判为包含关系），优于 `str.startswith`。
- **不泄漏路径**：越界时 `source_file` 只进入 `logger.warning`，不进入响应体；探针 patch `_REPO_ROOT` 的既有单测 `test_out_of_repo_source_is_unavailable_without_leaking_path` 断言响应体不含 tmp 路径 / `/Users` / `retrieve.py`。运行时 6/6 响应体绝对路径命中 0。
- **未新增暴露面（M-05）**：`grep "HOST\|0\.0\.0\.0\|auth\|token\|Authorization"` 在两个改动文件中**零命中**；`deploy/**` 本次无改动；本任务未触碰鉴权与绑定策略。

---

## 3. 问题清单

> 无 CRITICAL / HIGH。以下均为不影响本 spec 交付结论的意见项。

| 级别 | 位置 | 问题 | 建议 |
|---|---|---|---|
| **MEDIUM** | `docs/sdd/specs/036-tool-source-code-viewer.md:33`（表）、`:55`、`docs/sdd/plans/036/task-02-backend-tool-code-api.md:64`、`docs/sdd/reviews/036-requirement-review.md:56,102,140` | 三处文档把 `kb_ask` 的 `lineno` 写死为 **952**，实测当前工作区为 **953**（`routes_kb.py` 被 spec-035 在途改动上方 +1 行）。实现与测试均为动态取值不受影响，但**验收总控若按 952 硬核对会产生假阴性** | 在 spec 台账把「952」改为「动态取值：该行必须是装饰器行，行号随文件漂移」；验收脚本一律用 `GET` 返回的 `lineno` 回读文件，不硬编码数字 |
| **LOW** | `backend/app/skills/tool_service.py:66` | `resolve_tool_source(entry)` 是**模块级公开函数**，入参为任意点分路径，内部执行 `importlib.import_module`。当前唯一调用点传的是注册表 `entry`（M-06 成立），**今天不可被请求方触达、无实际漏洞**；但该签名在未来「查看任意函数」类需求下极易被直接接上请求参数，届时即成为任意模块导入（导入期副作用执行）+ 仓库内任意函数源码读取的原语 | ① 函数名/注释显式标注「仅供注册表 entry 使用，禁止接请求输入」；② 或在函数内加一道 `entry` 必须命中注册表的白名单校验，使该原语在结构上无法被误用 |
| **LOW** | `backend/app/skills/tool_service.py:144-155` | `get_tool_entry` 返回的是 `self._registry` 内的**共享可变对象本身**（`get_tool` / `set_enabled` 都返回新构造的副本）。当前路由只读，无实际影响；一旦有调用方原地修改该对象，会污染进程级注册表 | 返回 `dataclasses.replace(template)` 副本，或在返回类型上加 `Final`/只读约定并保留 docstring 警告（现已警告，可接受） |
| **LOW** | `backend/app/skills/tool_service.py:54,60` | `except Exception: continue` 会**静默吞掉**模块导入期的真实错误（如被依赖模块的 bug）并降级到更短前缀；另有语义死角：若 `a.b.c` 同时是子模块与 `a.b` 的同名属性，循环按「最长可导入」优先命中**子模块** → `attrs=[]` → 404（false negative，fail-closed 不泄漏） | 保持 fail-closed 现状可接受；建议把「降级」路径也纳入 `logger.debug`，便于排障；若未来 registry 出现「属性与子模块同名」的 entry，需显式约定优先级 |
| **LOW** | `backend/app/skills/tool_service.py:99` | 每次失败都 `logger.warning(..., exc_info=True)` 打全栈。本机单用户 + 无鉴权前提下可被反复触发刷日志（spec 明确不做限流，故不构成缺陷） | 可选：同一 `entry` 的失败日志做去重/降级为 `debug`；不阻塞 |
| **INFO** | `routes_tools.py:95-102` | 响应含 `language: "python"`，而 spec「明确不做」已排除语法高亮、前端不消费 → YAGNI（需求评审 Q-06 已记录 P2） | 实现与 spec:51 一致，**不判问题**；若后续仍无消费方，建议在下一轮 spec 收敛删除 |
| **INFO** | `backend/app/api/routes_tools.py:74` | 路径含 `/` 的未命中请求（如 `..%2F..%2Fetc%2Fpasswd`）由框架返回 `{"detail":"Not Found"}`，与项目统一的 `{error_code,message,retryable,request_id}` 结构不一致 | 既有全局行为（所有路由皆然），非本次引入；如要统一应作为独立任务处理 |

---

## 4. Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 1 | info |
| LOW | 4 | note |
| INFO | 2 | note |

**强制约束判定汇总**

| 约束 | 判定 | 关键依据（文件:行） |
|---|---|---|
| M-01 `lineno` = 源码块首行（装饰器行） | **PASS** | `tool_service.py:90,94`；实测 `kb_ask` → `routes_kb.py:953` = `@router.post("/kb/ask")`（无 `+1`） |
| M-03 终点必须 `isfunction/ismethod` 且属性链非空 | **PASS** | `tool_service.py:85`（闸门在 `:87/:90` 之前）；11 类模块/类/实例终点探针全 None；调用点唯一 `tool_service.py:84` |
| M-04 错误 `message` 固定文案 | **PASS** | `routes_tools.py:31,92-94`；异常含 `/Users/secret` 时响应体仍无路径 |
| M-06 `{name}` 精确相等、`entry` 只取自注册表 | **PASS** | `tool_service.py:152-155`；`routes_tools.py:87,90`；query/header 注入不改变结果 |
| M-07 只读 / 三接口结构不变 / 禁用可查看 / 不加缓存 | **PASS** | `tool_service.py:144-155`；`models.py:64` 未改；运行时状态文件 mtime 不变；2 请求 = 2 次 `getsourcelines` |
| 异常全部收敛为 404（无 500） | **成立** | `tool_service.py:83-100`；探针 A/B/C/D 全 404 |
| 路径安全（不硬编码 `/Users`、越界拒绝、不泄漏） | **成立** | `config.py:10` + `tool_service.py:33,91`；运行时 6/6 响应体 0 命中绝对路径 |

**Verdict：通过（附意见）** —— 无 CRITICAL / HIGH；M-01 / M-03 / M-04 / M-06 / M-07 五条强制约束**逐条 PASS**，异常收敛与路径安全两项专项结论**成立**。定向 pytest 38 passed、ruff 两文件零告警、运行时 5/5 Tool 返回 200 且响应体无绝对路径。

放行时请把以下 4 条固化为**强制约束**带入后续环节：

1. **验收不得硬编码行号**：`lineno` 一律以接口返回值为准并回读该行校验「装饰器行 / `def` 行」，禁止写死 952（已漂移为 953）。
2. **`resolve_tool_source` 仅限注册表 `entry`**：禁止任何请求参数（path/query/body/header）接入该函数的入参；新增调用点必须先复核 M-03 闸门仍在。
3. **M-03 闸门与类型校验必须同点**：`not attrs` + `isfunction/ismethod` 必须在 `inspect.getsource*` 之前；新增解析入口须同步复制该闸门。
4. **`to_dict()` 与既有三接口响应结构保持冻结**：后续任何 spec 若需在列表/详情暴露 `entry`，必须新开 spec 评审，不得顺手改。

---

## 5. 评审边界声明

- 本次评审**只产出本文件**，**未修改任何代码文件**（未改 `backend/**`、`frontend/**`、`tests/**`），也未修改被评审的 spec / plan 文件。
- 探针脚本写在 `/tmp/br036_probe.py`、`/tmp/br036_probe2.py`、`/tmp/br036_probe3.py`，**未落仓库**；pytest `--basetemp` 使用 `/tmp/br036_*` 新目录。
- **未使用** `git checkout` / `git restore` / `git stash` / `git reset` / `git clean`；未做 `git commit` / `git push`。
- **未重启**运行中服务（`:8000`）；运行时核对全部为只读 GET，**未**对线上实例执行 PATCH（避免写状态文件）。
- 工作区中其它角色/spec 的在途改动（`routes_kb.py`、`frontend/**`、`.env.example`、`backend/app/platform/*` 等）与本评审无关，未触碰；`ruff check backend` 的既有告警位于 `memory/repository.py`、`routes_conversations.py`、`routes_chat.py`、`platform/ollama_direct.py`、`chat/application/chat_graph.py`，**属其他模块，未纳入本次结论**。
