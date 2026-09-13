# Spec 036 实施计划索引

> 关联 spec：[036 Tool 模块查看内部 Python 代码](../../specs/036-tool-source-code-viewer.md)

## 目标

给「Skill 与 Tool」页面的 Tool 列表加一个**只读**的「代码」入口：点开任一 Tool，弹窗展示它在后端
真实执行的入口函数源码 + 仓库相对 `文件:行号`，让用户不必翻仓库就能审计 Tool 到底跑了什么。

## 任务顺序

| 编号 | 任务 | 角色 | 依赖 | 状态 |
|---|---|---|---|---|
| 02 | [后端：`GET /api/tools/{name}/code`](./task-02-backend-tool-code-api.md) | `backend-dev` | 01 | 已完成 |
| 03 | [前端：Tool「代码」按钮与弹窗](./task-03-frontend-tool-code-dialog.md) | `frontend-dev` | 02 | 已完成 |
| 04 | [评审、回归与端到端验收](./task-04-review-regression-acceptance.md) | 各评审/回归角色 + `tester` | 03 | 进行中 |

## 当前状态（2026-09-13）

- 需求评审已过（**通过（附意见）**，P0=0 / P1×4 已回填 / P2×5 / INFO×1），spec 已转 `已确认`。
- 任务 02/03 已实现，端到端实测：5 个 Tool 全部返回 200 与非空源码；
  未知名 / 点分路径 / 大小写变形一律 `TOOL_NOT_FOUND`；响应体与错误体均不含绝对路径。
- 服务已重启（新接口上线），前端 `?v` 已由 44 升到 45（原 43 被另一 agent 升过，以实际值为准）。
- 剩余：任务 04 的技术评审、定向回归与验收评审。

## 关键既有事实（实施前必读，避免重复扫描）

**后端**

- `backend/app/api/routes_tools.py`：既有 `GET /api/tools`、`GET /api/tools/{name}`、
  `PATCH /api/tools/{name}`；错误体统一用 `from backend.app.api.routes_kb import _document_error`，
  签名为 `_document_error(404, "TOOL_NOT_FOUND", "Tool 不存在", request=request)`。
- `backend/app/skills/models.py`：`ToolEntry(name, description, enabled, entry, parameters)`；
  `to_dict()` **只**返回 `{name, description, enabled}` —— **本 spec 不改这个结构**。
- `backend/app/skills/tool_service.py`：`ToolRegistryService` 的 `list_tools/get_tool/set_enabled`；
  注册项来自 `self._registry`（`ToolEntry` 列表，含 `entry`）。
- `backend/app/skills/registry.py`：`build_default_tool_registry()`，5 个 Tool 的 `entry` 均为
  `backend.app.*` 点分路径（含类方法 `X.Y`、模块函数、被装饰的路由函数 `kb_ask`）。

**前端**

- `frontend/index.html`：Tool 区在 `#skill-tool-view`，列表 `<ul id="st-tool-list">`；
  Skill 详情弹窗 `#st-skill-dialog`（class `settings-dialog st-detail-dialog`），正文用
  `<pre id="st-detail-body">`。
- `frontend/app.js`：`renderToolList()`（约 3903 行）渲染每一项 = `st-text`(名称+描述) + `st-actions`(启停按钮)；
  `openSkillDetail()`（约 3850 行）是**必须复用的范式** —— 自增 `stState.detailSeq` + `AbortController`
  丢弃过期响应，失败时 name/desc/body 统一展示同一失败文案。

## 架构师已实测的可行性前提（Go/No-Go 已通过）

`inspect` 能解析全部 5 个注册 entry，含被装饰的 `kb_ask`（`inspect` 自动 unwrap 到原始函数）：

| Tool | file:lineno | 行数 |
|---|---|---|
| `search_paper_catalog` | `backend/app/paper_discovery/application/paper_discovery_search.py:94` | 71 |
| `download_and_import_paper` | `backend/app/paper_discovery/application/paper_import.py:398` | 161 |
| `fetch_paper_detail` | `backend/app/paper_discovery/infrastructure/usenix_publication_source.py:994` | 61 |
| `kb_search` | `backend/app/knowledge_base/infrastructure/retrieve.py:139` | 112 |
| `kb_ask` | `backend/app/api/routes_kb.py:953` | 133 |

> 注：`file:lineno` 为当前工作树快照，会随其他在途改动漂移（如 spec-035 在 `routes_kb.py` 上方新增 import 后 `kb_ask` 装饰器行由 952→953）；验收以接口运行时返回值为准，禁止写死。

## 运行约定

- 后端 pytest：`env -u PYTHONPATH .venv/bin/python -m pytest <文件> -q --basetemp=/tmp/<每次新目录>`
  （不去 `PYTHONPATH` 会被 shim 污染；basetemp 必须每次换新目录；多文件易被 SIGTERM，按文件分批）。
- 前端静态核对：`node --check frontend/app.js`；前端契约 pytest 见 `tests/test_frontend_paper_contract.py`。
- 服务：健康检查是 `/api/health`（**不是** `/health`）；`deploy/stop.sh` 在沙箱内失效（内部用 `ps`），
  需 `lsof -nP -iTCP:8000 -sTCP:LISTEN` 取 PID 后 `kill -TERM` 并删 `deploy/run.pid`。
- 沙箱内 `find` 会被 SIGTERM（改用 Glob）；`grep "a\|b"` 交替匹配会静默返回空（改用 Grep 工具）。
- **不要跑全量回归**（用户既定要求），只跑定向。
