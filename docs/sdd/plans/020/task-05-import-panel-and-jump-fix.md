> 关联：[spec-020 零碎 bug 解决](../../specs/020-misc-bug-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`实施中`

# Task05 导入面板展示与跳转回归修复（BUG-03）

## 状态与一句话目标

`实施中`。修复"勾选 1 篇点击批量导入后**自动跳转**知识库、且该篇在导入进度面板**没有任何记录**"：移除自动跳转，把直达成功论文纳入面板展示，并保持批量路径逐条可见（含未完成项）。

## 背景与根因（含文件行号）

- `frontend/app.js:1042-1044`：`groups.size === 1 && candidate_ids.length === 1` 时请求体为 `{search_id, candidate_id}` → 后端 `backend/app/api/routes_paper.py:725-730` 走 `_import_single_paper`，返回 **`paper_id` 而非 `batch_id`**。
- `frontend/app.js:1049-1052` 的 `directSuccess` 分支：`paperState.directSuccess += 1` 后**无条件** `jumpToKnowledgeBase(data.paper_id)`；`jumpToKnowledgeBase`（`app.js:1203-1210`）内部 `showView('kb')` 隐藏 `#papers-view` → 面板连同论文信息一起消失（用户体感"自动跳转"）。
- 同一分支**从不调用 `renderPaperBatch`** → 该篇在面板无渲染入口，只剩汇总计数（"没了导入论文的信息"）。
- 该行为**非 BUG-01 引入**：`git diff 60e71f3~1 60e71f3 -- frontend/app.js` 未触碰 1051 行；BUG-01 打通即时反馈后此路径才被暴露。
- 已确认事实：`paperImportItems.replaceChildren()` 在全文件**不存在**，面板不会被整体清空；`paperState.candidateById` 在 `app.js:777` 已填充，可用 `candidateById.get(id)?.title` 取标题。

## 实施步骤与文件边界

**文件边界**：只改 `frontend/app.js`、`frontend/index.html`、`tests/test_frontend_paper_contract.py`。**不改 `backend/**`**。

### 1. `frontend/app.js`

**(a)** `paperState`（约 391 行）新增字段，紧邻 `directSuccess: 0,`：

```js
  directImports: [],
```

**(b)** `importPaperCandidates`（约 1023 行）在 `paperState.directSuccess = 0;` 旁重置：

```js
  paperState.directImports = [];
```

**(c)** 替换 directSuccess 分支（约 1049-1052 行）。**原代码**：

```js
      } else {
        paperState.directSuccess += 1;
        if (data.paper_id) jumpToKnowledgeBase(data.paper_id);
      }
```

**改为**（**删除 `jumpToKnowledgeBase` 调用，这是 BUG-03 核心**）：

```js
      } else {
        paperState.directSuccess += 1;
        if (data.paper_id || data.stored_name) {
          paperState.directImports.push({
            candidate_id: candidate_ids[0],
            paper_id: data.paper_id || null,
            stored_name: data.stored_name || '',
            existing: Boolean(data.existing),
          });
        }
      }
```

**(d)** 循环结束后（约 1059 行 `if (created.length) schedulePaperBatchPoll();` 之后）加一行，位于 `renderImportSummary();` 之前：

```js
  renderDirectImports();
```

**(e)** 新增函数 `renderDirectImports()`，放在 `renderPaperBatch` 之后、`selectPaperConference` 之前：

```js
function renderDirectImports() {
  if (!paperImportPanel || !paperImportItems) return;
  const existing = [...paperImportItems.children].find((node) => node.dataset.direct === '1');
  if (!paperState.directImports.length) {
    if (existing) existing.remove();
    return;
  }
  paperImportPanel.hidden = false;
  const container = existing || document.createElement('li');
  container.className = 'paper-import-batch';
  container.dataset.direct = '1';
  if (!existing) paperImportItems.appendChild(container);
  container.replaceChildren();
  const header = document.createElement('div'); header.className = 'paper-import-batch-header';
  const heading = document.createElement('h3'); heading.textContent = '直接导入';
  const count = document.createElement('span'); count.textContent = `${paperState.directImports.length} 篇已完成`;
  header.append(heading, count); container.appendChild(header);
  const list = document.createElement('ul'); list.className = 'paper-import-items';
  paperState.directImports.forEach((item) => {
    const row = document.createElement('li'); row.className = 'paper-import-item';
    const title = document.createElement('span'); title.className = 'paper-import-item-title';
    title.textContent = paperText(paperState.candidateById.get(item.candidate_id)?.title, item.stored_name || '未命名论文');
    row.appendChild(title);
    const state = document.createElement('span'); state.textContent = item.existing ? '已在知识库' : '已完成';
    row.appendChild(state);
    if (item.paper_id) {
      const jump = document.createElement('button'); jump.type = 'button'; jump.className = 'secondary-button';
      jump.textContent = '在知识库中查看';
      jump.addEventListener('click', () => jumpToKnowledgeBase(item.paper_id));
      row.appendChild(jump);
    }
    list.appendChild(row);
  });
  container.appendChild(list);
}
```

约束：

- 复用既有 class `paper-import-batch` / `paper-import-batch-header` / `paper-import-items` / `paper-import-item` / `paper-import-item-title` / `secondary-button`，**不新增 CSS class、不新增/更名 DOM id**（用 `data-direct="1"` 标记）。
- **不得伪造批次号**（此路径无 `batch_id`，标题只写"直接导入"）。
- 该容器为终态，**不加** `is-progressing`。
- 只用 `textContent` 与 DOM API，**禁止 `innerHTML`**。

### 2. `frontend/index.html`

`?v=21` → `?v=22`（`app.js` 与 `styles.css` 两处同步）。

### 3. `tests/test_frontend_paper_contract.py`

- 版本断言 `?v=21` → `?v=22`（两处）。
- 新增 `test_paper_direct_success_does_not_auto_jump`：断言 `app.js` 中**不再存在** `if (data.paper_id) jumpToKnowledgeBase(` 自动跳转写法，且 `jumpToKnowledgeBase(` 只出现在点击回调中。
- 新增 `test_paper_direct_imports_rendered_in_panel`：断言 `app.js` 含 `directImports`、`renderDirectImports`，且 direct 容器渲染"在知识库中查看"按钮与"直接导入"标题。

## 子代理分派

- `frontend-dev`（hy3）：只产出 `frontend/app.js` 的增量改动（一次一个文件）。
- 完成后 `frontend-tester`（hy3）：`node --check`、DOM 契约与 `?v=N` 核对（只读）。
- 日志：`.codebuddy/agent-logs/spec-020/task-05/<role>/<时间戳>.md`。

## 边界与明确不做

- **不改后端任何文件**；不改 `_import_single_paper` / `_create_paper_import_batch` 响应语义。
- **不把单篇改走批量端点**（Q2(b) 未采纳；日后若要"每篇必有批次号"另行立项）。
- 不新增/更名现有 DOM id；不新增 CSS class。
- 不改 `jumpToKnowledgeBase` 函数本身（仅不再被自动调用）。
- 不顺手重构状态机其它部分；不动 `renderPaperBatch` 的既有逐条渲染逻辑。

## 验收、风险与回滚

- 验收：
  1. 单篇导入后**停留在论文检索视图**、不自动跳转，导入进度面板可见。
  2. direct 成功论文在面板可见（标题 + `已完成`/`已在知识库` + "在知识库中查看"按钮）。
  3. 点击"在知识库中查看"才跳转知识库并定位该论文。
  4. 多篇批量路径逐条展示含未完成/失败/等待登录，导入完成后已完成项与批次号仍保留。
  5. `node --check frontend/app.js` 通过；契约测试全绿。
- 风险：新增容器复用既有 class，可能与批次卡片视觉一致（可接受）；若 `directImports` 未重置会导致跨轮累积 → 已在 (b) 重置。
- 回滚：`git revert` 本任务提交（仅前端 + 测试）。

## 产出物、执行结果与变更日志

### 改动文件

- `frontend/app.js`：① `paperState` 新增 `directImports: []`；② `importPaperCandidates` 起始重置 `paperState.directImports = []`；③ **删除** directSuccess 分支的 `if (data.paper_id) jumpToKnowledgeBase(data.paper_id);` 自动跳转，改为把论文 push 进 `paperState.directImports`（记录 `candidate_id`/`paper_id`/`stored_name`/`existing`）；④ 循环结束后 `renderImportSummary()` 之前调用 `renderDirectImports()`；⑤ 新增 `renderDirectImports()`（渲染"直接导入"容器：标题 + `已完成`/`已在知识库` + "在知识库中查看"按钮，`data-direct="1"` 标记，终态不加 `is-progressing`）。
- `frontend/index.html`：`?v=21` → `?v=22`（`app.js` 与 `styles.css` 两处）。
- `tests/test_frontend_paper_contract.py`：版本断言 21→22；新增 `test_paper_direct_success_does_not_auto_jump`、`test_paper_direct_imports_rendered_in_panel`。

### 执行说明（与计划的偏差）

- 计划分派 `frontend-dev`（hy3）实现，但连续两次分派均返回 `Subagent execution failed (code=10006): Too Many Requests`（hy3 侧限流）。为避免阻塞，改由**主会话（架构师，hy4）按已锁定 spec 直接实现**，实现内容与任务文档 (a)~(e) 完全一致，随后补跑全部自测。

### 验收自检结果

- `node --check frontend/app.js`：通过（exit=0）。
- `.venv/bin/python -m pytest tests/test_frontend_paper_contract.py -q`：**13 passed**（原 11 条 + 新增 2 条）。
- 部署与运行时验证（端口 **8123**，原因：8000 被另一项目目录 `/Users/wjh/ResearchAgent` 的残留服务占用）：
  - `GET /api/health` → HTTP 200，`paper_discovery_enabled: true`。
  - 线上 `GET /` 返回 `app.js?v=22`、`styles.css?v=22`（版本号已生效，非缓存）。
  - 线上 `app.js` 校验：`function renderDirectImports` 存在（1 处）；`directImports` 出现 6 处；**旧自动跳转写法 0 处**；点击式 `jumpToKnowledgeBase(item.paper_id)` 保留 2 处。

### 三项强制自查

1. DOM 契约：未新增/更名 DOM id；未新增 CSS class，复用既有 `paper-import-batch`/`paper-import-batch-header`/`paper-import-items`/`paper-import-item`/`paper-import-item-title`/`secondary-button`（均已在 `styles.css` 存在）。
2. 资源版本号：`index.html` `?v=21`→`?v=22`（app.js、styles.css 均升），契约测试同步断言，线上返回已确认为 v22。
3. XSS：新增 `renderDirectImports` 全用 `textContent` 与 DOM API，无 `innerHTML`（契约测试已断言该函数体内 `innerHTML` 为 0）。

### 风险与边界

- 仅改 `frontend/**` 与前端契约测试，**未碰 `backend/**`**；后端 `_import_single_paper` / `_create_paper_import_batch` 两条路径零改动。
- 未把单篇改走批量端点（Q2(b) 未采纳）；未伪造 `batch_id`。
- `jumpToKnowledgeBase` 函数本身未改，仅不再被自动调用。
- 已确认 `paperImportItems.replaceChildren()` 全文件不存在，面板不会被整体清空，已完成项与批次号保留。
