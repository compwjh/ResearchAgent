> 关联：[spec-037](../../specs/037-startup-readiness-gap-and-ux-bugs.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01（与 02 联调）；当前状态：`已完成`

# 任务 03：前端——上下文模块始终可见 + KB 计数加载态

## 一句话目标
删除「无会话即隐藏」逻辑，让上下文模块**永远可见**；并把 `#kb-count` 的硬编码 0 换成加载态。

## 背景与前置条件
- spec-037 Bug 1（前端半）与 Bug 2。
- `frontend/app.js`：`renderContextUsage` 882-890（无会话 `is-idle`）、`showContextUsageLoading` 837-856、`renderContextUsageError` 858-877、`kbCount` 5238、`renderKbPapers` 5448-5451。
- `frontend/index.html`：`#kb-count` 第 398 行硬编码 `0`；`#context-meter` 第 153 行初始带 `is-idle`。
- `frontend/styles.css`：`.composer-context.is-idle{visibility:hidden}` 第 39 行；`.async-slot-spinner` 第 53 行。

## 实施步骤（文件边界：`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`）
1. **上下文模块**：去掉「无会话 → 隐藏」分支（不再用 `is-idle` 做 `visibility:hidden`）。三态——加载中 spinner（沿用 `showContextUsageLoading`）、有数据显示真实百分比（含只有恒定上下文时的基线值）、失败 `—` + 重试（沿用 `renderContextUsageError`）。
2. 无会话**不等于 0% 也不隐藏**：渲染仅含恒定上下文的基线占比（依赖任务 02 的后端返回）。
3. **KB 计数**：`#kb-count` 初始渲染占位/转圈（复用 `.async-slot-spinner`），数据到达后淡入真实数字（复用 `#model-count.model-count-fade` 模式），失败显示 `!` 且可点重试。

## 边界与明确不做
- 不改 `#model-select` 位置与逻辑（spec-035 已定）。
- 不引入新色系/新框架，复用既有 `async-slot-spinner` 与 `--accent`。
- 不改百分比计算规则（只负责展示）。

## 验收
- 打开页面、未选任何会话时，上下文模块**可见**且显示恒定上下文基线百分比（非 0% 占位、非隐藏）。
- 加载中显示 spinner；10s 未收敛显示「仍在加载…」；失败显示 `—` 与重试按钮。
- 首屏 `#kb-count` 不出现硬编码 `0`；数据到达后数字正确；接口失败显示 `!` 可重试。
- `node --check` 通过；前端契约测试全绿。
