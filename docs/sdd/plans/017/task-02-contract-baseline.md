# 任务 02：建立迁移清单与契约基线

> 关联：[Spec017](../../specs/017-backend-bounded-context-modularization.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 01；当前状态：`待执行`

## 目标

记录所有待迁移 Python 文件、项目内 import、路由和配置归属，并为当前 HTTP/OpenAPI 与用户配置建立可比较基线。

## 文件边界与交付

- 新增迁移清单、路由/OpenAPI 快照说明和配置保留矩阵到 `docs/sdd/plans/017/`。
- 不移动代码，不修改数据或配置。
- 明确 Task04 承接 Spec015 Task10，并在随后更新其状态为“由 Spec017 承接”。

## 分派

由 tester 只读盘点 `backend/app/`、`tests/`、`frontend/` 与现有 Spec015；返回文件清单、外部契约、风险和测试命令。主 Agent 读回落盘产物后才能启动 Task03。

## 验收（技术评审必改项 5：硬门禁，未完成不得启动 Task03）

- **全量迁移清单逐项可勾选**，每行含：文件路径 → 目标目录 → 承接任务 → 删除时机；**同一文件只归属一个任务**。
- 清单必须覆盖：
  - 全部 `.py` 实现文件；
  - 测试与其 **monkeypatch / patch 字符串**（如 `backend.app.services.kb.store`、`backend.app.api.routes`、`tests/test_api_routes_coverage.py`）——漏改会造成「测试通过但打错目标」的假绿；
  - 启动与部署脚本（`scripts/`、`deploy/`）中的模块路径；
  - `observability/`、`core/config.py`、`core/article_settings.py`；
  - `services/kb/__init__.py` 的**全部 facade 消费者**；
  - 动态 import 字符串（`importlib.import_module`、点分路径配置）——无法用 AST 判定，必须按字符串 grep。
- 现有 API 路径、请求/响应模型、**两类错误体**（`/papers/*` 的 `{code,message,retryable}` 与其余端点的 `{"detail": ...}`）、环境变量和数据文件都有基线记录。
- 冻结 `GET /openapi.json` 快照：剔除不稳定字段，记录 FastAPI / Pydantic 版本。
- 无代码改动；清单未覆盖的文件一律标为「待裁决」，不得由实现 Agent 自行处理。

## 风险与回滚

基线缺失即阻塞；本任务仅新增文档，删除文档即可回退。
