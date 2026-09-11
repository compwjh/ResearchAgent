# Spec 022 Task09 需求评审：桌面项目树与会话菜单重构

## 评审范围与依据

- 评审对象：`docs/sdd/specs/022-project-conversation-memory.md`、`docs/sdd/plans/022/task-09-desktop-project-tree-sidebar.md`、`docs/sdd/plans/022/task-05-research-context-progress.md`。
- 现状证据：侧栏同时保留旧 `.project-switcher` 和新 `.flat-projects`，见 `frontend/index.html:14-41`；隐藏的旧创建表单仍在 DOM，见 `frontend/index.html:42-46`，且 `.new-project-form` 规则会强制 `display:grid`，见 `frontend/styles.css:40`。
- 现有交互仍使用 `window.prompt` / `window.confirm` 来重命名、移动、归档和删除，见 `frontend/app.js:781-858`；项目、会话菜单是滚动容器内绝对定位元素，见 `frontend/styles.css:51-60,117-126`。

## 结论

**GO（需求门禁通过；仅在本报告冻结范围内实施）。**

Task09 的用户价值、桌面边界、错误场景、验收行为与 Task05 已交付的会话/记忆契约可测地分离。它不要求改变项目、会话或记忆的领域含义；现有移动路径仍经 `PATCH /api/conversations/{id}`，见 `backend/app/api/routes_conversations.py:356-362`，可以保持服务端确认与项目隔离。

## 冻结范围

1. 桌面侧栏只保留一个可整体折叠的“项目”标题；项目树下只显示对应项目会话，未绑定会话只在“最近会话”出现。不得保留 `#project-select`、旧治理按钮或 `#new-project-form` 的兼容 DOM/事件。
2. 项目箭头只控制展开；项目名称只设置后续草稿的项目上下文，不移动当前会话。此保护与现有注释的意图一致，见 `frontend/app.js:770-778`。
3. 新建、重命名、移动均使用应用内对话框；归档/删除使用应用内确认框。不得再由 Task09 路径调用浏览器原生 `prompt` 或 `confirm`。
4. 移动只允许选择已有、`active`、非当前项目；请求必须继续带 `confirm_move: true` 和用户选择的 `memory_history_policy`。取消或失败不得预先改变 `conversationState`、项目展开状态或 DOM。
5. 移动成功后必须保留当前聊天，目标项目展开、会话仅出现一次且保持高亮；“移出项目”仍是独立菜单动作。
6. 项目内分页固定每批 10 条；未绑定“最近会话”固定每批 20 条。归档项目与归档会话各自是独立视图，恢复后恢复此前展开和滚动位置。

## 明确不做

- 不交付移动端项目树（Task06）、全量回归（Task08）、新的项目/会话存储、移动专用 API、手动项目排序字段或 schema 迁移。
- 不修改 Task05 已冻结的 stable turn、处理过程、异步记忆分析、RAG 来源/项目隔离，亦不改变项目删除时文档原件保留的语义。
- 不按参考截图逐像素复刻；只实现其信息层级、折叠与菜单位置。

## 风险分级与可执行约束

- **P1 — 状态污染：** 现有 `selectProjectContext()` 会立即切换 `conversationState.projectId` 并重载单一会话列表（`frontend/app.js:770-778`）。树渲染必须把“已打开会话身份”“草稿项目上下文”“展开项目”拆成明确状态；移动 API 成功前不得写其中任何目标状态。
- **P1 — 可访问性/菜单：** 现有行级菜单没有统一的外部点击、Esc 关闭和触发控件焦点恢复机制（菜单切换仅见 `frontend/app.js:757-764,810-819`）。实现必须以一个 active menu 状态保证同时最多一个打开，并覆盖鼠标与键盘。
- **P1 — 视觉裁剪：** `.project-list` / `.conversation-list` 都有 `overflow-y:auto`（`frontend/styles.css:51,117`），`z-index` 不能突破祖先裁剪。菜单必须用 portal/顶层定位层或等效脱离滚动裁剪的方案，并以底部向上翻转验收。
- **P2 — 本地排序完整性：** 当前项目列表一次取 100 条（`frontend/app.js:878-883`）。Task09 只允许浏览器本地名称排序；实现报告须说明项目树所持项目集合与项目 API cursor 的关系，避免仅对一个不完整页做全局 A–Z 声明。

## 测试门槛

- 前端：唯一“项目”标题、无旧下拉/常驻表单、无 Task09 路径的原生 `prompt/confirm`；桌面 DOM 契约覆盖树、空项目、10/20 条分页、移动成功/取消/失败、归档恢复和无重复节点。
- 交互：真实浏览器验证底部与滚动边缘菜单不裁剪、外点/Esc/焦点恢复、键盘打开和选择、创建后惰性草稿、移动后聊天不断开。
- 回归：`node --check frontend/app.js`、相关前端契约测试、必要后端精确测试、`git diff --check` 均须通过；不得在 Task09 运行全量回归。

## 子代理允许修改文件

| 角色 | 允许修改 | 禁止 |
|---|---|---|
| backend-dev | `backend/app/memory/repository.py`、`backend/app/memory/models.py`（如计算字段承载需要）、`backend/app/api/routes_conversations.py` 及相应精确测试 | schema、记忆/RAG/项目删除语义、第二套会话 API |
| frontend-dev | `frontend/index.html`、`frontend/app.js`、`frontend/styles.css` 及 Task09 前端契约测试 | `backend/**`、移动端范围、Task05 处理过程/记忆结果行为 |
| reviewers/testers | 仅各自评审或测试报告；测试可新增最小定向用例 | 业务实现文件 |

## 评审记录

- 角色：架构师/开发主管（临时 Terra medium；仅文档评审）。
- 结论：**GO**。
- 时间：2026-09-11。
