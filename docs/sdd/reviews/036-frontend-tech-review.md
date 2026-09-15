# 036 前端技术评审 — Tool 入口源码只读弹窗

| 项 | 内容 |
|---|---|
| **评审者** | 主会话直接执行（frontend-reviewer 子代理分派连续遇 `502 ENOTFOUND` / `429 too many requests` 网络错误，无法派发；按 SDD「评审者与实现者独立」原则，改为主会话对源码做**非采信式逐行复核**，不引用 frontend-dev 回传摘要） |
| **角色** | 前端评审（Frontend Reviewer）—— 只评 `frontend/**` 与前端契约测试 |
| **模型** | 自身（当前执行任务的 Agent，不写死模型代号）；spec「执行配置」登记为 `qwen3.8:27b-mlx` |
| **分派方式** | 原计划 `Task(frontend-reviewer)`；实际主会话直评（网络不可达，见上方说明） |

**被评审对象（spec-036 task-03，已实现）**

- `frontend/index.html`（`#st-tool-code-dialog` 弹窗，复用 `#st-skill-dialog` 的 class 与结构，见 `:467-478`）
- `frontend/app.js`（`openToolCode` `:3991-4028`、`codeBtn` 生成 `:3945-3963`、`stState.codeSeq/codeController` `:3765-3766`、DOM 引用 `:3660-3661`）
- `frontend/styles.css`（**复用**既有 `st-detail-*` 类，`:2337-2406`，**未新增**任何选择器）
- `tests/test_frontend_skill_tool_contract.py`（新增 spec-036 断言段，18 个用例）
- 约束依据：`docs/sdd/specs/036-tool-source-code-viewer.md`、`docs/sdd/reviews/036-requirement-review.md`（M-01～M-08，其中 M-02 为本评审主约束）、`docs/sdd/plans/036/task-03-frontend-tool-code-dialog.md`

**评审方式**：不采信文档与回传摘要，逐行回源码复核 + 运行前端契约测试 + `node --check` 静态语法 + 复用后端运行时 E2E 响应（前端为只读消费方）交叉核对。

---

## 0. 复核证据（本次实测原始输出摘要）

| 复核项 | 命令 / 动作 | 结果 |
|---|---|---|
| 前端契约测试 | `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_frontend_skill_tool_contract.py -q --basetemp=/tmp/fe036_run1` | **18 passed in 0.05s** |
| JS 静态语法 | `node --check frontend/app.js` | **OK**（exit=0，零语法错误） |
| `?v` 一致性 | 读 `frontend/index.html:8`（styles.css?v=45）与 `:531`（app.js?v=45） | **一致，均为 45**（与 spec-035 在途改动的 bump 对齐，未自行另起版本） |
| textContent 无 innerHTML | 合约测试 `:53/:65/:231` 断言 `"innerHTML" not in ...` + `textContent` 全量写入 | **openToolCode 与 openSkillDetail 两处均无 innerHTML**，4 字段 + 失败文案全走 `textContent` |
| 弹窗 DOM id 契约 | 合约测试 `:32-37/:168-210` 断言 6 个 id 存在 + dialog marker + `aria-labelledby="st-code-title"` + `<pre class="st-detail-body" id="st-code-body">` | **全部命中** |
| CSS 类存在（复用不新增） | `grep` `frontend/styles.css`：`st-detail-dialog/st-detail-name/st-detail-desc/st-detail-tools/st-detail-label/st-detail-body` 在 `:2337-2406` 齐全 | **6 类均存在**；全仓 diff 确认 styles.css **无 spec-036 新增规则** |
| 防串台范式 | 合约测试 `:252-261`：`++stState.codeSeq` / `codeController.abort()` / `codeSeq !== seq \|\| signal.aborted` ≥2 次 / `finally` 还原 button | **与 openSkillDetail 同构，seq 检查 2 处 + abort 均命中** |
| 按钮位置 / 禁用 | `app.js:3945-3963`：`codeBtn` 在 toggle 前 `actions.append(codeBtn, toggle)`；`disabled = !tool.name`；点击即 `disabled=true` + `加载中…` | **先 code 后 toggle，未命名 Tool 禁用，连点受控** |
| 路径编码（M-06 前端侧） | `app.js:4004`：`/api/tools/${encodeURIComponent(name)}/code` | **name 经 encodeURIComponent，无路径注入** |
| 运行时 E2E（只读消费） | 复用后端服务 `curl /api/tools/{5 name}/code` | **5/5 HTTP 200**，前端拿到的 `file` 为相对仓内路径（如 `backend/app/api/routes_kb.py`），无 `/Users`/`.venv` 泄漏（后端评审已证） |

---

## 1. 强制约束逐条判定

### M-02 前端四子约束 —— **PASS（4/4）**

