# Task 02 — 后端：新增 `GET /api/tools/{name}/code`

> 关联：[spec-036](../../specs/036-tool-source-code-viewer.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`待执行`

## 1. 状态与一句话目标

**待执行。** 新增一个只读接口，按 Tool 注册名返回其在后端真实执行的**入口函数源码**与
**仓库相对 `文件:行号`**，供前端「代码」弹窗展示。

## 2. 背景与前置条件

- Tool 注册表唯一事实源是代码：`ToolEntry.entry` 已保存点分入口路径，
  例如 `backend.app.knowledge_base.infrastructure.retrieve.hybrid_search`（模块函数）
  与 `...PaperDiscoverySearchService.search`（类方法）。
- `entry` 目前**刻意不进 API 响应**（`ToolEntry.to_dict()` 只返回 `name/description/enabled`），
  本任务**不得改变**该结构，只在**新接口**里返回。
- 架构师已实测：5 个注册 entry 全部可用 `inspect` 解析（含被装饰的 `kb_ask`，`inspect` 自动 unwrap）。

## 3. 数据、配置与接口

新增响应体（仅本接口）：

| 字段 | 类型 | 约束 |
|---|---|---|
| `name` | str | 必填；Tool 注册名 |
| `entry` | str | 必填；`模块.函数` 点分路径，取自注册表 |
| `file` | str | 必填；**仓库相对路径**（如 `backend/app/...py`），不得为绝对路径 |
| `lineno` | int | 必填；入口源码起始行（1-based） |
| `language` | str | 固定 `"python"` |
| `code` | str | 必填；入口函数/方法源码原文 |

错误码：

| 状态码 | `error_code` | 触发条件 | `retryable` |
|---|---|---|---|
| 404 | `TOOL_NOT_FOUND` | `name` 不在注册表 | false |
| 404 | `TOOL_CODE_UNAVAILABLE` | `entry` 为空 / 无法解析 / 源码不可读 / 解析到的文件不在仓库内 | false |

## 4. 实施步骤与文件边界

**允许改动**：`backend/app/api/routes_tools.py`、`backend/app/skills/tool_service.py`、
`backend/app/skills/models.py`（仅在必须时）、新增/修改测试文件。
**禁止改动**：`ToolEntry.to_dict()` 的输出、`/api/tools` 与 `/api/tools/{name}` 的响应结构、
启停逻辑与状态文件、`frontend/**`。

1. **`ToolRegistryService` 暴露 entry**：在 `backend/app/skills/tool_service.py` 增加
   `get_tool_entry(name) -> ToolEntry | None`（复用既有 `_registry` 遍历，`_to_tool` 语义不变），
   让路由层能拿到注册表里那个 `entry`。**不要**把 `entry` 塞进既有 `get_tool()` 的返回。
2. **源码解析**：新增解析函数（建议放在 `backend/app/skills/tool_service.py` 或同目录新模块），
   输入为注册项自带的 `entry` 字符串，**不接受外部传入的任意点分路径**。要点：

   > **M-03（强制，P1）**：解析终点**必须**是函数或方法 —— 属性链**非空**且结果满足
   > `inspect.isfunction(obj) or inspect.ismethod(obj)`；否则返回 `TOOL_CODE_UNAVAILABLE`。
   > **禁止**以模块对象（`inspect.ismodule`）或类对象作为终点，否则 `inspect.getsource`
   > 会返回整个文件/整个类体（实测：模块 entry 会返回整文件 182 行）。
   > 「从长到短尝试 import」的算法必须保证**最长可导入模块不会成为终点**。

   - 从长到短尝试 `importlib.import_module(".".join(parts[:i]))` 拆出「模块路径 + 属性链」，
     再按属性链 `getattr` 取到目标对象（类方法形态 `X.Y` 同样成立）。
   - 取到对象后先做 M-03 的类型校验，再 `inspect.getsource(obj)` 取源码（会自动 unwrap 装饰器）；
     `inspect.getsourcefile(obj)` + `inspect.getsourcelines(obj)[1]` 取文件与起始行。
   - **`lineno` 语义（M-01）**：`inspect.getsourcelines(obj)[1]` 是**源码块首行**；
     对带装饰器的函数它是**装饰器行**（实证 `routes_kb.py:953` = `@router.post("/kb/ask")`（装饰器行），
     `def kb_ask` 在 954）。这是 `inspect` 的既定行为，**不要**为了对齐 `def` 而行号加一。
   - **路径安全**：把 `getsourcefile` 结果解析成绝对路径后，必须确认它位于**仓库根目录内**
     （可用 `backend` 包的父目录推导，不要硬编码 `/Users/...`）；越界一律返回
     `TOOL_CODE_UNAVAILABLE`，且**不得把该路径放进响应**。
   - `file` 输出为 `Path.relative_to(仓库根)` 的 POSIX 形式。
3. **新增路由**：在 `backend/app/api/routes_tools.py` 增加
   `GET /api/tools/{name}/code`：
   - **名称匹配（M-06）**：`{name}` 与注册名**精确相等**匹配，不做前缀/模糊/大小写归一化；
     不存在直接 `TOOL_NOT_FOUND`，**不得**回退文件系统查找或模糊兜底。
   - `name` 不存在 → `_document_error(404, "TOOL_NOT_FOUND", ...)`（沿用既有文案与签名）。
   - 解析失败/类型不符/越界 → `_document_error(404, "TOOL_CODE_UNAVAILABLE", "<固定文案>", request=request)`。
   - **错误文案（M-04，强制）**：`TOOL_CODE_UNAVAILABLE` 的 `message` 必须是**固定文案**；
     **禁止**拼接 `str(exc)`、异常 `repr`、绝对路径或 `entry` 之外的任何内部路径
     （`inspect.getsourcefile` 天然返回绝对路径，拼进错误体即泄漏）。异常详情只进服务端日志。
   - **任何异常都必须收敛成上面两类错误响应，不得抛 500。**
   - **禁用的 Tool 同样可查看代码（M-07）**：可见性不受 `enabled` 影响，不要按状态过滤。
   - **不加缓存（M-07）**：实时解析，避免行号漂移。
4. **测试**（扩展既有 `tests/test_tool_registry.py`，或新增不带 spec/task 编号的测试文件）：
   - 5 个注册 Tool 全部返回非空 `code`，且 `lineno` 满足 **M-01 判据**：该行是 `def <name>`，
     或是装饰器行且其后首个非装饰器行是 `def <name>`。**不要**断言「必须含 `def`」。
   - 类方法形态（`X.Y`）与模块函数形态都覆盖到。
   - 被装饰函数（`kb_ask`）返回原始函数源码，且 `lineno` 落在装饰器行（953，当前工作树；行号随源码漂移，以接口返回值为准）。
   - **M-03 负例**：构造「entry 解析到模块对象」（如只有模块路径、无属性链）与「解析到类对象」
     两种情形，断言返回 `TOOL_CODE_UNAVAILABLE` 且**不是**整文件源码。
   - `file` 是仓库相对路径；响应体（**含错误体**）内不出现绝对路径片段（不含 `/Users`）。
   - 未知 name → `TOOL_NOT_FOUND`；entry 无法解析 / 文件越界 → `TOOL_CODE_UNAVAILABLE`
     （用 monkeypatch 造异常），且错误 `message` 为固定文案、不含异常详情（M-04）。
   - **禁用（`enabled=false`）的 Tool 仍返回 200**（M-07）。
   - 既有 `GET /api/tools`、`GET /api/tools/{name}`、`PATCH /api/tools/{name}` 的响应结构未变。

## 5. 子代理分派

| 步骤 | 角色 | 模型 | 最小上下文 |
|---|---|---|---|
| 1-4 | `backend-dev` | `qwen3.8:27b-mlx` | 本 task + spec-036 的「数据模型/端点接口/边界/明确不做」+ 上述既有文件事实 |

回传后由架构师**读真实文件校验**（Grep 路由与解析函数、`sed` 看关键分支），再进下一门禁。

## 6. 边界与明确不做

- 只做**只读**解析，不执行、不 eval、不写文件、不改注册表状态。
- 不展示整个模块文件、不递归调用链。
- 不改既有三个接口的响应结构，不改 `ToolEntry.to_dict()`。
- 不动 `frontend/**`。
- 不新增第三方依赖。

## 7. 验收、风险与回滚

**验收**：

1. `GET /api/tools/{name}/code` 对 5 个注册 Tool 均返回 200 且字段齐全。
2. 定向 pytest 全绿；`ruff check backend` 对本任务改动文件零新增告警。
3. 既有 Tool 三个接口响应结构未变（有测试断言）。

**风险**：① `entry` 未来可能指向不可解析对象（内置/C 扩展）→ 已用 `TOOL_CODE_UNAVAILABLE` 兜底；
② 属性链解析可能误命中同名属性 → 用「从长到短尝试 import」的顺序规避，并以 `inspect` 复核。
**回滚**：本任务为纯新增路由 + 新增服务方法，删掉新增函数与路由即可，不影响既有行为。

## 8. 产出物、执行结果与变更日志

- 产出物：`backend/app/api/routes_tools.py`、`backend/app/skills/tool_service.py`（或新增解析模块）、测试文件。
- 执行结果：待执行后填写。
- 变更日志：待执行后填写。
