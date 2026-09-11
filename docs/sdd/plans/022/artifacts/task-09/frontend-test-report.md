# Task09 前端定向测试报告

## 命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | 通过 |
| `pytest -q tests/test_frontend_task09_project_tree_contract.py` | 0 | 5 passed |
| `git diff --check` | 0 | 通过 |

## 覆盖项

- 唯一项目树与旧下拉/常驻表单 DOM 删除。
- 项目内 10 条、最近会话 20 条分页；手风琴展开与空项目入口。
- 对话框、已有 active 项目移动选择、历史策略、PATCH 确认字段。
- overlay 菜单、viewport 定位、Escape/外点关闭与焦点恢复标记。
- `textContent` 动态内容边界、资源版本 `v=30`。

## 边界

未运行后端 pytest、全量回归或真实浏览器 smoke；这些属于 Task09 后续评审/验收角色职责。

## Reviewer 修复回归（2026-09-11）

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | 通过 |
| `pytest -q tests/test_frontend_task09_project_tree_contract.py tests/test_frontend_conversation_contract.py tests/test_frontend_task05_repair_contract.py tests/test_frontend_management_contract.py` | 0 | 36 passed |
| `node tests/test_frontend_conversation_research.js` | 0 | 通过 |
| `node tests/test_frontend_kb_inspection_interaction.js` | 0 | 通过 |
| `node tests/test_frontend_kb_inspection_pdf.js` | 0 | 通过 |
| `node tests/test_frontend_kb_inspection_renderer.js` | 0 | 通过 |
| `node tests/test_frontend_kb_inspection_runtime.js` | 0 | 通过 |
| `git diff --check -- frontend/index.html frontend/app.js frontend/styles.css tests/test_frontend_task09_project_tree_contract.py tests/test_frontend_conversation_contract.py tests/test_frontend_task05_repair_contract.py tests/test_frontend_management_contract.py` | 0 | 通过 |

新增合同覆盖 dialog 取消零请求、移动后目标高亮/缓存清理、删除项目上下文清理和归档过滤隔离。

最终复审 P2 回归新增断言：归档项目视图下移动 dialog 仍从独立 active 集合生成候选、排除当前项目、保留 `project_id` option value，并支持名称搜索。

## 接口状态范围适配回归（2026-09-11）

新增 Task09 合同断言：最近会话 active/unbound-only、项目子树 active、归档会话 archived 且不带 unbound-only；原有 P0/P1 合同继续保留。
