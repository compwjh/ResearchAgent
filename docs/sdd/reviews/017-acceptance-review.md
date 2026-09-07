# Spec017 验收评审：后端限界上下文模块化

- **评审者**：架构师（**主模型代行**）
- **代行原因**：用户 2026-09-08 明确要求「子 agent 都让你代行（临时要求）」，
  故本次验收评审由主会话按 `tester` / `backend-reviewer` 的职责清单执行，
  未另起子代理。代行事实已在本文件头部与 `docs/sdd/retro/2026-09-08-spec017-modularization-retro.md` 留痕。
- **评审时间**：2026-09-08（Asia/Shanghai）
- **评审对象**：`feature/spec-015-security-paper-discovery` 分支上 Task02–Task08 全部提交
- **关联 Spec**：[`017-backend-bounded-context-modularization.md`](../specs/017-backend-bounded-context-modularization.md)
- **关联任务**：[Task 02](../plans/017/task-02-contract-baseline.md)、[Task 03](../plans/017/task-03-api-platform.md)、
  [Task 04](../plans/017/task-04-paper-discovery.md)、[Task 05](../plans/017/task-05-knowledge-base.md)、
  [Task 06](../plans/017/task-06-article-chat.md)、[Task 07](../plans/017/task-07-remove-legacy-boundaries.md)、
  [Task 08](../plans/017/task-08-review-deploy-retro.md)

## 结论：**通过**（Task02–Task08 全部完成）

## 验收项与证据

| 验收项 | 要求 | 证据 | 结论 |
|---|---|---|---|
| 目录结构 | 业务按限界上下文归位 | `knowledge_base/`（application + infrastructure 10 模块）、`paper_discovery/`（domain 5 / infrastructure 11 / application 4）、`article_assistant/`、`chat/`、`platform/`（settings、ports、bootstrap、ollama、ollama_direct、observability） | 通过 |
| API 契约不变 | 路径/schema/状态码/错误体无差异 | 与 Task02 冻结的 `openapi-baseline.json` 逐项比对：36 个操作，0 缺失 / 0 新增 / 0 operationId 变化 / 0 schema 差异 | 通过 |
| 旧结构清零 | 旧路径零 import、零实现文件 | `backend/app/{services,domain,graphs,observability}` 已删除；架构测试 `test_no_legacy_module_paths` 锁定 | 通过 |
| 包级 facade 拆除 | 不存在包级 wildcard/facade 作为跨层通道 | `services/kb/__init__.py`（43 成员）已删；三个上下文的 `__init__.py` 均 `__all__ = []`；跨上下文改走 `knowledge_base.application` / `paper_discovery.application.entry` / `article_assistant.application.entry` | 通过 |
| 依赖方向 | `api → application → domain/infrastructure`；platform 不反向依赖业务 | 架构测试 5 条：`api` 无模块级单例、`api` 不直连 `infrastructure`、platform 不 import 业务模块、业务模块不 import 其它上下文 domain/infrastructure、旧路径零 import | 通过 |
| 设置拆分与原子写 | 保留未知 key、原子写 | `platform/settings/`（article_assistant / paper_discovery / settings_repository），Task03 已交付并经既有测试覆盖 | 通过 |
| 跨域 port | 论文导入→知识库只定义不实现 | `platform/ports.py`（Protocol + 只读 DTO），实现仍留 Task05 之后的 spec-015 范围 | 通过 |
| composition root | 统一 factory + 测试替换点 | `platform/bootstrap.py`（ProviderRegistry，`override` 支持嵌套与异常恢复）；路由依赖经 `get_provider` 解析 | 通过 |
| 全量回归 | 测试通过 | `631 passed / 0 failed`（628 基线 + 3 条新增架构断言中的 2 条增量，另 2 条替换前次 3 条） | 通过 |
| 静态检查 | 无新增告警 | `ruff check backend tests scripts` = 122 条，与迁移前基线持平 | 通过 |
| 运行时 | 实际启动并验证 | `./deploy/start.sh -d` 启动成功；`GET /api/health` 200（`status: ok`）、`GET /` 200、`GET /api/kb/health` 200、`GET /api/papers/conferences` 200（返回真实会议列表）、`GET /api/kb/papers` 200（返回真实论文） | 通过 |

## 运行时尚存降级（不阻塞）

- **Reranker 以 RRF 降级模式启动**：本地缺少 `data/models/qwen3-reranker-0.6b-q8_0.gguf`，
  `/api/kb/health` 返回 `reranker: false`。这是 spec-014 已记录的既定降级行为，非本次迁移引入，
  不阻塞收口。

## 过程发现并已修正的问题

1. **`platform/ollama.run_chat` 反向依赖业务模块**：它通过 `graphs.chat` 驱动 LangGraph，
   而 platform import 业务模块属禁止项——由新增的边界测试当场捕获，已下沉到
   `chat/application/chat_runner.py`。
2. **引用形式漏扫**：只扫 `services.kb.X import` 会漏掉 `from services.kb import X`
   （子模块当属性导入，测试侧 15 行），曾导致一次 ImportError。
3. **转发文件不能用 `import *`**：会生成独立模块对象使 `patch.object` 失效（实测 3 个测试失败），
   改用 `sys.modules` 别名。
4. **patch 目标必须随代码迁移**：`platform.ollama.chat_direct_stream` 等 patch 点需同步更新，
   否则 mock 失效并可能打到真实模型。

## 签字

- 测试（QA）：**通过**（主模型代行，原因见文首）
- 开发主管（Tech Lead）：**通过**（主模型代行，原因见文首）
- 架构师（Architect）：**通过**，同意 Spec017 转 `已完成`
