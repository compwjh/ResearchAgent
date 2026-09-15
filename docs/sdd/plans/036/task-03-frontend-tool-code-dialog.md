# Task 03 — 前端：Tool 列表「代码」按钮与弹窗

> 关联：[spec-036](../../specs/036-tool-source-code-viewer.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`待执行`

## 1. 状态与一句话目标

**待执行。** 在「Skill 与 Tool」页面的 Tool 列表每一项加一个「代码」按钮，点击后弹窗只读展示
该 Tool 的入口 `模块.函数`、仓库相对 `文件:行号` 与源码。

## 2. 背景与前置条件

- 依赖任务 02 的后端接口 `GET /api/tools/{name}/code`（200 返回
  `{name, entry, file, lineno, language, code}`；404 为 `TOOL_NOT_FOUND` / `TOOL_CODE_UNAVAILABLE`）。
- 既有实现：
  - `frontend/index.html` —— Tool 列表 `<ul id="st-tool-list">`；Skill 详情弹窗
    `#st-skill-dialog`（class `settings-dialog st-detail-dialog`），正文 `<pre id="st-detail-body">`。
  - `frontend/app.js` —— `renderToolList()`（约 3903 行）逐项渲染
    `st-text`（`st-name` + `st-desc`）与 `st-actions`（启停按钮）；
    `openSkillDetail()`（约 3850 行）是**必须复用的范式**。
- 用户已定：交互方式 = **「代码」按钮 + 弹窗**（复用 Skill 详情弹窗样式），不是行内展开、不是侧边面板。

## 3. 数据、配置与接口

不适用新增配置；消费任务 02 的接口。

| 请求 | 成功 | 失败 |
|---|---|---|
| `GET /api/tools/{name}/code` | 200 → 弹窗展示 `entry`、`file:lineno`、`code` | 404 → 弹窗展示可读错误文案 |

## 4. 实施步骤与文件边界

**允许改动**：`frontend/index.html`、`frontend/app.js`（必要时 `frontend/styles.css`）。
**禁止改动**：`backend/**`；Tool 的启停逻辑与按钮；Skill 侧任何行为与弹窗。

1. **`index.html`**：新增一个 Tool 代码弹窗（建议 id `st-tool-code-dialog`），
   复用 `settings-dialog st-detail-dialog` 的既有 class，内部包含：
   - 名称 `#st-code-name`、`entry` 行 `#st-code-entry`、`file:lineno` 行 `#st-code-location`；
   - 源码 `<pre id="st-code-body">`；
   - 关闭按钮（沿用 `<form method="dialog">` + `value="cancel"` 的既有写法）。
2. **`app.js`**：
   - 在 `renderToolList()` 的 `st-actions` 里，于启停按钮**之前**追加「代码」按钮
     （class `secondary-button`），点击调 `openToolCode(tool, button)`；`tool.name` 为空时禁用。
   - 新增 `openToolCode(tool, button)`，**严格复用 `openSkillDetail()` 的防串台范式**：
     自增序号 + `AbortController` 中止上一次请求，响应返回时若序号不符或已 abort 则直接丢弃。
   - 加载中：`#st-code-body` 显示占位文案（如「加载中…」）。
   - 失败：名称/entry/location/body **统一展示同一失败文案**，禁止出现
     「有名称 + 空白代码」的割裂展示（与 spec-023.1 F3 的处理一致）。
   - `finally` 里恢复按钮可用态并清掉 controller 引用。
3. **样式**：优先复用既有 `.st-detail-body` / `.st-detail-*` class；确需新增时只做最小补充，
   不引入语法高亮库、不新增依赖。

> **M-02（强制，P1）—— 前端项目级硬约束，四条都要落地**：
> ① 改动 `frontend/app.js` 或 `frontend/styles.css` 后，必须把 `frontend/index.html` 的 `?v=N`
> 从 **43 升到 44**（`:8` 的 `styles.css?v=43` 与 `:518` 的 `app.js?v=43` **两处同步**）。
> ② 源码文本 `code` 与 `entry` / `file:lineno` 一律用 **`textContent`** 写入，
> **禁止** `innerHTML` 或模板字符串拼接（代码内容不可信，防注入）。
> ③ 新增 DOM id 必须同步扩 **`tests/test_frontend_skill_tool_contract.py`** 的静态断言：
> id 存在 + `textContent` 用法 + 无 `innerHTML`。
> ④ 新增 class 必须在 `frontend/styles.css` 有对应规则。

## 5. 子代理分派

| 步骤 | 角色 | 模型 | 最小上下文 |
|---|---|---|---|
| 1-3 | `frontend-dev` | `qwen3.8:27b-mlx` | 本 task + spec-036 的「边界/明确不做」+ 上述既有 DOM id 与 `openSkillDetail` 范式 |

回传后由架构师**读真实文件校验**（Grep 新增 id/函数、`node --check`），再进下一门禁。

## 6. 边界与明确不做

- **只读展示**：不提供编辑/保存，不执行代码。
- 不引入语法高亮库与任何新依赖（纯 `<pre>` 文本）。
- 不改 Tool 列表接口消费方式，不改启停逻辑，不动 Skill 侧。
- 不改 `backend/**`。

## 7. 验收、风险与回滚

**验收**：

1. `node --check frontend/app.js` 通过；`tests/test_frontend_skill_tool_contract.py` 等前端契约 pytest 不回归。
2. Tool 列表每项出现「代码」按钮；5 个 Tool 都能点开并看到非空源码与 `file:lineno`。
3. 快速连续点开两个不同 Tool，最终显示**后点的那个**（无串台）。
4. 关闭弹窗后列表与启停状态不变。
5. `frontend/index.html` 的 `?v=N` 已由 43 升到 44（`:8` 与 `:518` 两处一致）。
6. 全文件无 `innerHTML` 拼接源码；新增 class 在 `styles.css` 有规则。

**风险**：① 慢响应串台 → 已用 `openSkillDetail` 的序号 + `AbortController` 范式规避；
② 源码较长（最长 161 行）→ 弹窗内滚动展示，不做分页、不做截断。
**回滚**：删除新增弹窗节点与 `openToolCode` 及按钮即可，不影响既有列表与启停。

## 8. 产出物、执行结果与变更日志

- 产出物：`frontend/index.html`、`frontend/app.js`（必要时 `frontend/styles.css`）。
- 执行结果：待执行后填写。
- 变更日志：待执行后填写。
