# 036 Tool 模块查看内部 Python 代码

## 状态

**当前状态：已确认**

> 确认依据：
> 1. 用户提出「Tool 模块加上可以查看内部 python 代码」，并明确选择 —— ① 展示范围 =
>    **入口函数源码 + 文件路径/行号**（非整文件、非调用链）；② 交互方式 =
>    **「代码」按钮 + 弹窗**（复用 Skill 详情弹窗样式，点击后按需请求）。
> 2. 需求评审（`architect`）结论 **通过（附意见）**：P0 = 0、P1 × 4、P2 × 5、INFO × 1；
>    4 条 P1（M-01～M-04）已按评审意见全部回填进本 spec（见「需求评审意见回填记录」）。

## 一句话目标

让用户在「Skill 与 Tool」页面的 Tool 列表里，点开任一 Tool 就能**只读**看到它在后端真实执行的代码
（入口函数源码 + 仓库相对 `文件:行号`），用于审计「这个 Tool 到底跑了什么」，而不必去翻仓库。

## 背景与问题

- Tool 注册表的唯一事实源是代码：`ToolEntry.entry` 已保存真实入口（`模块.函数/方法`），
  例如 `backend.app.knowledge_base.infrastructure.retrieve.hybrid_search`。
- 但该字段**刻意不进 API 响应**（`models.py` `ToolEntry.to_dict` 只返回 `name/description/enabled`），
  前端只有名称与描述 —— 用户无法知道一个 Tool 实际执行了什么。
- 架构师已实测可行性（`inspect` 解析 5 个注册项），需求评审亦独立复跑、数字逐字一致：

| Tool | entry 形态 | file:lineno | 行数 |
|---|---|---|---|
| `search_paper_catalog` | 类方法 | `backend/app/paper_discovery/application/paper_discovery_search.py:94` | 71 |
| `download_and_import_paper` | 模块函数 | `backend/app/paper_discovery/application/paper_import.py:398` | 161 |
| `fetch_paper_detail` | 类方法 | `backend/app/paper_discovery/infrastructure/usenix_publication_source.py:994` | 61 |
| `kb_search` | 模块函数 | `backend/app/knowledge_base/infrastructure/retrieve.py:139` | 112 |
| `kb_ask` | **被装饰的路由函数** | `backend/app/api/routes_kb.py:952` | 133 |

全部可读、体积适中（2.7–7.3 KB），无需分页。

**暴露面前提（M-05）**：本功能成立的前提是「`127.0.0.1` 本机单用户、无鉴权」。
本次改动**不得**新增或放宽网络暴露（如 `HOST=0.0.0.0`）、不得改动鉴权策略、
不得改 `deploy/start.sh` 的默认绑定。后续若部署方式变更，须重新评估本节前提。

## 数据模型

本 spec **不新增持久化字段**，也不改动 `ToolEntry` 的既有字段语义。

| 字段（仅新增接口的响应体） | 类型 | 约束 |
|---|---|---|
| `name` | str | 必填；Tool 注册名 |
| `entry` | str | 必填；`模块.函数` 点分路径，取自注册表（**不接受用户输入**） |
| `file` | str | 必填；**仓库相对路径**（如 `backend/app/...py`），**不得**返回绝对路径 |
| `lineno` | int | 必填；`inspect.getsourcelines(obj)[1]`，即**源码块首行**（1-based） |
| `language` | str | 固定 `"python"` |
| `code` | str | 必填；入口函数/方法的源码原文，**含装饰器行与签名**（M-01） |

**`lineno` 语义（M-01，易误判）**：对带装饰器的函数，源码块首行是**装饰器行**而非 `def` 行 ——
实证 `backend/app/api/routes_kb.py` 的 952 行是 `@router.post("/kb/ask")`，`def kb_ask` 在 953。
因此验收判据必须是「第 `lineno` 行是 `def <name>`，**或**是装饰器行且其后首个非装饰器行是 `def <name>`」；
**禁止**使用「第 `lineno` 行必须含 `def`」这一判据。

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| `GET /api/tools/{name}/code` | 路径参数 `name`（注册名） | 200 + 上表字段 | 404 `TOOL_NOT_FOUND`；404 `TOOL_CODE_UNAVAILABLE` |

- 错误体复用 `routes_kb._document_error` 的既有结构 `{error_code, message, retryable, request_id}`；
  两类 404 均 `retryable=false`。
- **`TOOL_CODE_UNAVAILABLE` 的 `message` 必须是固定文案**（M-04）：**禁止**拼接 `str(exc)`、
  异常 `repr`、绝对路径或 `entry` 之外的任何内部路径；异常详情（含 stack）只进服务端日志。
- 触发 `TOOL_CODE_UNAVAILABLE` 的情形：`entry` 为空 / 无法解析 / 解析终点不是函数或方法 /
  源码不可读（内置函数、C 扩展）/ 解析到的文件不在仓库根目录内。
