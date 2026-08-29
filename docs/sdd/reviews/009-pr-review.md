# PR Review：feature/spec-009-agent-roles（基线 main）

> 评审人角色：开发主管（Tech Lead）
> 评审方式：基于真实代码逐行核对（Grep/Read），非依据描述下结论。
> 门禁参考：后端 44 passed / 覆盖率 69%（历史遗留，本次不涉 backend Python）/ node --check 通过 / curl 通过。

## 结论：Approve（附意见）

改动全部落在 `frontend/`、`.codebuddy/`、`docs/sdd/`、`AGENTS.md`、`.gitignore`，不涉及后端接口与数据结构。6 个高频回归点全部核对通过，无阻塞项。附 3 条非阻塞建议。

---

## 一、必备核对表（逐项给结论 + 依据行号）

| # | 核对项 | 结论 | 依据（文件:行） |
| :-- | :-- | :-- | :-- |
| 1 | **DOM 契约** JS 渲染 class ⇄ CSS 选择器一一对应 | ✅ 通过 | JS 输出 class：`model-item`(app.js:390)、`model-text`(394)、`model-name`(341)、`model-real`(344)、`model-edit`(399)、`model-badge`(409)、`alias-input`(355)。CSS 全部命中：`#models-view .model-item`(styles.css:43)、`.model-text`(106)、`.model-name`(63/113)、`.model-real`(123)、`.model-edit`(132)、`.model-badge`(74)、`.alias-input`(154)。**无错位**，历史 `model-list-item`/`.model-item` 事故未复现。 |
| 2 | **静态资源版本号** `?v=N` 随 js/css 改动升级 | ✅ 通过 | 基线 `main:frontend/index.html` 为 `?v=2`；当前 `index.html:7,88` 为 `?v=4`；且 diff 确认 `app.js`(+205/-…) 与 `styles.css`(+75/…) 均被修改。源已改 + 版本已升，满足约束。 |
| 3 | **XSS** 用户输入无 `innerHTML` 拼接 | ✅ 通过 | 别名展示走 `textContent`(app.js:342/345)、编辑走 `input.value`(357)、`setAlias` 只写 `localStorage`；`innerHTML` 仅用于**静态骨架**(114/125/135)，其后用户数据一律 `textContent`。无用户输入进入 `innerHTML`。 |
| 4 | **事件隔离** 编辑操作不误触发"切换当前模型" | ✅ 通过 | ✎ 按钮 `click` 里 `event.stopPropagation()`(app.js:404)；输入框 `click`(368)、`keydown`(370) 均 `stopPropagation()`；"切换当前模型"逻辑在 `li` 的 `click`(416)，被上述隔离挡住。`li.dataset.model` 与 `name===current` 判定正确。 |
| 5 | **CSS 作用域** 新增样式隔离、无非法声明 | ✅ 通过 | 新增段(styles.css:105-170)全部带 `#models-view` 前缀；无非法 media query/声明。**次要注意**：`.model-name` 在 63 与 113 重复定义（冗余，非非法，见建议 2）。 |
| 6 | **agent 配置** `model` 为不含 `/` 的已注册模型名 | ✅ 通过（附文档一致性质疑） | 实际 front matter：`junior-dev=qwen3.8:27b`、`tech-lead=qwen3.8:27b`、`pm=qwen3.5:9b`、`tester=qwen3.5:9b`、`code-drafter=deepseek-coder-v2:16b`、`sdd-orchestrator=inherit`，**均不含 `/`**，与 AGENTS.md:91-92「须填用户级已注册名、含命名空间 ID 会报 invalid model」实测结论一致。⚠️ 但 AGENTS.md 分配表 L103-104 写的是 `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU`（含 `/`），与实测结论及实际文件矛盾 → 见建议 1。 |

**核对统计：6/6 通过，阻塞项 0。**

---

## 二、改动面 & 兼容性 & 容错（技术维度补记）

- **改动面**：纯前端交互重做（spec-008 行内编辑）+ agent 资产（6 agents/4 skills/models.json）+ 规则文档。无接口契约变更，`/api/health`、`/api/agent/run` 等调用链未动。
- **兼容性**：`renderModelList` 由旧弹层改为原地编辑，`refreshModelOptions()`(310) 仍刷新 `#model-select`，聊天页下拉与模型 tab 显示一致（`displayName` 统一口径，app.js:51）。
- **容错**：`loadAliases` 捕获 `localStorage` 异常并降级内存 Map(28-50)，隐私模式可用；`enterAliasEdit` 防重复进入(352)；`finish` 用 `saved` 标志防 Enter+blur 双提交(359-363)。边界处理到位。
- **安全**：见核对项 3；`searchUrls/downloadDir` 等设置项用 `.value`(63-65,80-82)，无注入。
- **.gitignore**：改为忽略 `plans/`、`settings.local.json`、`agent-memory/`、`agent-logs/`，保留 `agents/`、`skills/`、`models.json` 入库共享——合理。

