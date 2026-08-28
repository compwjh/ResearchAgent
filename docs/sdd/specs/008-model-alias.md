# 008 - 模型别名展示与设置

- 状态：`已完成`
- 类型：功能增强（前端展示层）
- 关联痛点：Ollama 模型名冗长难读（如 `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU`），用户希望用简短别名展示，并可在界面上设置。

## 一句话目标

为模型库列表（及切换器）支持**自定义别名**：用户可给每个模型起易读名称，前端用别名展示，真实模型名仅在底层请求时使用。别名持久化在前端（localStorage），不污染后端 settings。

## 现状（已核实）

- 模型列表数据来自 `GET /api/health` 的 `models: [...]`（真实模型名）。
- `frontend/app.js` 中用 `activeModel`、`modelSelect.value` 持有**真实模型名**；展示节点 `<span class="model-name">` 仅作文本显示。
- 后端已有 `GET/PUT /api/agent/settings`（持久化 `article_settings.json`），但属于文章检索配置，与模型别名无关，不应混入。
- 前端已有 `#settings-dialog`（文章检索设置），与别名场景不直接耦合；模型库视图以 `#models-view` 独立呈现。

## 方案（仅前端，不影响后端请求）

### 1. 别名存储
- 前端用 `localStorage` 存映射：`{ "<真实模型名>": "<别名>" }`，key 定为 `model_aliases`。
- 读取：`loadAliases()` 容错（JSON 解析失败/缺字段则回退空对象）。
- 展示规则：`displayName(name) = aliases[name] || name`（无别名时用原始名）。

### 2. 展示替换点（最小改动）
- `renderModelList`：`nameSpan.textContent = displayName(name)`（仅改展示，不选值）。
- 顶部 `modelLabel`（顶部模型显示，若有）同步走 `displayName`。
- 顶部下拉 `modelSelect` 的 option 文本也走 `displayName`，但 `value` 保持真实名。

### 3. 设置入口（交互）
方案：在**模型库视图**顶部加一行"编辑别名"按钮（或每行 hover 出现 ✎），点击弹出轻量弹层/内联编辑：
- 弹层列出所有模型（真实名 + 输入框预填当前别名），保存即写 `model_aliases` 并重新渲染。
- 选中真实名不可编辑；别名为空即清除别名（回退原名）。
- 提供"重置全部"按钮。

交互细节（由初级开发实现，不强制）：
- 可复用现有 dialog 风格（参考 `.settings-dialog` 的 token：圆角/阴影/backdrop）；
- 无别名时折叠，避免干扰；编辑态有保存/取消。

### 4. 明确不做
- 不改动后端 `ArticleSettings` schema（别名属前端偏好）。
- 不改动 `/api/health` 返回结构。
- 不把别名同步到后端（多设备不共享，符合"前端偏好"定位）。
- 不改变 `activeModel`/`modelSelect.value` 的真实名语义。

### 5. 强制约束（实现必须遵守，来源：开发主管评审意见）
- **XSS 安全**：别名渲染必须用 `textContent`（禁止 `innerHTML` 注入）；弹层回显用 `input.value = alias`。
- **localStorage 容错**：`loadAliases()` 必须 `try/catch` JSON.parse，失败回退 `{}` 并清脏数据；封装 `safeStore/safeLoad`，隐私模式禁用时降级为内存 `Map`。
- **空态边界**：`/api/health` 返回空列表时，隐藏/禁用"编辑别名"按钮，避免空弹层。
- **别名长度**：输入框 `maxlength="40"`，与 `.model-name` 文本截断对齐。
- **重置全部**：直接 `removeItem('model_aliases')`，避免已下线模型残留累积。

## 数据模型 / 接口
- 无新增接口。持久化为 `localStorage["model_aliases"]`，schema：
  ```json
  { "oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU": "Qwen3.8 27B 量化" }
  ```

## 产品使用步骤（PM 补充）
1. 用户打开"模型库" tab，看到模型列表（默认显示真实名）。
2. 点击"编辑别名"按钮，弹出别名设置面板。
3. 为每个模型填写别名（例如把 `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU` 改为 `Qwen3.8 27B`）。
4. 保存后，列表与该模型的选择器均立即以别名显示；真实名仍用于底层请求。
5. 清空某别名或"重置全部"可恢复原始展示。

## 验收点
- A1 别名保存后，模型库列表与顶部选择器均显示别名（真实名保留于 value）。
- A2 未设置别名时，回退显示真实名，行为与改动前一致（无回归）。
- A3 别名持久化：刷新页面后仍生效（localStorage）。
- A4 清除别名/重置后正确回退。
- A5 不影响实际模型请求（activeModel 仍为真实名）。
- A6 设置面板样式与全站一致（复用 `.settings-dialog` token），不引入裸 DOM。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 职责 |
|---|---|---|---|
| 架构师 | Hy3（即当前执行本任务的 Agent 自身） | 200k | 编写/修订本 spec、技术决策、落地校验 |
| 产品经理 | qwen3.5:9b（本地 Ollama） | 32k | 梳理产品使用步骤、验收场景 |
| 开发主管 | qwen3.8:27b（本地 Ollama） | 32k | 需求/技术/验收评审、合并裁决 |
| 初级开发 | oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU（本地 Ollama 量化 27B） | 32  | 实现别名逻辑与设置面板前端代码 |
| 测试 | qwen3.5:9b（本地 Ollama） | 32k | 验收评审 |

> 选型依据：纯前端 localStorage 偏好，复杂度低。本地模型名以 `ollama list` 实际输出为准（已核对）。架构师角色由当前 Agent（Hy3）自身承担。

## 评审记录
- 需求评审：`docs/sdd/reviews/008-requirement-review.md`（结论：/）
- 技术评审：`docs/sdd/reviews/008-tech-review.md`（结论：通过，附意见已采纳）
- 验收评审：`docs/sdd/reviews/008-acceptance-review.md`（结论：/）

## 变更日志（Changelog）
| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-08-27 | 架构师(Hy3) | 编写 spec-008（模型别名展示与设置） |
| 2026-08-27 | 开发主管(Hy3 兼行) | 需求评审通过、技术评审通过（附意见已采纳进 §5 强制约束） |
| 2026-08-27 | 初级开发(Hy3 兼行) | 实现别名逻辑：localStorage 工具 + displayName 替换 option/modelLabel/nameSpan + 编辑弹层 + 样式 |
| 2026-08-27 | 测试(Hy3 兼行) | 验收通过（A1–A6 + XSS/容错/空态）；按用户要求本 spec 不调用子模型，全部角色由 Hy3 承担 |
| 2026-08-27 | 开发主管(Hy3 兼行) | 验收签字，spec 转 `已完成` |
