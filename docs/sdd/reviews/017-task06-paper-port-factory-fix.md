# Spec017 PaperImportPort factory 接线修复

- 关联规范：`docs/sdd/specs/017-backend-bounded-context-modularization.md`
- 关联任务：Spec017 PaperImportPort 收口单点修复
- 执行角色：backend-dev
- 进展日志：`.codebuddy/agent-logs/spec-017/task-00/backend-dev/backend-dev-spec017-paper-port-20260908-000000.md`
- 执行模型：gpt-5.6-luna xhigh（本轮临时选择）

## 状态摘要

已修复 API composition root 中 `PaperImportPort` 的 factory 注册方式。
`ProviderRegistry.get()` 会调用注册值后再返回结果；若直接注册
`create_paper_import_port`，`paper_import_port_factory` 会解析成已实例化的
`KnowledgeBasePaperImportAdapter`，导致论文发现侧在传入临时路径、indexer、deleter
或 client 时无法调用 factory。现改为显式零参包装器，返回构造器本身；论文发现仍
只通过 provider/port 合作，不恢复对 `knowledge_base.application` 的直接 import。

## 改动文件

- `backend/app/api/common.py`
  - 新增 `_paper_import_port_factory()` 包装器。
  - `paper_import_port_factory` 注册为该包装器（`singleton=False`），保证解析结果是
    可调用的 `create_paper_import_port`。
- `backend/app/paper_discovery/application/paper_import.py`
  - 本轮未修改；保留现有 `PaperImportPort` 注入与 provider 解析逻辑。

## 测试命令 / 退出码 / 结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m py_compile backend/app/api/common.py backend/app/paper_discovery/application/paper_import.py` | 0 | 通过 |
| provider 解析检查（断言 `get_provider("paper_import_port_factory")` 可调用） | 0 | 输出 `function create_paper_import_port` |
| 自定义 paths/indexer/deleter 的 `_resolve_port` 解析检查 | 0 | 输出 `KnowledgeBasePaperImportAdapter`，临时 paths 断言通过 |
| `.venv/bin/python -m pytest tests/test_paper_import.py -q` | 0 | `9 passed in 0.41s` |
| `.venv/bin/python -m pytest tests/test_paper_import_batch_api.py tests/test_paper_discovery_api.py tests/test_paper_discovery_async_api.py -q` | 0 | `25 passed, 9 subtests passed in 0.80s` |
| `.venv/bin/python -m pytest tests/test_api_routes_coverage.py -q` | 0 | `41 passed in 18.82s` |
| `.venv/bin/python -m pytest tests/test_api_module_boundaries.py -q` | 0 | `6 passed in 0.31s` |
| `git diff --check -- backend/app/api/common.py backend/app/paper_discovery/application/paper_import.py` | 0 | 通过 |

## 风险与边界

- 本修复仅涉及 composition root 的 provider/factory 接线；不改变导入状态机、错误码、
  文件安全策略或 API 契约。
- `paper_discovery` 未新增对 `knowledge_base.application` 的 import；KB 实现仍由 API
  装配层提供。
- 全量 pytest、本地服务部署与 Spec018 不在本任务范围内；当前工作树其它 Spec017
  迁移改动未调整。

## 交接

主 Agent 可将本报告、进展日志与 `backend/app/api/common.py` 的接线改动一并纳入
Spec017 收口提交。该修复开始于约 19:32，结束于 19:39（Asia/Shanghai），耗时约 7 分钟。
