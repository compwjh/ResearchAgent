# Task02 后端实现报告

## 结果

后端最小纵向闭环已实现：独立 memory SQLite、项目 CRUD 最小接口、惰性首条消息和已有会话消息入口、服务端历史装配/游标、项目记忆分类与召回、处理步骤和 SSE。旧 `/api/chat`、`/api/agent/run` 未修改。

## 改动文件

- `backend/app/memory/__init__.py`
- `backend/app/memory/models.py`
- `backend/app/memory/repository.py`
- `backend/app/chat/application/conversation_service.py`
- `backend/app/api/routes_conversations.py`
- `backend/app/api/schemas.py`
- `backend/app/api/routes.py`
- `tests/test_memory_repositories.py`
- `tests/test_conversations_api.py`

## 接口契约

- `POST/GET/PATCH/DELETE /api/projects[/{project_id}]`（项目删除级联删除所属会话/项目记忆）
- `POST /api/conversations/messages`：校验后原子创建 conversation/user/assistant pending，再返回 SSE
- `POST /api/conversations/{id}/messages`：已有会话消息
- `GET /api/conversations`、`GET /api/conversations/{id}/messages?before=&target_chars=`
- `PATCH/DELETE /api/conversations/{id}`
- `GET /api/memories`、`GET /api/messages/{id}/processing-steps`
- SSE 帧为 `data: JSON\n\n`，包含 `meta`、`progress`/`memory`、`token`、`error`、`done`；记忆分析、记忆召回、回答生成均发送真实 processing step 的 running/completed/failed `progress` 事件；memory 支持 `saved`、`used`、`needs_confirmation`、`not_analyzed`。

## 决策依据与边界

- 数据库固定默认到 `data/memory/memory.sqlite3`，支持 `MEMORY_DB_PATH` 测试/部署覆盖；WAL、busy timeout、外键和幂等 schema version 1。
- owner 使用服务端 `MEMORY_OWNER_ID`（默认 `local-user`），不接受客户端 owner_id。
- 项目记忆查询同时限制 owner/project/status；未绑定会话不查询项目记忆。
- `explicit` 仅写入项目 memory/evidence；`ambiguous` 仅发 `needs_confirmation`；`none` 不新增记忆。分类异常发 `not_analyzed` 并继续聊天。
- 模型回答通过既有 `run_chat` adapter，未复制论文、知识库或文章任务逻辑。

## 风险与后续

- 默认工作树 `.venv/bin/pytest` 启动器指向已不存在的旧解释器路径；验证使用 `/Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest`。主 Agent 部署前应修复或明确项目运行时路径。
- 前端仍需接入新端点、稳定 `/c/{conversation_id}` URL、处理过程与记忆事件展示。
- 项目删除级联、完整 memory 管理 UI、全局记忆写入和中断连接的客户端竞态属于后续任务/整合验收。
