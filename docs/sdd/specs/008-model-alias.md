# 008 - 模型别名展示与设置

- 状态：`已完成`（v2 行内编辑交互，验收通过 A1–A9，R1–R3 风险已修复）
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

### 3. 设置入口（交互）— 【已重做，替代 v1 统一弹层】

> **重做原因**：v1 实现为"列表顶部『编辑别名』按钮 + 统一弹层批量编辑"，用户反馈不符合预期——
> 期望**在模型自己的卡片内直接改**（别名归属该模型，编辑入口随卡片走），而非集中到列表外面批量改。

**新交互：卡片内行内编辑（inline edit）**

- 每个模型卡片右侧有一个 **✎ 铅笔图标**（`.model-edit`），hover 时高亮。
- 点击 ✎ → 卡片内的名字**原地变为输入框**（不弹层、不跳转），预填当前别名。
- 保存：`Enter` 或**失焦(blur)** 即保存；取消：`Escape`。
- 清空输入框后保存 = 清除该模型别名（回退显示真实名）。
- **移除** v1 的列表顶部"编辑别名"按钮、`.alias-bar` 容器、`openAliasEditor()` 弹层与"重置全部"批量按钮。
  （单行清除能力保留在卡片内，批量重置入口取消——用户未要求，避免过度设计。）

**与"点击切换当前模型"的冲突处理（关键）**：
- `<li>` 的 click 事件当前用于切换 `activeModel`。✎ 按钮与输入框的 click/keydown 必须 `event.stopPropagation()`，否则点编辑会误切当前模型。

**展示结构：别名为主 + 真实名副标题**

```html
<li class="model-item" data-model="oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU">
  <div class="model-text">
    <span class="model-name">Qwen3.8 27B</span>        <!-- 别名；未设别名时为真实名 -->
    <span class="model-real">oamazonasgabriel/…</span>  <!-- 仅当已设别名时显示 -->
  </div>
  <button class="model-edit" type="button" title="编辑别名">✎</button>
  <span class="model-badge current">当前</span>
</li>
```
- `.model-real`（真实名灰色小字）**仅在已设别名时显示**；未设别名时隐藏，避免与 `.model-name` 内容重复。

**保存后同步刷新三处**：重渲染模型列表、重建顶部 `modelSelect` 的 option 文本（value 保持真实名）、更新 `modelLabel`。

### 4. 明确不做
- 不改动后端 `ArticleSettings` schema（别名属前端偏好）。
- 不改动 `/api/health` 返回结构。
- 不把别名同步到后端（多设备不共享，符合"前端偏好"定位）。
- 不改变 `activeModel`/`modelSelect.value` 的真实名语义。

### 5. 强制约束（实现必须遵守，来源：开发主管评审意见）
- **XSS 安全**：别名渲染必须用 `textContent`（禁止 `innerHTML` 注入）；弹层回显用 `input.value = alias`。
- **localStorage 容错**：`loadAliases()` 必须 `try/catch` JSON.parse，失败回退 `{}` 并清脏数据；封装 `safeStore/safeLoad`，隐私模式禁用时降级为内存 `Map`。
- **别名长度**：行内输入框 `maxlength="40"`，与 `.model-name` 文本截断对齐。
- **事件隔离（v2 新增）**：`.model-edit` 按钮与编辑态 input 的 `click`/`keydown` 必须 `event.stopPropagation()`，不得冒泡触发 `<li>` 的"切换当前模型"。
- **重复渲染防护（v2 新增）**：`blur` 与 `Enter` 都可能触发保存，需防重复写与重复渲染（保存后置脏标记/先移除监听再渲染）。
- **DOM 契约（v2 新增，防回归）**：JS 渲染的 class 必须与 CSS 选择器交叉核对（`.model-item/.model-text/.model-name/.model-real/.model-edit/.model-badge`），禁止凭记忆书写——曾因 JS 输出 `model-list-item` 而 CSS 写 `.model-item` 导致样式整体失效。
- **静态资源版本号（v2 新增，防回归）**：改动 `app.js`/`styles.css` 后同步升 `index.html` 的 `?v=N`，否则浏览器沿用旧缓存导致"服务端已更新但页面未变"。

## 数据模型 / 接口
- 无新增接口。持久化为 `localStorage["model_aliases"]`，schema：
  ```json
  { "oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU": "Qwen3.8 27B 量化" }
  ```

