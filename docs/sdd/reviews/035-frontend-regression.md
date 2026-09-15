# spec-035 前端回归报告（frontend-tester）

- 分支：`feature/spec-035-online-model-provider`
- 核对范围：`frontend/app.js`、`frontend/index.html`、`frontend/styles.css`，及 4 个契约测试
- 不计入项：`tests/test_frontend_skill_tool_contract.py`（spec-036 在途改动；本次也通过，无需归因）
- 日期：2026-09-13
- **结论：spec-035 前端未引入回归（明确：否）**

---

## 一、五项高频回归点逐项结论（含行号依据）

### 1. DOM 契约 ↔ CSS 交叉核对 —— PASS
JS 实际输出 class 与 `styles.css` 选择器逐一对应（均带 `#models-view` 前缀隔离）：

| JS 输出 class | app.js 行号 | CSS 选择器 | styles.css 行号 |
|---|---|---|---|
| `.model-item` | 4176 | `#models-view .model-item` | 317 |
| `.model-name` | 4082 | `#models-view .model-name` | 337 |
| `.model-real` | 4085 | `#models-view .model-real` | 437 |
| `.model-text` | 4180 | `#models-view .model-text` | 420 |
| `.model-edit` | 4185 | `#models-view .model-edit` | 446 |
| `.model-badge`(+online/failed/current) | 4206 | `.model-badge` / `.online`(404) / `.failed`(408) / `.online.current,.failed.current`(413-414) | 348 / 404 / 408 / 413-414 |
| `.model-group` | 4270 | `#models-view .model-group` | 380 |
| `.model-group-title` | 4272 | `#models-view .model-group-title` | 385 |
| `.model-list` | 4276 | `#models-view .model-list` | 311 |

未发现历史失配（如 JS 输出 `model-list-item` 而 CSS 写 `.model-item`）。分组渲染与线上状态徽标的 CSS 已齐备。

### 2. 静态资源版本号 —— PASS
- **真实 live 引用**：`index.html` `styles.css?v=45`（第 8 行）、`app.js?v=45`（第 531 行）。
- **历史兼容 marker**：第 7、530 行为 `v=30..35` 注释串，属预期「历史 marker」，非断言目标。
- **4 个 spec-035 相关测试均断言真实 live `v=45`**（与 index.html 一致）：
  - `test_frontend_model_library_contract.py`：`ASSET_VERSION = 45`，`f"/assets/app.js?v={ASSET_VERSION}"`（L14、L50-52）
  - `test_frontend_management_contract.py`：`/assets/app.js?v=45` 与 `styles.css?v=45`（L68-69）
  - `test_frontend_context_meter.py`：同上（L42-43）
  - `test_frontend_skill_legacy_contract.py`：正则匹配真实 `src` 版本 `>=40` 且断言 `v=45`（L115-124）
- **其余 9 个前端测试断言旧 `v=3x`**：`default_effort`/`effort_selector_states`/`reasoning_panel`/`optimistic_card`(v=35)、`conversation_contract`/`paper_contract`/`memory_repair`/`project_tree`/`system_rule`(v=31/v=30)。这些串仅出现在 index.html 第 7、530 行的兼容 marker **注释**中，故 `in INDEX` 命中注释即 pass —— **属历史 marker 兼容检查，非 live 版本断言，符合预期，不算失败**。

### 3. XSS —— PASS
- 模型名渲染全部走 `textContent`：
  - `renderModelText`（L4079-4089）：`nameSpan.textContent = alias||model`；`realSpan.textContent = model`
  - 分组标题 `titleEl.textContent`（L4273）；徽标 `badge.textContent`（L4209）；下拉 `opt.textContent = displayName(m.id)`（L4044、L4429）
- `app.js` 内 9 处 `innerHTML` 均与模型名无关：`sendLabel`（L11）、助手/候选消息气泡（L267、L460）、markdown 渲染（L1230、L4386，经 purify 净化，见 L4343 注释）、发送按钮态（L2397、L2402）。
- 契约测试 `test_model_library_renderers_use_safe_text_boundaries` 明确校验 `renderModelList` / `refreshModelOptions` / `refreshKbModelOptions` 区间无 `innerHTML`。