- **只读**：不执行、不 eval、不写文件、不改注册表状态；**不加缓存**（实时解析，避免行号漂移，M-07）。
- **名称匹配语义（M-06）**：`{name}` 与注册名**精确相等**匹配，不做前缀/模糊/大小写归一化；
  不存在时直接 `TOOL_NOT_FOUND`，**不得**回退文件系统查找。`entry` 只从注册表读取，
  **任何情况下不得接受请求方传入的点分路径**（含 query / body / header 变体）。

## 边界（每条之后会变成一条测试）

- 5 个注册 Tool 全部返回非空 `code`，且 `file:lineno` 满足 M-01 判据（装饰器行或 `def` 行，其后为 `def <name>`）。
- `entry` 为类方法（`X.Y`）与模块函数两种形态都要能正确解析。
- `entry` 指向被装饰的函数时，返回**原始函数**源码（`inspect` unwrap），且 `lineno` 落在装饰器行（M-01）。
- **解析终点必须是函数或方法（M-03）**：属性链**非空**且结果满足
  `inspect.isfunction(obj) or inspect.ismethod(obj)`；否则 `TOOL_CODE_UNAVAILABLE`。
  **禁止**以模块对象（`inspect.ismodule`）或类对象作为解析终点 —— 否则会返回整个文件/整个类体。
- `file` 必须是**仓库相对路径**；任何情况下不得返回形如 `/Users/...` 的绝对路径（含错误体）。
- 解析到的文件不在仓库根目录内（异常 entry / 软链越界）→ `TOOL_CODE_UNAVAILABLE`，且**不泄漏**该路径。
- Tool 名不存在 → `TOOL_NOT_FOUND`，不得回退成返回空源码。
- 源码不可读（内置函数、C 扩展、动态生成对象）→ `TOOL_CODE_UNAVAILABLE`，不得抛未捕获异常（500）。
- **禁用的 Tool（`enabled=false`）同样可查看代码**（M-07）：代码可见性不受启停状态影响。
- 接口不读取也不改变 `parameters` / `enabled`；既有 `GET /api/tools`、`GET /api/tools/{name}`、
  `PATCH /api/tools/{name}` 的**响应结构逐字不变**（须有测试断言，M-07）。
- 前端：点「代码」后弹窗展示 `entry` 与 `file:lineno`；加载中显示占位文案；失败显示可读错误，
  不得出现「有名称 + 空白代码」的割裂展示。
- 前端：连续切换不同 Tool 时，用自增序号 + `AbortController` 丢弃过期响应，避免慢响应覆盖新结果（串台）。
- **前端项目级硬约束（M-02）**：① 改动 `frontend/app.js` 或 `frontend/styles.css` 后，须把
  `frontend/index.html` 的 `?v=N` 从 **43 升到 44**（`:8` 与 `:518` 两处同步）；
  ② 源码文本与 `entry` / `file:lineno` 一律用 `textContent` 写入，**禁止** `innerHTML` 或模板字符串拼接；
  ③ 新增 DOM id 必须同步扩 `tests/test_frontend_skill_tool_contract.py` 的静态断言
  （id 存在 + `textContent` 用法 + 无 `innerHTML`）；
  ④ 新增 class 必须在 `frontend/styles.css` 有对应规则。

## 明确不做

- 不展示**整个模块文件**源码，不递归展开调用链（用户已选择只看到入口函数；并由 M-03 机械封死）。
- 不提供代码编辑/保存/热重载；本功能**只读**（M-07）。
- 不执行或求值任何代码。
- 不引入语法高亮库（用既有 `<pre>` 纯文本展示），不新增前端依赖。
- 不改动 `ToolEntry.to_dict()` 的输出，也不把 `entry` / `parameters` 加进列表接口。
- 不改动 Tool 的启停逻辑与状态文件。
- 不碰 Skill 侧的任何行为与弹窗。
- 不做缓存、不做鉴权/限流、不改网络暴露面（M-05）。

## 产品使用步骤（由架构师代拟；产品经理角色不适用，见「执行配置」）

- 步骤 1：打开左侧「Skill 与 Tool」页面，滚到 Tool 区域。
- 步骤 2：在目标 Tool（如 `kb_search`）右侧点「代码」。
- 步骤 3：弹窗显示该 Tool 的入口 `模块.函数`、仓库相对 `文件:行号` 与源码，关闭即结束。
- 验收场景 A：5 个 Tool 逐个点开，都能看到非空源码，且 `文件:行号` 满足 M-01 判据。
- 验收场景 B：快速连续点开两个不同 Tool，最终显示的必须是**后点的那个**（无串台）。
- 验收场景 C：点开再关闭，列表与启停状态不变；刷新页面后 Tool 列表响应结构未变
  （仍只有 `name/description/enabled`）。

## 需求评审意见回填记录（2026-09-13，评审者 `architect`）

