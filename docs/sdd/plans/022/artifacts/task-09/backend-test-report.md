# Task09 Backend Test Report

## 结果状态与摘要

实现级静态检查和 SQLite 定向行为检查通过；pytest 因本机依赖/虚拟环境阻塞，未取得测试退出码 0。

本次增量新增 `tests/test_task09_conversation_filters.py`，覆盖绑定归档会话全局可见、
`unbound_only`、active/archived keyset 分页、非法 status 与非法组合。

## 测试命令/退出码/结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `python -m py_compile backend/app/memory/models.py backend/app/memory/repository.py backend/app/api/routes_conversations.py` | 0 | 通过 |
| `PYTHONPATH=. python - <<'PY' ...`（5 项目并列时间跨页、去重、排序及旧 cursor 拒绝） | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| `PYTHONPATH=. python - <<'PY' ...`（会话 status/unbound_only 过滤及筛选 cursor 隔离） | 0 | 通过 |
| `PYTHONPATH=. python - <<'PY' ...`（默认/项目 A/项目 B/unbound/status cursor 互换拒绝） | 0 | 通过 |
| `pytest -q tests/test_task09_project_activity.py tests/test_memory_repositories.py tests/test_conversations_api.py` | 2 | 阻塞：系统 Python 缺少 `fastapi`，且未设置项目 import 环境 |
| `pytest -q tests/test_task09_conversation_filters.py tests/test_task09_project_activity.py tests/test_memory_repositories.py tests/test_conversations_api.py` | 2 | 阻塞：系统 Python 缺少 `fastapi`，且未设置项目 import 环境 |
| `.venv/bin/pytest -q tests/test_task09_project_activity.py tests/test_memory_repositories.py tests/test_conversations_api.py` | 127 | 阻塞：`.venv/bin/pytest` shebang 指向不存在的 `/Users/wjh/PyCharmMiscProject/.venv/bin/python` |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_task09_project_activity.py tests/test_task09_conversation_filters.py tests/test_memory_repositories.py` | 0 | 通过：32 passed，1 warning |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_task09_project_activity.py tests/test_task09_conversation_filters.py tests/test_memory_repositories.py tests/test_conversations_api.py` | 1 | 42 passed，1 unrelated asynchronous worker test flaky failure (`test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse`) |
| `PYTHONPATH=. /Users/wjh/ResearchAgent_codebuddy/.venv/bin/pytest -q tests/test_task09_project_activity.py::test_projects_api_payload_always_contains_last_activity_at` | 0 | 通过：1 passed，1 warning |

## 覆盖范围

- 无会话项目回退到项目 `updated_at`。
- active/archived 会话参与聚合，deleted 会话排除。
- owner 隔离。
- 并列 `last_activity_at` 按 `project_id DESC` 稳定排序。
- 多页 keyset 无重复/遗漏；旧 `projects` cursor 不被接受。
- API payload 恒含 `last_activity_at`。
- API payload 测试同时验证项目时间领先时回退项目时间、会话时间领先时采用会话时间。
- 项目列表只建立一次数据库连接，避免 N+1 查询。
- 会话 cursor 交换拒绝：默认列表、项目 A、项目 B、`unbound_only` 和 status 筛选各自隔离。

## 风险与阻塞

需要在安装 `requirements.txt` 的环境重新执行上述 pytest 命令，特别是 API payload 测试和既有 conversations 回归。

## 开始结束总耗时

- 开始：2026-09-11
- 结束：2026-09-11
- 总耗时：约 20 分钟

## 可用时模型/token/tool 统计

- 模型：当前子 Agent（Luna high，按任务交接指定）
- token/tool：未提供可核验的运行时 token 计数；记录了命令退出码和静态/行为验证结果。
