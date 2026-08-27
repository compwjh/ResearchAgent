# 005 前端候选展示限制与 Skill 选取提示

**状态：已完成**

## 一句话目标

在保留 Crossref / OpenAlex 元数据检索的前提下，规范前端的两条交互：①候选推荐**最多展示 3 项，且只展示相似度（candidate `confidence`）大于 50% 的推荐文章**；②当用户问题被意图识别为"下载论文"、对应 `download_paper` skill 被选定后，前端以**灰色文字**提示"已选取 download_paper 技能"，提示文案规范化。

## 设计要点

- **候选推荐限制（展示层规则）**：相似度指候选的 `confidence`（0–1）。仅 `confidence > 0.5` 的候选进入推荐；按 `confidence` 降序取**前 3 条**。后端在 `search` 与 `run` 两条链路中返回时即完成过滤与截断，前端按返回列表渲染（仍做兜底守卫）。
- **Skill 选取提示（意图驱动）**：先做意图识别；当 `intent == download_paper` 时，后端在 `intent` SSE 事件中附带被选中的 `skill` 名称（即 `download-paper`），前端据此渲染灰色提示。提示文案规范为：**"已选取 download_paper 技能，负责本次论文下载"**（文案可在确认时微调，须为灰色、非阻断、无需用户操作）。
- 该提示仅对 `download_paper` 意图出现；`chat` / `unsupported` 意图不展示。

## 数据模型

| 字段 | 类型 | 约束 |
|---|---|---|
| `candidate.confidence` | number | 0–1；仅 `> 0.5` 进入推荐 |
| 推荐条数 | integer | 最多 3，按 `confidence` 降序 |
| `intent_event.skill` | string | 当 `intent == download_paper` 时携带，值固定 `download-paper` |

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况（状态码） |
|---|---|---|---|
| `POST /api/agent/run` | `{ question, ... }` | SSE：`intent` 事件对 `download_paper` 附带 `skill`；`candidate` 事件仅发送 `confidence > 0.5` 的前 3 条 | 保持现有错误语义 |
| `POST /api/agent/articles/search` | `{ query, ... }` | 候选列表已过滤（`confidence > 0.5`）并截断（≤3） | 保持现有错误语义 |

## 边界（每条之后会变成一条测试）

- `confidence <= 0.5` 的候选**不得**出现在推荐中，即使总数不足 3 条。
- 满足 `confidence > 0.5` 的候选超过 3 条时，只展示相似度最高的 3 条。
- `chat` / `unsupported` 意图的 `intent` 事件**不得**携带 `skill`，前端不得展示 skill 提示。
- skill 提示必须为灰色、非阻断、无需点击；不改变既有候选选择 / 登录 / 下载流程。
- 前端对推荐列表做兜底：超过 3 条或含 `confidence <= 0.5` 时仅渲染合规部分。

## 明确不做

- 不改动元数据发现源（Crossref / OpenAlex 维持现状，属 004 范围）。- 不因展示限制而静默丢弃用户已明确选择的候选；限制只作用于"推荐展示"，已选定候选的下载流程不受影响。
- 不把 skill 提示用于 `chat` / `unsupported` 意图，不因此触发自动下载。

## 验证方式

- 单元测试 / API 测试：`search` 与 `run` 返回的候选均满足 `confidence > 0.5` 且数量 ≤ 3；`run` 的 `download_paper` 意图事件携带 `skill: "download-paper"`，`chat` 意图事件不带 `skill`。
- 前端测试：推荐区最多 3 项；`download_paper` 意图下出现灰色 skill 提示且文案正确；`chat` 意图下无该提示。
- 回归：现有 28 个测试继续通过；后端编译通过；前端 JavaScript 语法检查通过。
- 运行时验证：启动本地服务，发送一篇论文标题，确认仅展示 ≤3 条高相似候选，并在意图识别后前端显示灰色 skill 提示。

---

**三条自检**：①每条规则能不能写成测试？能。②人能在 2 分钟内审完吗？能。③范围划死了吗？能。

## 实施与验证（2026-08-26）

- 后端 `backend/app/api/routes.py`：新增 `RECOMMEND_MIN_CONFIDENCE = 0.5`、`RECOMMEND_MAX_COUNT = 3` 与 `top_recommendations()`（仅保留 `confidence > 0.5`、按降序截断前 3 条）；在 `search` 与 `run` 两条链路返回前均应用过滤；`intent` SSE 事件对 `download_paper` 意图附带 `skill="download-paper"`，其余意图不带。
- 前端 `frontend/app.js`：移除旧的无守卫 `candidate` 处理（此前使新守卫失效），改为单一守卫 `confidence > 0.5 && recommendedCount < 3`；新增 `showSkillHint(skill)`（渲染灰色提示"已选取 download_paper 技能，负责本次论文下载"）与 `clearSkillHint()`，在提交与新会话时重置；`intent` 事件携带 `skill` 时调用 `showSkillHint`。`frontend/index.html` 增加 `#skill-hint` 元素（默认 `hidden`），`frontend/styles.css` 增加 `.skill-hint`（灰字、非阻断、[hidden] 隐藏）样式。
- 新增/改写测试覆盖：候选过滤与截断、意图事件携 `skill`、skill-led 计划；全量 39 条测试通过。
- 运行时验证：真实搜索 `下载论文 Attention is all you need` 返回 3 条候选且 `confidence` 均 > 0.5（来源 Crossref，发现链路未受影响）；`/api/agent/run` 的 `intent` SSE 事件为 `{"intent":"download_paper","confidence":0.96,"skill":"download-paper"}`；前端 `app.js` 通过 `node --check` 语法校验。
