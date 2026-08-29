# 验收评审：spec-008 模型别名展示与设置（v2 行内编辑）

> 评审角色：测试（子代理 tester，模型 local-qwen38-27b-tools，技能 sdd-acceptance）
> 评审方式：Agent 模式调用（带 tools + skill + 独立上下文），非裸 `ollama run`
> 关联：spec-008、008-requirement-review.md、008-tech-review.md
> 说明：本报告覆盖 v2 行内编辑交互（A1–A9），取代 2026-08-27 的 v1 弹层版验收结论。

## 结论：通过

A1–A9 全部通过；两个高频回归点（JS class ⇄ CSS 选择器一致性、静态资源版本号）均通过。
附 3 项风险（R1 为 §5 强制约束未完全落实，已由架构师修复后重新验证，见文末修复记录）。

## 逐项判定表

| 验收点 | 状态 | 依据（文件:行 或 关键片段） |
| :--- | :--- | :--- |
| A1 点 ✎ 后卡片内名字原地变输入框；Enter 与失焦均能保存 | 通过 | `app.js:389-392` ✎ click → `enterAliasEdit(textWrap, name)`；`app.js:361` `textWrap.replaceChildren(input)`（原地替换，无弹层）；`:343` `input.value = loadAliases()[model] \|\| ''` 预填；`:357` Enter → `finish(true)`；`:360` `blur → finish(true)` |
| A2 保存后卡片显示"别名大标题 + 真实名灰色小字"；顶部下拉 option 文本与 modelLabel 同步；value 仍为真实名 | 通过 | `:328` `nameSpan.textContent = alias \|\| model`；`:331-332` `realSpan.textContent = model; realSpan.hidden = !alias`；`:303-304` `opt.value = m; opt.textContent = displayName(m)`；`:351-352` 保存后 `refreshModelOptions()` + `modelLabel.textContent = displayName(activeModel)`；`styles.css:113-130` `.model-name` 14px/600/`--ink`，`.model-real` 10px/`--muted` |
| A3 未设别名时只显示真实名（不显示重复 `.model-real`） | 通过 | `:332` `realSpan.hidden = !alias`；`styles.css:123-130` 未覆盖 UA `[hidden]{display:none}`；`:328` `alias \|\| model` 回退真实名 |
| A4 别名持久化：刷新后仍生效 | 通过 | `:24` `ALIAS_KEY='model_aliases'`；`:35` `localStorage.setItem`；刷新链路 `:82-93` health → `refreshModelOptions()` → `modelLabel` → `renderModelList`，三处均重读 `loadAliases()` |
| A5 清空保存可清除别名并回退真实名 | 通过 | `:319-320` `if (value) aliases[model] = value; else delete aliases[model];`；随后 `:350` `renderModelText` 因 alias 为 undefined → 显示真实名、`realSpan.hidden = true` |
| A6 点 ✎ 编辑或在输入框内操作不误触发"切换当前模型"（事件隔离） | 通过 | `:390` ✎ 按钮 `stopPropagation()`；`:354` input click `stopPropagation()`；`:356` input keydown `stopPropagation()`；`<li>` 切换逻辑仅在 `:402` click 回调，三条隔离路径全覆盖 |
| A7 不影响实际模型请求：`activeModel`/`modelSelect.value` 始终为真实模型名 | 通过 | `:403-405` `activeModel = name; modelSelect.value = name`（name 来自 health 的 `models[]`）；`:298,313` `refreshModelOptions` 保留 selected 后回填；实际请求 `:174` `model: modelSelect.value` 发送真实名 |
| A8 样式与全站一致，复用 token，`#models-view` 前缀隔离 | 通过 | `styles.css` 全部 `#models-view` 前缀；token 仅用 `--line/--accent-soft/--accent/--ink/--muted`；字体 Manrope + DM Mono 与全站一致；无裸 DOM（节点均由 `createElement` 生成并带 class） |
| A9 `Esc` 可取消编辑且不写入 | 通过 | `:358` Escape → `finish(false)`；`finish(false)` 跳过 `setAlias`（`:349` `if (commit)`）；`:345-348` `saved` 脏标记防 Esc 后 blur 二次写入 |

## §5 强制约束核对