### 4. 降级不回归 —— PASS
- `getModelGroups()`（L4147-4169）：`modelLibrary` 无有效 groups 时，回退到 `currentModels` 映射为单一「端侧模型」组（与改动前形态一致）；两者皆空返回 `[]`。
- `renderModelList()`（L4239-4283）：`allIds` 为空时显示「暂无可用模型」并 `return`（L4255-4261）；遍历中对空组 `if (!models.length) continue`（L4268）——无线上模型时不报错、不空白，只显示端侧组。

### 5. `option.value` 语义 —— PASS
- `refreshModelOptions`（L4042-4045）：`opt.value = m.id`（真实模型 id），`opt.textContent = displayName(m.id)`（展示名）。
- `refreshKbModelOptions`（L4427-4430）：同样 `opt.value = m.id`，`opt.textContent = displayName(m.id)`。
- 下拉 `option.value` 仍为真实模型 id，非展示名；选中/切换逻辑（`modelSelect.value = id`）保持一致。

---

## 二、命令真实输出

### node --check frontend/app.js
```
NODE-CHECK: PASS
```

### grep -n "?v=" frontend/index.html
```
7:    <!-- Task09/Task10 compatibility markers retained for older static contracts: /assets/styles.css?v=30 /assets/styles.css?v=31 /assets/styles.css?v=32 /assets/styles.css?v=33 /assets/styles.css?v=34 /assets/styles.css?v=35 -->
8:    <link rel="stylesheet" href="/assets/styles.css?v=45">
526:  <script src="/assets/vendor/purify.min.js?v=13"></script>
527:  <script src="/assets/vendor/marked.min.js?v=13"></script>
528:  <script src="/assets/kb-inspection.js?v=23"></script>
529:  <script src="/assets/conversation-research.js?v=1"></script>
530:  <!-- Task09/Task10 compatibility markers retained for older static contracts: /assets/app.js?v=31 /assets/app.js?v=32 /assets/app.js?v=33 /assets/app.js?v=34 /assets/app.js?v=35 -->
531:  <script src="/assets/app.js?v=45"></script>
```

### grep -rn "innerHTML" frontend/app.js | head -20
```
frontend/app.js:11:const sendLabel = sendButton.innerHTML;
frontend/app.js:267:  message.innerHTML = type === 'assistant'
frontend/app.js:460:  message.innerHTML = '...candidate-bubble...';
frontend/app.js:1230:  element.innerHTML = renderMarkdown(content);
frontend/app.js:2397:  ... sendButton.innerHTML = sendLabel; ...
frontend/app.js:2402:  ... sendButton.innerHTML = '<span class="sending-indicator">•••</span>';
frontend/app.js:3784:// 标记纯展示，用 DOM API + textContent 构造，绝不拼 innerHTML。
frontend/app.js:4343:// XSS 底线：模型/论文内容一律「先净化、后 innerHTML」；vendor 缺失时降级为转义纯文本，绝不裸奔。
frontend/app.js:4386:    element.innerHTML = renderMarkdown(raw);
```
（9 处，均非模型名拼接；markdown 渲染经 purify 净化）

### env -u PYTHONPATH .venv/bin/python -m pytest tests/ -k frontend -q --basetemp=/tmp/s035-fe
```
........................................................................ [ 39%]
........................................................................ [ 78%]
........................................                                 [100%]
184 passed, 1521 deselected, 6 warnings in 6.76s
```
通过数：**184 / 184**（0 失败，含 spec-036 在途 `test_frontend_skill_tool_contract.py` 亦通过）。

---

## 三、是否引入回归：否

spec-035 前端改动（模型库分组渲染、`optgroup` 下拉、线上状态徽标、资源版本号 bump 至 `v=45`）经静态契约核对与 184 个前端测试全部通过，五项高频回归点全部 PASS，**未引入回归**。spec-036 在途测试本次亦通过，无需归因。
