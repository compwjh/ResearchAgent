# spec-023 前端评审报告 — Skill 与 Tool 管理模块

- **评审角色**：frontend-reviewer
- **评审范围**：`frontend/**`（`index.html` / `app.js` / `styles.css`），证据取自 `tests/test_frontend_skill_tool_contract.py`、`tests/test_frontend_paper_contract.py`
- **明确不评**：`backend/**`（含 `routes_skills.py` / `routes_tools.py` / `backend/app/skills/`），归 backend-reviewer
- **评审依据**：spec-023（Q3 能力边界）、`.codebuddy/skills/{frontend-patterns,regression-guard,coding-standards}.md` 的 Project Addendum
- **评审方式**：只读；未修改任何代码
- **基线**：工作区未提交改动（`git diff` HEAD）

## 结论

**通过（Approve）**，P0 阻塞问题 **0 个**。

四项必守全部 PASS；XSS 最高优先级项在新代码中零 `innerHTML` 拼接。P1 均为健壮性/可用性改进建议，不阻塞合并。

## 四项必守逐条判定

| # | 必守项 | 判定 | 核对依据（grep 命令与命中行） |
|---|---|---|---|
| 1 | **DOM 契约**（JS class ↔ CSS 双向存在） | **PASS** | JS→CSS：`renderSkillList`/`renderToolList` 使用 `st-item`/`st-text`/`st-name`/`st-desc`/`st-tools`/`st-actions`（app.js:1505-1535、1591-1620），在 styles.css:1876/1893/1900/1907/1915/1922 全部存在。CSS→HTML：`st-workspace`/`st-section`/`st-section-head`/`st-status`/`st-list`/`st-empty`/`st-detail-label` 命中 index.html:300-324、336。**既有 DOM id 未被改动或重命名**：`git diff frontend/index.html` 的删除行仅一条（`app.js?v=25` → `?v=26`）；`grep -o 'id="[^"]*"' frontend/index.html \| sort \| uniq -d` 输出为空（无重复 id）。 |
| 2 | **版本号 `?v=N`** | **PASS** | `grep -n "?v=" frontend/index.html` → 第 7 行 `styles.css?v=26`、第 366 行 `app.js?v=26`；`git diff` 证实由 25 递增至 26，**两个文件都已同步递增**。`tests/test_frontend_paper_contract.py:91-92` 断言同步更新为 26。 |
| 3 | **XSS**（禁止 `innerHTML` 拼接） | **PASS** | `grep -n "innerHTML" frontend/app.js` 命中 10/118/129/139/188/248/293/1833/1876 行，**全部为既有聊天/markdown 链路**（第 1876 行注释声明「先净化、后 innerHTML」，走 `renderMarkdown`）。新增段落内 `innerHTML` **零命中**：`renderSkillList` 用 `name/desc/tools.textContent`（app.js:1511/1514/1519）、`renderToolList` 用 `name/desc.textContent`（app.js:1598/1601）、`openSkillDetail` 的 **Skill 正文走 `stDetailBody.textContent`**（app.js:1571），错误信息亦为 `textContent`（app.js:1552/1573/1587/1638）。`<pre>` 承载正文配合 CSS `white-space: pre-wrap`（styles.css:1977），无需 HTML 渲染。 |
| 4 | **CSS 作用域** | **PASS** | 新增选择器全部以 `#skill-tool-view `（styles.css:1830/1839/1849/1855/1860/1868/1876/1888/1893/1900/1907/1915/1922/1929/1990）或 `.st-detail-dialog `（styles.css:1937/1945/1953/1960/1968/1985/1991）为前缀，无裸全局标签选择器；`grep -n "!important" frontend/styles.css` **零命中**；全局 `.secondary-button` 原定义（styles.css:19）未被改写，仅在本视图内追加 `min-height`（styles.css:1990-1991），无全局污染。 |

## 功能完整性核对（对照 spec 端点表与 Q3）

| 需求 | 实现 | 依据 |
|---|---|---|
| Skill 列表（名称/描述/tools/启用态） | 有 | app.js:1505-1535；`tools.textContent` 拼接声明工具，空则「未声明工具」 |
| Skill 详情（含正文） | 有 | app.js:1559-1575；`GET /api/skills/{name}` 取 `body` |
| Tool 列表（名称/描述/启用态） | 有 | app.js:1591-1620 |
| 启停走 PATCH 且成功后刷新按钮态 | 有 | app.js:1544-1556、1627-1641；按后端返回 `data.enabled` 回写 `skill.enabled` / 按钮文案 |
| 启停失败有提示 | 有 | `stSkillStatus` / `stToolStatus` 文案（app.js:1552、1638） |
| 空态文案 | 有 | `#st-skill-empty`「还没有可用的 Skill。」index.html:311 + app.js:1502；`#st-tool-empty` 同理 index.html:324 + app.js:1588 |
| 加载中状态 | 有 | 「正在加载 Skill…」app.js:1484、1583；详情「加载中…」app.js:1564 |
| 错误态（加载失败） | 有 | app.js:1489-1493、1585-1590；`stJson` 统一解析 `{error_code,message}`（app.js:1434-1442） |
| **不提供新建/编辑/删除**（Q3） | **符合** | `grep` 新增段落仅调用 `GET /api/skills`、`GET /api/skills/{name}`、`PATCH /api/skills/{name}`、`GET /api/tools`、`PATCH /api/tools/{name}`（app.js:1485/1545/1567/1580/1631），无 POST/DELETE 新增，与 spec 端点表一一对应 |
| 不引入前端框架/构建 | 符合 | 纯原生 DOM API |

