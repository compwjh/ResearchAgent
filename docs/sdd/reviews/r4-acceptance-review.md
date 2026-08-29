# 验收评审：spec-008 R4「重名别名去重提示」

## 结论：通过

R4 为 spec-008 v2 的功能增强（行内编辑时的重名检测与提示），新增验收点 A1-A9 全部通过。前端静态资源 v=5 已上线，无阻塞性缺陷。

## 逐项判定表

| 验收点 | 状态 | 依据（文件：行号 或 关键片段） |
| :--- | :--- | :--- |
| **A1 功能正确性**：模型 A 设别名 X，再给模型 B 设相同别名 X 时，B 弹出重名提示且不立即保存（编辑态保留） | 通过 | `app.js:389-394`：<br>`const conflict = findAliasConflict(model, input.value);`<br>`if (conflict) { showWarning(true); return; }`<br>返回时未置 `saved`，等待用户改别名或 Esc，保留编辑态 |
| **A2 排除自身**：给同一模型改别名（与原不同）不应误报重名 | 通过 | `app.js:344`：<br>`for (const key of Object.keys(aliases)) { if (key === model) continue; ... }`<br>循环跳过当前 model，不会与自身比对 |
| **A3 空值/trim**：空别名、全空格、首尾空格不触发重名 | 通过 | `app.js:340-341`：<br>`const v = (alias \\|\\| '').trim();`<br>`if (!v) return null;`<br>先 trim 再比对，空或全空格视为无别名（回退真实名） |
| **A4 事件隔离**：点击提示或输入框不误触发卡片"切换当前模型"；提示文字点击把焦点拉回输入框 | 通过 | `app.js:378-381` warning click 事件：<br>`event.stopPropagation(); input.focus();`<br>`app.js:403-406` input click/keydown 均 `stopPropagation()`<br>`app.js:453-468` 切换模型仅 `<li>` click，编辑态隔离路径覆盖 |
| **A5 XSS 安全**：提示文案与别名输入全程用 textContent/createElement，无 innerHTML 拼接用户输入 | 通过 | `app.js:373-375`：<br>`const warning = document.createElement('span');`<br>`warning.textContent = '已有其它模型使用此别名';`<br>无 user input 进入 innerHTML；input.value 仅展示，未注入 DOM 内容 |
| **A6 DOM 契约**：新增 .alias-input/.alias-warn 在 CSS 中确有对应规则，且 CSS 带 #models-view 前缀隔离 | 通过 | `styles.css:154-183`：<br>`#models-view .alias-input { ... }`<br>`#models-view .alias-warn { ... }`<br>选择器完整一致（7/7），无 v1 的 model-list-item 错配 |
| **A7 版本号**：若改了 app.js/styles.css，index.html 的 ?v= 已同步升级（v4→v5） | 通过 | `index.html:7,88`：<br>`styles.css?v=5`<br>`app.js?v=5`<br>两处均 v=5，与改动同步 |
| **A8 静态资源生效**：服务启动后 curl /assets/app.js?v=5 \| grep -c findAliasConflict 命中，确认新版本已部署 | 通过 | `curl .../app.js?v=5 \| grep -c findAliasConflict` → 2<br>新版本含重名检测逻辑，v=5 已上线 |
| **A9 回归**：未改动后端、未改动 activeModel 语义、未扩大范围 | 通过 | `app.js:398-401`：<br>`if (commit) setAlias(model, input.value); renderModelText(...)`<br>`modelSelect.value = name`（真实名）仍保持；`activeModel` 始终为真实模型名 |

## 风险与建议

无新发现不阻塞缺陷。历史风险 R1-R3 已在 v2 验收报告（008-acceptance-review.md）中修复：
- **R1** 隐私模式降级为内存 Map —— 已落实 `memoryAliases`
- **R2** ✎ 可见性偏低 —— 默认 opacity: .45 + hover/focus-within 高亮
- **R3** DOM 清理方式 —— 改用 `replaceChildren()`

R4（本次新增）不引入历史风险。

## 开发主管签字

（由开发主管填写；本 agent 留空待签）
