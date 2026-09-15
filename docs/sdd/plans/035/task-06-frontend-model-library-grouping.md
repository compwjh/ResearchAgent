> 关联：[spec-035](../../specs/035-online-model-provider.md) ｜ 索引：[README](./README.md)
> 依赖：任务 04；当前状态：`待执行`

## 1. 状态与一句话目标

`待执行`。模型库按「端侧模型 / 线上模型」两组展示，模型下拉按 `optgroup` 分组，并在打开页面/模型库时调用一次 `/api/models?probe=1` 获取状态。

## 2. 背景与前置条件

- 渲染主函数 `renderModelList(models, current)`（`frontend/app.js:4064-4118`）是**纯扁平循环**，无分组/排序/筛选。
- 数据流：页面加载时 `fetch('/api/health')`（`app.js:234-255`）→ `currentModels` 全局缓存 → `renderModelList()` / `refreshModelOptions()`（`app.js:3957`） / `refreshKbModelOptions()`（`app.js:4217`）。
- `showView('models')`（`app.js:3689-3721`）**不触发任何加载**，切到模型库不会刷新。
- 现有 DOM：`#models-view` / `#model-list` / `#model-empty` / `#model-count`；卡片 class `.model-item` / `.model-text` / `.model-name` / `.model-real` / `.model-edit` / `.model-badge`。
- 静态资源带版本号：`index.html:8` `styles.css?v=43`、`index.html:518` `app.js?v=43`。

## 3. 数据、配置与接口

消费 `GET /api/models?probe=1`（结构见 spec 035）。新增 DOM 契约（需与 CSS 选择器**交叉核对**，禁止凭记忆书写）：

| 新增 class | 用途 |
|---|---|
| `.model-group` | 分组容器 |
| `.model-group-title` | 分组标题（「端侧模型」/「线上模型」） |
| `.model-badge.online` | 线上模型标识 |
| `.model-badge.failed` | 连接失败标识 |

下拉改用 `<optgroup label="端侧模型">` / `<optgroup label="线上模型">`，`option.value` **仍为真实 id**。

## 4. 实施步骤与文件边界

| 顺序 | 文件 | 改动 |
|---|---|---|
| 1 | `frontend/app.js` | 新增/改造分组渲染；`refreshModelOptions()` / `refreshKbModelOptions()` 改 `optgroup`；打开模型库时触发一次 `fetch('/api/models?probe=1')` |
| 2 | `frontend/index.html` | **静态资源版本号递增**（原 `?v=43` → 实装时 `?v=44`；后因 spec-036 并行改动同一文件，实际落为 **`?v=45`**）。**以 `index.html` 实际值为准**，不要照抄本表的数字 |
| 3 | `frontend/styles.css` | 新增分组标题与状态徽标样式，选择器带 `#models-view` 前缀隔离 |
| 4 | `tests/test_frontend_model_library_contract.py`（**新建**） | 静态契约：分组容器、optgroup、版本号、无 innerHTML |

**强制约束（违反即打回）**：

- **XSS**：所有展示名用 `textContent`，**禁止 `innerHTML`** 拼接模型名。
- **版本号同步**：改 `app.js` / `styles.css` 后必须升 `index.html` 的 `?v=N`，并同步 `tests/test_frontend_management_contract.py:68-69` 里**硬编码的版本号断言**（否则旧断言失败）。
- 别名（spec-008 `localStorage["model_aliases"]`）对线上模型同样生效，`value` 仍为真实 id。
- 编辑别名按钮的 `click`/`keydown` 必须 `event.stopPropagation()`（既有约束，不得回归）。

## 5. 子代理分派

| 项 | 内容 |
|---|---|
| 角色 | `frontend-dev`（`Deepseek-V4.1-Flash`） |
| 最小上下文 | 本 task 文件 + `app.js:4064-4118` 原文 + `app.js:234-255` 原文 + `index.html:8,518` 两行 |
| 单次文件范围 | **只改 `frontend/**`**，禁止碰任何 `.py` |
| 回传后读回校验 | 架构师 `node --check frontend/app.js`、核对 JS 输出的 class 与 CSS 选择器逐一对应、确认版本号已升 |

## 6. 边界与明确不做

- 边界：无线上模型（只显示端侧组，形态与改动前一致）、线上组为空、Ollama 不可达、探测中（loading）、连接失败、当前模型是线上模型、别名已设/未设。
- 明确不做：不做搜索/排序/筛选；不在 UI 填 Key；不做失败重试按钮；不改 `/api/health` 消费逻辑（新增独立 fetch）；不补端侧模型的 size/参数量展示。

## 7. 验收、风险与回滚

验收：

```bash
node --check frontend/app.js
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_frontend_model_library_contract.py tests/test_frontend_management_contract.py --basetemp=/tmp/s035t06 -q
```

- 新契约测试全绿，`test_frontend_management_contract.py` 版本号断言已同步、无回归。
- 风险：只改前端，本任务**不跑后端 pytest**（按 `AGENTS.md` 单端改动原则）。
- 回滚：回退三个前端文件即可，后端不受影响。

## 8. 产出物、执行结果与变更日志

待执行后填写。
