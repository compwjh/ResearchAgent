# 任务 06：迁移文章助手与聊天

> 关联：[Spec017](../../specs/017-backend-bounded-context-modularization.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 03（settings repository 就绪）；当前状态：`已完成`

> 2026-09-08 收口：Article Agent 已迁入 `article_assistant/application/article_agent.py`，旧路径删除，文章/意图/API 定向回归通过。
> 目录边界不重叠时可与 Task04 并行，但**不得与 Task04 同时移动同一个 settings repository 或数据文件**。

## 目标

把旧文章 Agent、搜索、下载、下载 Skill、TaskStore 与设置迁移到 `article_assistant/`；把聊天领域状态和图迁移到 `chat/`。

## 约束

- 保持 `/api/agent/*`、`/api/chat`、持久化设置文件、下载行为和 SSE 输出不变。
- 文章助手设置与论文发现设置分离；兼容读取旧 JSON，保存时不删除另一业务的字段。
- 聊天模型仅经 `platform` 的 Ollama 适配调用。

## 验收

- Agent 搜索、下载、登录确认、任务查询和聊天流式响应测试通过。
- 顶层 `agents/`、`graphs/`、旧文章相关 `services/` 与 `domain/article.py`、`domain/chat.py` 无残留实现。