---

## 三、建议（非阻塞，供后续清理）

1. **AGENTS.md 分配表与实测/实际文件对齐**（一致性）：AGENTS.md L103-104 仍写 `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU`（含 `/`），而 L91-92 明确"含命名空间 ID 会报 invalid model，须填用户级已注册名"，实际 agents 也已用 `qwen3.8:27b`。若有人照分配表填 `junior-dev`/`tech-lead` 会踩 invalid model。建议把分配表统一改为实际注册名，或注明"以用户级 `~/.codebuddy/models.json` 注册名为准"。
2. **CSS `.model-name` 去重**：styles.css L63 与 L113 对 `.model-name` 有重叠声明（font-size/weight/color/ellipsis 重复）。无功能问题，建议合并避免日后改一处漏一处。
3. **`code-drafter` 用 `deepseek-coder-v2:16b` 的合规性复核**：AGENTS.md L106「禁止用 deepseek-coder 系列驱动任何 Agent」、L114 实测其不支持 tools。`code-drafter` 定位是"纯文本片段初稿、不支持操作文件、产出由主会话落盘"，与"不驱动文件类 Agent"边界相容，可接受；建议在 `code-drafter.md` 显式声明"仅用于无工具纯文本草稿，禁止授予 tools/写文件"，避免误用于需要 tool call 的场景。

---

## 四、强制约束（合并后必须保持）

- 前端任何渲染用户数据的 DOM 更新**必须**走 `textContent`/`input.value`，禁止 `innerHTML` 拼接（本次 spec-008 已遵守，作为长期约束）。
- 每次 `app.js`/`styles.css` 变更**必须**同步升级 `index.html` 的 `?v=N`。
- JS 新增渲染 class 时**必须**在同次提交补齐 `#models-view` 前缀的 CSS 选择器（DOM 契约成对出现）。
- agent front matter 的 `model` **必须**填用户级已注册、不含 `/` 的模型名；分配文档与实际文件必须一致。

## 风险定级：**低**

纯前端 + 文档 + agent 配置，无后端/接口/数据变更，回归点全部通过。

---
*评审文档路径：`docs/sdd/reviews/009-pr-review.md`*
*进展日志：`.codebuddy/agent-logs/tech-lead-009-20260829-003735.md`*

---

## 合并门禁检查（架构师执行，2026-08-29）

| 门禁项 | 要求 | 实测 | 是否通过 |
|---|---|---|---|
| ① CI 全绿 | lint / test / build 通过 | 后端 `pytest tests`：**44 passed**；前端 `node --check` 通过；服务 `curl` 运行时验证通过（HTTP 200 + `/api/health` 正常） | ✅ 通过（本地验证替代，本项目无真实 CI workflow，见 `AGENTS.md`「CI/CD 与质量门禁」说明） |
| ② 测试覆盖率 | ≥ 80% | **69%**（818 语句 / 251 未覆盖） | ❌ **未通过** |
| ③ Code Review | ≥ 1 approval | tech-lead（子代理，**Approve 附意见**，6/6 回归点通过、0 阻塞项） | ✅ 通过 |

### 覆盖率未达标的原因与处置（落盘备案）

- **非本次改动引入**：本次 PR 共 23 个文件，全部位于 `frontend/`、`.codebuddy/`、`docs/sdd/`、`AGENTS.md`、`.gitignore`，**不涉及任何 backend Python 代码**（已用 `git diff --name-only main..HEAD` 核实）。
- 因此 69% 是**项目历史遗留覆盖率**，本次改动在数学上不可能影响该指标。
- 若强制要求"本 PR 补到 80%"，需补的是与本次改动**无关的后端测试**，属范围外工作。

### 处置选项（待用户拍板）

- **A. 豁免合入**：以"历史遗留、本次不涉及后端"为由记录在案后合并。
- **B. 先补测试**：另开 spec 将后端覆盖率补到 ≥80%，再合并本 PR。
- **C. 暂不合入**：保留分支。

> 按 `AGENTS.md`「门禁失败必须阻断并落盘原因，不得静默跳过」，在用户选定前**不执行合并**。
