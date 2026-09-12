# Task 05：前端档位选择器三态与选中值校正

> 关联：[spec-026](../../specs/026-reasoning-effort-feedback-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03；当前状态：`已完成`

## 一句话目标

让档位选择器区分 `loading` / `known` / `stale` / `unknown` 四种状态，并在能力变化时**校正当前选中值到该模型支持的最高档**（带一次性提示），不再让「已置灰但仍选中」导致 409。

## 背景与前置条件

- 已确认 spec 026，重点 §数据模型（前端 state）、§边界 B9–B14、B11。
- 现状代码：`frontend/app.js`
  - `syncReasoningEffortOptions`（`:359-366`）：只改 `option.disabled`，**从不校正 `select.value`**。
  - `loadReasoningOptions`（`:368-391`）：失败分支编造 `supported=['off']`、`defaultEffort='off'`（`:386-389`）。
  - `normalizeReasoningEffort`（`:346-349`）与 `setReasoningEffort`（`:351-357`）：兜底硬编码 `'xhigh'`（`:346`、`:352`）；`:380` 同样硬编码。
  - 模型切换监听（`:340-344`）与会话载入（`:1412-1413`）都会触发 `loadReasoningOptions`。
- 前置：Task 03 已完成，接口返回 `source` 且 `unknown` 时 `supported_efforts=[]`、`default_effort=null`。
- 约束：静态资源引用带 `?v=N`；不引入新依赖。

## 数据、配置与接口

- `reasoningOptionsState` 增加：`loadState`（`loading`/`known`/`stale`/`unknown`）、`staleCachedAt`。
- 校正规则：当 `loadState ∈ {known, stale}` 且当前选中档位不在 `supported_efforts` 内 → 改为 `supported_efforts` 中序位最高者，并触发一次性提示。
- **例外（024 红线，B11）**：由 `reasoningEffortSelect` 的 `change` 事件（用户显式选择）触发的路径**不得**校正；若用户显式选了不支持档位，保持原值，由后端 409 兜底。
- 提示文案：「已因模型能力从『X』调整为『Y』」，显示在档位选择器旁，同一模型/会话内只出现一次。

## 实施步骤与文件边界

目标文件：**`frontend/app.js`**（必要时 `styles.css` 加提示条样式）。

1. `loadReasoningOptions` 成功分支：按 `data.source` 设置 `loadState`（`ollama_probe`/`cache` → `known`，`stale` → `stale`，`unknown` → `unknown`）；保存 `staleCachedAt`。
2. **删除**失败分支里编造 `['off']` 的逻辑（`:386-389`）；改为 `loadState='unknown'`、`supported=null`，并渲染对应 UI。
3. `syncReasoningEffortOptions` 增加第二参数或读取 state：`unknown` 时禁用除 `off` 外的全部选项并显示「能力未确认」+「重新检测」；`loading` 时整体禁用 + 「检测能力中…」；`stale` 时按旧集合禁用并显示「沿用 X 前的能力检测结果」。
4. 新增 `reconcileEffortWithCapabilities(reason)`：在 `loadReasoningOptions` 成功且非用户显式触发时调用，按上述校正规则改 `select.value`、更新 `lastEffort`，并弹出一次性提示。
5. 移除 `normalizeReasoningEffort` / `setReasoningEffort` / `:380` 处对 `'xhigh'` 的硬编码兜底，改为使用后端 `default_effort`（可能为 `null` → 则由前端按 `supported_efforts` 求最高档；都为空则 `off`）。
6. 「重新检测」按钮调用 `loadReasoningOptions(activeModel)` 并带 `refresh=1`，**不重发消息**。
7. 完成后可观察结果：切换到一个仅支持 `off/low` 的模型时，档位自动落到 `low`，并出现一次性提示；选择器中 `medium/high/xhigh` 置灰且带悬停说明。

## 子代理分派

| 角色 | 模型 | 最小上下文 | 文件范围 | 回读校验 |
|---|---|---|---|---|
| frontend-dev | `Deepseek-V4.1-Flash` | spec 026 §数据模型/边界 B9-B14 + `app.js:340-410`、`:1412` | `frontend/app.js`（必要时 `styles.css`） | 主会话核对：无 `['off']` 编造、`node --check`、版本号 |
| frontend-reviewer | `Deepseek-V4.1-Flash` | 同上 + diff | 评审报告 | DOM 契约、可访问性（`aria-disabled`/`title`）、XSS |

## 边界与明确不做

- 不做：不改 `/api/health` 与模型下拉框数据源。
- 不做：不加静态能力映射表、不猜能力。
- 不做：不修改 PATCH `/reasoning` 的调用逻辑（登记为后续项）。
- 不得把 `unknown` 状态伪装成「本模型只支持关闭」——必须显式说明是**未确认**（B12）。
- 用户显式选择的档位不得被静默改写（B11）。

## 验收、风险与回滚

- 验收：`unknown` 时选择器除 `off` 外全禁用，且展示「能力未确认」字样；`supported_efforts` 为空数组时**不得**渲染成「只支持关闭」。
- 验收：`stale` 时展示旧缓存时间，禁用集合与旧 `supported_efforts` 一致。
- 验收：切换模型触发校正 → 选中值等于新模型支持的最高档，提示出现一次；再次切回不重复刷提示。
- 验收：用户手动选档 → 不被校正；若选了不支持档位，发送后走 409 并由 Task 04 的文案正确呈现。
- 风险：校正逻辑与 `persistConversationReasoningEffort` 的 PATCH 时序可能冲突 → 校正后是否 PATCH 需在实现中明确并写回本文件（建议：校正不触发 PATCH，下次发送时随 payload 生效）。
- 回滚：`git checkout -- frontend/app.js frontend/styles.css`。

## 产出物、执行结果与变更日志

待执行后填写：静态检查命令、DOM 断言输出、真实模型切换的观察结果。
