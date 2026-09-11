# Task09 Backend Implementation Report

## 结果状态与摘要

已完成。项目列表现在由单条 SQLite 聚合投影计算 `last_activity_at`，并按
`last_activity_at DESC, project_id DESC` 使用同键 keyset cursor 分页；旧项目
`updated_at` cursor 会被独立 cursor kind 拒绝，避免排序键混用。

### 后续增量：会话归档治理筛选

已补充既有 `GET /api/conversations` 的可选 `status=active|archived` 和
`unbound_only=true` 筛选。显式 status 视为全局状态视图，因此可以看到绑定项目
的 archived conversation；`unbound_only` 仅返回未绑定会话，且与 `project_id`
组合稳定返回 400。筛选签名写入 cursor kind，避免跨筛选复用 keyset cursor。

## 改动文件

- `backend/app/memory/models.py`：为 `Project` 增加非持久化的 `last_activity_at` read-model 字段。
- `backend/app/memory/repository.py`：项目列表改为单条 CTE/聚合查询；过滤同 owner 且 status != `deleted` 的会话；新增 activity cursor keyset；point read 无聚合时回退到项目 `updated_at`。
- `backend/app/memory/repository.py`：会话列表 cursor 升级为始终包含 `project_id`、`status`、`unbound_only` 的 v3 scope 签名，项目/默认/未绑定/状态列表之间不可互换 cursor。
- `backend/app/api/routes_conversations.py`：项目 payload 恒返回 `last_activity_at`。
- `tests/test_task09_project_activity.py`：新增 Task09 后端定向覆盖。
- `tests/test_task09_conversation_filters.py`：新增归档、未绑定筛选、筛选分页和非法参数覆盖。

## 决策依据

- 遵循 Task09 技术评审冻结的排序键和 cursor 一致性约束。
- `LEFT JOIN ... AND c.status != 'deleted'` 保留无会话项目，并将 archived 会话纳入活动时间。
- 不新增 schema 列、不修改项目/会话删除或 owner 隔离语义。
- 默认无筛选请求保持原有未绑定且非 deleted 的列表行为；project_id 请求继续保留原有项目存在性校验。

## 风险与阻塞

- 当前工作区默认 Python 环境缺少 FastAPI，项目 `.venv/bin/pytest` 的解释器链接指向不存在的 `/Users/wjh/PyCharmMiscProject/.venv/bin/python`，因此 pytest 无法在本机环境完成收集；已通过 py_compile、SQLite 定向脚本和 diff 检查。新增筛选的 SQLite 分页/过滤脚本已通过。

## 主 Agent 后续动作

- 在具备项目依赖的环境执行报告中的精确 pytest 命令；确认通过后与前端 Task09 结果合并并执行集成验收。

## 开始结束总耗时

- 开始：2026-09-11（本轮交接开始）
- 结束：2026-09-11
- 总耗时：约 20 分钟

## 可用时模型/token/tool 统计

- 模型：当前子 Agent（Luna high，按任务交接指定）
- token/tool：未提供可核验的运行时 token 计数；使用文件读取、补丁编辑、py_compile、定向脚本与 pytest/diff 检查。