## 不回归核对

- `git diff frontend/index.html` 删除行仅版本号一行，既有 143 个 id 无一被删改；新增 id 全部以 `st-` 前缀且无重复。
- `showView()` 仅在既有分支后**追加** `if (stView) stView.hidden = ...`（app.js:1451）与 `skill-tool` 分支（app.js:1463-1466），未改动 chat/models/kb/papers 既有逻辑。
- 新增资源加载仅在进入 `skill-tool` 视图时触发（app.js:1463-1466），**不影响聊天默认行为**。
- `node --check frontend/app.js` → **通过**。
- `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python python -m pytest tests/test_frontend_skill_tool_contract.py tests/test_frontend_paper_contract.py -q` → **30 passed**。

## 问题清单

### P0（阻塞）— 0 个

无。

### P1（建议修复，不阻塞）

**P1-1 详情按钮缺少 in-flight 保护，存在并发请求竞态**
- 依据：`app.js:1527` `detailBtn` 未做 `disabled` 保护（对比同文件 toggle 按钮在 `toggleSkill`/`toggleTool` 中先 `button.disabled = true`，app.js:1539、1623）。
- 影响：连点「详情」会并发发出多个 `GET /api/skills/{name}`，若先发后回的响应较慢，`stDetailBody.textContent` 会被**旧请求结果覆盖**（stale write），展示与当前所选 Skill 不一致。虽为只读数据、无写副作用，仍属可见缺陷。
- 建议：为 `openSkillDetail` 引入请求序号/`AbortController`，仅当响应对应最新一次调用时才写入 DOM；或在请求期间禁用该按钮。

**P1-2 `stJson` 对网络异常未做兜底，错误提示可能暴露底层异常文本**
- 依据：`app.js:1434-1442` 仅处理 `response.ok === false`；`fetch` 抛出的网络错误（TypeError）会以 `error.message` 直接拼入状态文案（app.js:1491/1552/1573/1585/1638）。
- 影响：用户会看到形如「Failed to fetch」的原始异常文本；且四类错误共用同一文案模板，无法区分「网络不可达」与「后端 4xx/5xx」。
- 建议：`stJson` 或调用处区分 `TypeError`（网络）与业务错误，给用户可读的中文提示（如「无法连接本地服务，请确认后端已启动」）。

**P1-3 详情对话框请求失败时未回填描述与工具字段**
- 依据：`app.js:1573` 仅设置 `stDetailBody` 为「加载失败：…」，`stDetailDesc` / `stDetailTools` 停留在打开时清空的状态（app.js:1561-1562）。
- 影响：失败态下详情区出现「名称有值 + 描述/工具空白 + 正文报错」的割裂展示。
- 建议：catch 分支一并给出统一失败提示，或整体以错误态替换详情内容。

### P2（可选优化）

**P2-1 列表渲染每次整体重建 DOM，未复用节点**
- 依据：`renderSkillList`（app.js:1497）与 `renderToolList`（app.js:1586）均先 `replaceChildren()` 再全量重建；`showView` 切回视图时无条件重新 `loadSkills()`/`loadTools()`（app.js:1463-1466）。
- 影响：重复进入该视图会重复请求并重建全部 `<li>`，与 `paperState.conferencesLoaded` 的既有懒加载收敛做法（app.js:1462）不一致。当前数据量为 2 Skill + 若干 Tool，**性能影响可忽略**，仅为一致性建议。
- 建议：参照 papers 视图增加 `stState.loaded` 标记，避免重复拉取。

**P2-2 导航项缺失 `aria-controls` / `href`，与 papers 导航写法不一致**
- 依据：`index.html:20` 新导航项为 `<a class="nav-item" data-view="skill-tool" role="button" tabindex="0">`，未带 `aria-controls="skill-tool-view"`；而 papers 导航项（`index.html:19`）带 `href` + `aria-controls`。
- 影响：无障碍属性不完全对齐，功能无影响。
- 建议：补 `aria-controls="skill-tool-view"`。

**P2-3 新增代码无 `console.log` 调试残留（已确认良好），但缺 JSDoc**
- 依据：`grep -n "console.log" frontend/app.js` 在新增段落零命中（良好）；`stJson`/`loadSkills`/`openSkillDetail` 等未加注释说明契约。
- 建议：`stJson` 补一行说明后端错误体结构（现已在 app.js:1434 有注释，可保留）。

## 与 ECC Review Summary 对齐

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 3     | info   |
| LOW      | 3     | note   |

> 映射说明：本报告 P0↔CRITICAL，P1↔MEDIUM（无 HIGH/CRITICAL 项），P2↔LOW。

**Verdict：APPROVE — 无 CRITICAL/HIGH 问题。四项必守全部 PASS，可合并。P1 建议在后续迭代修复。**
