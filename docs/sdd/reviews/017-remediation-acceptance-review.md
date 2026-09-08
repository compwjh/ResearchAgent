# Spec017 修复轮验收评审

- **评审时间**：2026-09-08（Asia/Shanghai）
- **评审对象**：Spec017 审计回退后的旧路径清理、配置归位、PaperImportPort 接线与 Article Agent 迁移
- **执行模型**：本轮实现子代理统一使用 `gpt-5.6-luna xhigh`；该选择仅对本轮有效，不写入长期规则
- **关联 Spec**：[017-backend-bounded-context-modularization.md](../specs/017-backend-bounded-context-modularization.md)

## 结论：通过

本轮修复已闭环此前阻塞收口的四项缺口，且未改变既有 HTTP、下载安全、索引和错误语义。

| 审计项 | 修复与证据 | 结论 |
|---|---|---|
| 旧 Article Agent | `backend/app/agents/article_agent.py` 删除；实现迁入 `article_assistant/application/article_agent.py`；生产与测试 import 已同步 | 通过 |
| 旧配置路径 | `backend/app/core/config.py` 删除；唯一配置实现为 `platform/config.py`；旧 import 扫描零结果 | 通过 |
| routes 兼容 facade | `backend/app/api/routes.py` 仅保留总路由注册，不再 re-export / `__getattr__`；API 消费者按真实模块引用 | 通过 |
| PaperImportPort | `paper_discovery/application/paper_import.py` 只消费 `platform.ports` 与 provider；KB 侧提供 `KnowledgeBasePaperImportAdapter`；factory 自定义参数回归已修复 | 通过 |
| 边界测试 | `tests/test_api_module_boundaries.py` 通过 6 项；旧路径与跨域直连扫描无违规 | 通过 |
| 定向回归 | `131 passed, 13 subtests, 5 warnings` | 通过 |
| 全量回归 | `.venv/bin/python -m pytest -q`：`653 passed, 38 subtests, 5 warnings` | 通过 |
| 工作树卫生 | `git diff --check` 通过；全仓冲突标记扫描无结果 | 通过 |

## 运行时与已知非阻塞项

- Spec017 既有部署证据已记录于历史验收报告；本轮未改变启动入口。
- Reranker 缺少本地模型时仍按 Spec014 的既定 RRF 降级，不属于本轮回归。
- OpenAPI 当前存在后续 Spec015 异步检索端点相对早期冻结基线的差异；该差异不由本轮修复引入，保留在 Spec015 范围处理。

## 签字

- 测试：通过（本轮实际定向与全量命令证据）
- 开发主管：通过（本轮修复范围与边界证据）
- 架构师：通过，同意 Spec017 转 `已完成`

## 产物

- `docs/sdd/reviews/017-task06-article-agent-fix.md`
- `docs/sdd/reviews/017-task06-paper-port-factory-fix.md`
- `.codebuddy/agent-logs/backend-dev-spec017-20260908-191423.md`
- `.codebuddy/agent-logs/backend-dev-spec017-20260908-000000.md`
- `.codebuddy/agent-logs/backend-dev-spec017-paper-port-20260908-000000.md`