| 编号 | 级别 | 评审意见 | 回填位置 |
|---|---|---|---|
| M-01 | P1 | `lineno` 对带装饰器函数是**装饰器行**（`routes_kb.py:953` = `@router.post("/kb/ask")`，装饰器行），原判据「必须含 `def`」与事实冲突 | 「数据模型」`lineno` 语义段 + 「边界」第 1 条 |
| M-02 | P1 | 前端缺 `?v=43→44`、`textContent`（禁 `innerHTML`）、静态契约断言、新增 class 需配 CSS 四条项目级硬约束 | 「边界」最后一条 |
| M-03 | P1 | 「不展示整个模块文件」无机械约束：同一算法遇模块 entry 会返回整文件（实测 182 行） | 「边界」第 4 条（解析终点必须 `isfunction/ismethod` 且属性链非空） |
| M-04 | P1 | 错误 `message` 未约束，`inspect` 天然返回绝对路径 → 可能经错误体泄漏 | 「端点 / 接口」`message` 固定文案段 |
| M-05 | P1 | 暴露面前提未记录 | 「背景与问题」暴露面前提段 + 「明确不做」 |
| M-06 | P2 | 名称匹配语义、`entry` 来源 | 「端点 / 接口」名称匹配语义段 |
| M-07 | P2 | 只读与回归冻结、禁用 Tool 亦可查看、不加缓存 | 「端点 / 接口」+「边界」第 9 条 |
| M-08 | P2 | （其余 P2 / INFO 见评审文档） | 详见 `docs/sdd/reviews/036-requirement-review.md` |

> 评审另记两处与本次实现无关的台账失真，已由架构师记录待办：
> `docs/sdd/spec-status-changelog.md` 中「036 空缺」表述已过期；`docs/sdd/specs/023-*.md` 中
> Tool「4 个」的旧表述与当前 5 个不符。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、可行性实测、落地校验 |
| 产品经理 | 不适用（功能边界单一，产品步骤由架构师代拟） | — | — | — |
| 开发主管 | `qwen3.8:27b-mlx` | 32k | `Task(architect)` | 需求/技术评审、合并裁决 |
| 后端开发 | `qwen3.8:27b-mlx` | 32k | `Task(backend-dev)` | 新增 `/api/tools/{name}/code` |
| 前端开发 | `qwen3.8:27b-mlx` | 32k | `Task(frontend-dev)` | Tool 列表「代码」按钮与弹窗 |
| 后端评审 | `qwen3.8:27b-mlx` | 32k | `Task(backend-reviewer)` | 只评 `backend/**` 改动 |
| 前端评审 | `qwen3.8:27b-mlx` | 32k | `Task(frontend-reviewer)` | 只评 `frontend/**` 改动 |
| 后端回归 | `qwen3.5:9b` | 32k | `Task(backend-tester)` | 定向 pytest |
| 前端回归 | `qwen3.5:9b` | 32k | `Task(frontend-tester)` | 静态核对 |
| 验收总控 | `qwen3.5:9b` | 32k | `Task(tester)` | 运行时端到端验收与报告 |

## 任务计划

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-036 | 本文件 | — | 完成 |
| 02 | 后端：新增 `GET /api/tools/{name}/code` | [`task-02-backend-tool-code-api.md`](../plans/036/task-02-backend-tool-code-api.md) | 01 | 已完成 |
| 03 | 前端：Tool 列表「代码」按钮与弹窗 | [`task-03-frontend-tool-code-dialog.md`](../plans/036/task-03-frontend-tool-code-dialog.md) | 02 | 已完成 |
| 04 | 评审、回归与端到端验收 | [`task-04-review-regression-acceptance.md`](../plans/036/task-04-review-regression-acceptance.md) | 03 | 已完成 |

## 评审记录

- 需求评审：`docs/sdd/reviews/036-requirement-review.md`（**通过（附意见）**，P0=0 / P1×4 已回填 / P2×5 / INFO×1）
- 技术评审：`docs/sdd/reviews/036-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/036-acceptance-review.md`（待评审（未执行））

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-13 | 架构师(自身) | 编写本 spec；先实测 `inspect` 对全部 5 个注册 entry 的可解析性（含被装饰的 `kb_ask`）作为 Go/No-Go 前提；就展示范围与交互方式向用户确认 |
| 2026-09-13 | `architect` | 需求评审：**通过（附意见）**，P0=0 / P1×4 / P2×5 / INFO×1；独立复跑 inspect 复核数字一致，并指出 M-01（`lineno` 装饰器行）、M-03（整模块文件泄漏）等 4 条阻塞项 |
| 2026-09-13 | 架构师(自身) | 按评审意见回填 M-01～M-08（含暴露面前提、名称匹配语义、只读与回归冻结、前端 `?v=43→44` 与 `textContent` 硬约束）；状态转 `已确认` |