## 产品使用步骤（PM 补充，已按 v2 行内编辑更新）
1. 用户打开"模型库" tab，看到模型卡片列表（未设别名时显示真实名）。
2. 找到要改的模型，点击其卡片右侧的 **✎ 图标**，卡片内名字原地变为输入框。
3. 输入易读别名（例如把 `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU` 改为 `Qwen3.8 27B`）。
4. 按 `Enter` 或点击别处即保存；按 `Esc` 取消。
5. 保存后该卡片以**别名大标题**显示，**真实名降级为灰色小字**在下方；顶部下拉与顶部模型标签同步更新。
6. 清空输入框并保存 = 清除别名，恢复显示真实名（真实名小字随之隐藏）。
7. 刷新页面后别名仍生效。
8. 边界：模型列表为空（`/api/health` 返回 `models: []`）时，打开"模型库" tab 看到「暂无可用模型」的提示；此时没有任何模型卡片，因而也没有 ✎ 编辑入口，用户无法发起编辑（此为预期，不算异常）。
9. 边界：浏览器处于隐私模式或禁用了 localStorage 时，在卡片内编辑别名并保存后，**本次会话内**该模型仍按别名正常展示（降级为内存存储）；但刷新页面后内存中的别名丢失，模型会回退显示真实名（此为预期降级，别名不保留）。

## 验收点（v2）
- A1 点 ✎ 后卡片内名字原地变输入框；`Enter` 与失焦均能保存。
- A2 保存后：卡片显示"别名大标题 + 真实名灰色小字"，顶部下拉 option 文本与 `modelLabel` 同步显示别名；**value 仍为真实名**。
- A3 未设别名时只显示真实名（不显示重复的 `.model-real`），与改动前一致，无回归。
- A4 别名持久化：刷新后仍生效（localStorage）。
- A5 清空保存可清除别名并正确回退真实名。
- A6 **点 ✎ 编辑或在输入框内操作，不会误触发"切换当前模型"**（事件隔离生效）。
- A7 不影响实际模型请求：`activeModel` / `modelSelect.value` 始终为真实模型名。
- A8 样式与全站一致（复用现有 token，选择器带 `#models-view` 前缀隔离），不引入裸 DOM。
- A9 `Esc` 可取消编辑且不写入。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 职责 |
|---|---|---|---|
| 架构师 | 自身（当前执行本任务的 Agent，不写死模型代号） | 200k | 编写/修订本 spec、技术决策、落地校验 |
| 产品经理 | qwen3.5:9b（本地 Ollama） | 32k | 梳理产品使用步骤、验收场景 |
| 开发主管 | qwen3.8:27b（本地 Ollama） | 32k | 需求/技术/验收评审、合并裁决 |
| 初级开发 | oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU（本地 Ollama 量化 27B） | 32  | 实现别名逻辑与设置面板前端代码 |
| 测试 | qwen3.5:9b（本地 Ollama） | 32k | 验收评审 |

> 选型依据：纯前端 localStorage 偏好，复杂度低。本地模型名以 `ollama list` 实际输出为准（已核对）。架构师角色由当前 Agent 自身承担（代号随版本变化，不硬编码）。

## 评审记录
- 需求评审：`docs/sdd/reviews/008-requirement-review.md`（结论：/）
- 技术评审：`docs/sdd/reviews/008-tech-review.md`（结论：通过，附意见已采纳）
- 验收评审：`docs/sdd/reviews/008-acceptance-review.md`（结论：/）

## 变更日志（Changelog）
| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-08-27 | 架构师(Hy4) | 编写 spec-008（模型别名展示与设置） |
| 2026-08-27 | 开发主管(Hy4 兼行) | 需求评审通过、技术评审通过（附意见已采纳进 §5 强制约束） |
| 2026-08-27 | 初级开发(Hy4 兼行) | 实现别名逻辑：localStorage 工具 + displayName 替换 option/modelLabel/nameSpan + 编辑弹层 + 样式 |
| 2026-08-27 | 测试(Hy4 兼行) | 验收通过（A1–A6 + XSS/容错/空态）；按用户要求本 spec 不调用子模型，全部角色由 Hy4 承担 |
| 2026-08-27 | 开发主管(Hy4 兼行) | 验收签字，spec 转 `已完成` |
| 2026-08-28 | 用户 | 反馈 v1 交互不符预期：要求在模型自己的卡片内编辑别名，而非列表外统一弹层 |
| 2026-08-28 | 架构师(Hy4) | 修订 spec-008 为 v2 行内编辑（✎ + 原地输入框 + 双行展示），状态转 `实施中`，记录 spec-status-changelog |
| 2026-08-28 | 架构师(Hy4) | v2 实现完成，首次以 tester 子代理（tools + sdd-acceptance skill + 本地模型）执行验收，A1–A9 通过；R1/R2/R3 修复并复验，静态资源升 ?v=4 |