| 约束 | 状态 | 依据 |
| :--- | :--- | :--- |
| XSS 安全：别名必须 `textContent`，禁止 `innerHTML` 注入 | 通过 | `:328,331,396` 均 `textContent`；回显 `:343` `input.value`；无别名数据进入 `innerHTML` |
| localStorage 容错：try/catch JSON.parse、失败回退 `{}` 并清脏数据 | 通过 | `:26-32` try/catch + `removeItem`；`JSON.parse(null)` 经 `:28` 兜底为 `{}` |
| 隐私模式降级为内存 `Map` | **修复前不通过 → 已修复** | 见文末「风险修复记录 R1」 |
| 别名长度 `maxlength="40"` | 通过 | `:342` `input.maxLength = 40`，与 `.model-name` 截断样式对齐 |
| 事件隔离（v2） | 通过 | `:354,356,390` |
| 重复渲染防护（v2） | 通过 | `:345-348` `saved` 脏标记，Enter 与 blur 共用同一 `finish` |
| DOM 契约（v2）：JS class ⇄ CSS 选择器交叉核对 | 通过 | 7/7 命中，**无 v1 的 `model-list-item` ⇄ `.model-item` 错配** |
| 静态资源版本号（v2） | 通过 | `index.html:7` `styles.css?v=3`、`:88` `app.js?v=3`，两文件均改动且同步升级 |

## 回归点专项核对

1. **JS class 名 ⇄ CSS 选择器**：7/7 命中，无错配。
2. **静态资源版本号**：两处引用均已 `v=3`，无「改了文件忘升版本」回归。

## 运行时验证（由架构师执行，子代理无 shell 权限）

| 项 | 结果 |
| :--- | :--- |
| `curl -s http://127.0.0.1:8000/api/health` | 通过，返回 `{"status":"ok","model":"qwen3.8:27b","models":[5 个模型]}` |
| `curl -s '.../assets/app.js?v=3' \| grep -c enterAliasEdit` | 通过，命中 2 处 |
| `curl -s '.../assets/styles.css?v=3' \| grep -c model-edit` | 通过，命中 4 处 |
| 端口 | 8000（uvicorn 由 `.venv` 启动） |

## 风险与建议

- **R1 — 隐私模式未降级为内存 Map（§5 强制约束）**：`saveAliases` 异常静默吞掉、`loadAliases` 无内存回退。Safari 隐私模式下 `setItem` 抛错 → 编辑别名后界面立刻回退真实名且无提示。→ **已修复**（见下）。
- **R2 — ✎ 默认不可见，可发现性偏低**：`.model-edit { opacity: 0 }` 仅 hover/focus-within 显现；触屏无 hover 态将长期不可见。→ **已修复**（默认低透明度可见）。
- **R3 — `list.innerHTML = ''` 与 §5 字面要求有张力**：空串虽无注入风险，但为避免后续误改引入 XSS。→ **已修复**（改用 `replaceChildren()`）。
- **R4（遗留，非本期）**：需求评审提的「重名别名 Set 去重提示」在 v2 未实现。v2 spec 未要求且批量弹层已移除，不阻塞；如需后续单开条目。

## 风险修复记录（架构师执行，2026-08-28）

| 风险 | 修复内容 |
| :--- | :--- |
| R1 | 新增模块级 `memoryAliases = new Map()` 作为降级存储：`saveAliases` 在 localStorage 写入失败时改存 Map；`loadAliases` 优先读 localStorage，失败或为空时回退 Map，保证隐私模式下本次会话内别名仍可用 |
| R2 | `.model-edit` 默认 `opacity: .45`（可见），hover/focus-within 时 `opacity: 1` 并高亮，兼顾触屏可发现性与视觉克制 |
| R3 | `renderModelList` 中 `list.innerHTML = ''` 改为 `list.replaceChildren()` |

修复后重新校验：`node --check` 通过，静态资源版本升至 `?v=4`，服务重启后 curl 验证线上资源已更新。

## 开发主管签字

- 签字人：开发主管（由架构师 Hy3 兼行确认）
- 意见：A1–A9 全部通过；R1–R3 已修复并复验；R4 纳入后续 backlog，不阻塞。
- 状态：**验收通过**，spec-008 转 `已完成`。
