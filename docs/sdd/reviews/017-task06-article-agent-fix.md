# Spec017 Task06 文章 Agent 模块迁移结果

- 关联规范：`docs/sdd/specs/017-backend-bounded-context-modularization.md`
- 关联任务：`docs/sdd/plans/017/task-06-article-chat.md`、`docs/sdd/plans/017/task-07-remove-legacy-boundaries.md`
- 执行角色：backend-dev
- 进展日志：`.codebuddy/agent-logs/backend-dev-spec017-article-agent-20260908-191423.md`

## 状态摘要

已完成审计缺口 A：将文章 Agent 从旧 `backend.app.agents` 实现目录迁移到
`backend.app.article_assistant.application`，更新生产代码及测试 import/patch 路径，并删除旧实现文件；未保留兼容转发。新文件与旧实现正文逐字一致，意图识别、`ArticleTask` 构造、HTTP/SSE 路由调用行为保持不变。

## 改动文件

- 新增 `backend/app/article_assistant/application/article_agent.py`
- 删除 `backend/app/agents/article_agent.py`
- 更新 `backend/app/api/routes_article.py`
- 更新 `tests/test_article_agent.py`
- 更新 `tests/test_intent_classification.py`

## 测试命令 / 退出码 / 结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m py_compile backend/app/article_assistant/application/article_agent.py backend/app/api/routes_article.py tests/test_article_agent.py tests/test_intent_classification.py` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/test_article_agent.py tests/test_intent_classification.py tests/test_chat_route.py tests/test_api.py tests/test_api_routes_coverage.py` | 0 | 68 passed |
| `.venv/bin/python -m pytest -q`（迁移后首轮） | 0 | 651 passed，5 warnings，38 subtests passed |
| `git show HEAD:backend/app/agents/article_agent.py \| diff -u - backend/app/article_assistant/application/article_agent.py` | 0 | 新旧实现逐字一致 |
| `.venv/bin/python -m pytest -q tests/test_article_agent.py tests/test_intent_classification.py`（最终文件复核后） | 0 | 11 passed |
| `.venv/bin/python -m pytest -q`（最终复跑） | 2 | 收集阶段被并行 Spec017 配置迁移阻塞：`backend.app.core.config` 已被另一切片移除但 `paper_import`、观测测试等旧引用尚未同步；与本切片文件无关 |
| `git diff --check -- backend/app/article_assistant backend/app/agents backend/app/api/routes_article.py tests/test_article_agent.py tests/test_intent_classification.py` | 0 | 通过 |

## 决策依据

Spec017 Task06 明确要求旧文章 Agent 归属 `article_assistant/application`，Task07 要求迁移范围内旧 `agents/` 实现和项目内 import 清零。实现采用纯路径迁移：不改变函数签名、常量、LangGraph 节点、模型调用、`ArticleTask` 字段和状态判定；生产路由只改为从新应用模块导入 `build_task`，测试中的 import/patch 目标同步改为新路径。

## 风险与阻塞

- 本切片未发现文章 Agent、聊天或 API 定向回归风险。
- 最终全量 pytest 的 15 个收集错误来自并行 Spec017 配置迁移留下的 `backend.app.core.config` 旧引用，属于其他切片的集成阻塞；首轮全量在该并行改动尚未落入当前导入状态时通过。
- `backend/app/agents/__pycache__` 中可能仍有本地历史字节码缓存，但旧源文件和项目内可执行 import 已删除；该缓存未纳入版本控制，也未作为兼容实现使用。

## 主 Agent 后续动作

1. 将本报告、进展日志及本切片代码纳入同一 Spec017 修复提交。
2. 待配置迁移切片完成后，重新运行全量 pytest，并确认 `backend.app.agents.article_agent` 全仓旧路径扫描仍为零。
3. 按 Spec017 收口流程继续处理其余审计缺口，不在本切片扩展论文发现、KB 或用户数据范围。

## 执行时间与资源

- 开始：2026-09-08 19:14:23 +0800
- 结束：2026-09-08 19:20:44 +0800
- 总耗时：约 6 分 21 秒（不含后续主 Agent 集成等待）
- 可用模型：gpt-5.6-luna xhigh
- Token：由调度器计量；本子任务未暴露独立 token 统计
- 工具：读取/搜索、补丁编辑、项目虚拟环境 `py_compile`/`pytest`、Git 只读差异检查；未执行 reset、stash、clean、push 或提交历史修改