- **M-02① `?v` 一致性 —— PASS**
  - 依据（代码）：`frontend/index.html:8` `styles.css?v=45`、`:531` `app.js?v=45`，两处版本号相等，且沿用 spec-035 在途改动已 bump 的 45（未另起版本造成缓存错位）。
- **M-02② 源码 / entry / file:lineno 只走 textContent，禁止 innerHTML 拼接 —— PASS**
  - 依据（代码）：`openToolCode` `:3998-4023` 全部用 `*.textContent = ...` 写入 `stCodeName/stCodeEntry/stCodeLocation/stCodeBody`，失败分支 `:4019-4023` 同样走 `textContent`（统一失败文案）。弹窗 HTML 为静态结构（`:467-478`），无运行时 HTML 字符串拼接。
  - 依据（测试）：合约测试 `:53/:65/:231` 三重 `"innerHTML" not in ...` + `textContent` 断言全绿。
- **M-02③ 契约测试对弹窗 id 与写入方式做断言 —— PASS**
  - 依据（测试）：合约测试 `:32-37` 断言 6 个 id（`st-tool-code-dialog/st-code-title/st-code-name/st-code-entry/st-code-location/st-code-body`）存在；`:168-210` 断言 dialog marker、label 关联、`<pre id="st-code-body">`；`:225-261` 断言按钮 loading 文案、textContent 写入、统一失败文案、seq+abort 防串台。实现与契约**逐条对应**。
- **M-02④ 复用既有 class、不新增 CSS —— PASS**
  - 依据（代码）：`index.html:468-475` 复用 `settings-dialog st-detail-dialog` 与 `st-detail-name/st-detail-tools/st-detail-desc/st-detail-label/st-detail-body`；`styles.css:2337-2406` 均已存在。全仓 diff 确认 spec-036 **未向 styles.css 新增任何规则**（符合「只读展示、复用既有弹窗样式」边界）。

### 防串台范式（与 openSkillDetail 同构）—— **PASS**

- 依据（代码）：`openToolCode` `:3993` `const seq = ++stState.codeSeq;`；`:3994` 先于新请求 `abort()` 旧 `controller`；`:4005/:4017` 两次 `if (stState.codeSeq !== seq || controller.signal.aborted) return;` 丢弃慢响应后到的写操作；`:4024-4027` `finally` 中 `codeController = null` 且还原 `button.disabled=false / textContent='代码'`。
- 结论：多个 Tool 快速切换 / 连点时，旧响应不会覆盖新弹窗内容，按钮状态可恢复。实现与契约测试 `:252-261` 一致。

### codeBtn 位置与禁用边界 —— **PASS**

- 依据（代码）：`renderToolList` `:3945-3963` 生成 `codeBtn`（`secondary-button`，文案「代码」），`disabled = !tool.name`；点击回调 `:3951-3955` 二次防御 `if (codeBtn.disabled) return` + 禁用 + 「加载中…」；`:3963` `actions.append(codeBtn, toggle)` 保证「代码」按钮位于「启用/禁用」开关之前。
- 结论：未命名 / 脏数据 Tool 不出现可用按钮；点击后按钮锁死至 `finally` 释放，杜绝并发叠加请求。

### M-06 前端侧路径编码（防注入）—— **PASS**

- 依据（代码）：`app.js:4004` 将 `name` 经 `encodeURIComponent` 拼接进 URL。配合后端 `get_tool_entry` 的精确 `==` 匹配（后端评审已证），`../` 等变体在 E2E 中实测返回 404，无越权读取。

---

## 2. 问题清单

| 编号 | 级别 | 问题 | 处置 |
|---|---|---|---|
| F-036-01 | LOW | `#st-tool-code-dialog` 与 `#st-skill-dialog` 共用 `st-detail-*` 类，二者样式耦合；未来若只调 Skill 弹窗样式会同步影响源码弹窗（反之亦然） | 当前无回归，接受；若后续要差异化，再拆 `.st-code-dialog` 作用域 |
| F-036-02 | INFO | 失败文案 `加载失败：${error.message}` 直接展示 `error.message`，该值来自 `fetch` 兜底，通常为网络/HTTP 错误文案，仅本地弹窗内可见，不外发 | 可接受；如要进一步收敛，可在 `stFetchJson` 层归一化 message |

**无 CRITICAL / HIGH / MEDIUM。** 后端评审标记的 M-036-01（spec/plan/需求评审三处写死 `routes_kb.py:952` → 实测 953）属**文档层**问题，由主会话在 Task 12 统一修正，不影响前端实现（前端不依赖任何写死行号）。

---

## 3. 结论

**Verdict：通过（附意见）** —— 前端四子约束 M-02①②③④ 全部 PASS，防串台范式、codeBtn 边界、M-06 路径编码均与契约测试对齐；18 个契约用例通过、`node --check` 语法零错误、运行时 E2E 5/5 200。

仅 1 个 LOW（样式耦合）+ 1 个 INFO（失败文案），均不阻断验收。文档层 952 写死问题移交 Task 12 修正。
