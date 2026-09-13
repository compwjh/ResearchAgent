# Spec034 Task06 后端验收报告

## 结论

**GO**。上轮发现的 USENIX 目录图兼容性回归已修复并稳定复验通过；Task06 合同、固定 SQLite/fake 运行时探针、Spec015/027/032/033/Skill/Tool 定向回归及静态门禁全部通过，未发现当前阻塞。

本次仅验收，未修改业务代码或 Spec，未执行 commit/push/merge/reset/stash/clean。

## 验收范围

- Spec015 目录/RAG/Store 复用与 Task06 唯一 `CatalogSourceFactory` 接线。
- 本地命中、远程增量刷新、`usenix`/`dblp`/`all` scope、同一 Adapter 的 scope 切换与 SearchJob 来源隔离。
- 单源/双源失败诊断、缓存诊断、Evaluator 阈值与淘汰统计、Critic 两轮与审批标记。
- Tool 参数映射、候选 URL/下载边界、论文文本不进入研究运行时上下文、唯一 Orchestrator 接线。
- 真实 USENIX/DBLP/Ollama/Qdrant 仅按环境可达性验证，不以 fake 结果冒充真实成功。

## 命令与结果

| 检查 | 命令摘要 | 退出码 | 结果 |
|---|---|---:|---|
| 上轮失败测试复验 | `.venv/bin/python -m pytest -q tests/test_usenix_publication_source.py::test_frozen_job_is_not_degraded_when_only_detail_pages_failed` | 0 | **1 passed**，0.49s |
| Task06 + Spec015/027/032/033 + Skill/Tool 定向 pytest | `.venv/bin/python -m pytest -q`，包含 Task06 合同、Graph/Catalog/PaperDiscovery、USENIX/DBLP、详情/候选、Spec027、Skill/Tool 测试 | 0 | **384 passed, 5 warnings, 11 subtests passed**，28.61s |
| Task06 合同 | `.venv/bin/python -m pytest -q tests/test_spec034_task06_contract.py` | 0 | **12 passed**，0.50s |
| Python 语法 | `.venv/bin/python -m py_compile`（Task06 Graph/Adapter/Runner/Orchestrator/Planner/Entry 及合同测试） | 0 | 通过 |
| 聚焦 Ruff | `.venv/bin/ruff check`（Task06 改动文件及合同测试） | 0 | All checks passed |
| diff 空白检查 | `git diff --check 1879fb3 --`（Task06 改动文件及合同测试） | 0 | 通过 |

## 上轮阻塞与本轮修复复验

上轮失败：`tests/test_usenix_publication_source.py::test_frozen_job_is_not_degraded_when_only_detail_pages_failed`。

原问题是 `CatalogSearchGraph.__new__(CatalogSearchGraph)` fixture 仅设置 `graph.store`，而 `_catalog_conference_ids()` 直接访问未初始化的 `self.source_scope`，抛出：

```text
AttributeError: 'CatalogSearchGraph' object has no attribute 'source_scope'
```

本轮修复后同一测试单独运行退出码 0，`1 passed in 0.49s`；完整定向回归亦退出码 0。当前无验收阻塞。

## 固定 SQLite/fake 运行时探针

Task06 合同 `12 passed` 覆盖并实际执行了以下探针：

1. 本地已有 indexed 论文时 cache hit，不刷新远程；本地不足时注入 fake Graph 执行远程增量并保留 refresh diagnostics。
2. `usenix`、`dblp`、`all` 三种 scope 的 Graph 构造、DBLP SearchJob 隔离及同一长生命周期 Adapter 的 scope 切换。
3. 单源无来源/异常返回 `SOURCE_UNAVAILABLE` 或 `SOURCE_DEGRADED`，不把空候选伪装 completed；Graph/source 失败诊断可保留。
4. Evaluator 保留软阈值边界、淘汰原因和统计；Critic 最多两轮同范围 re-plan，范围扩大标记 `approval_required`。
5. Tool 映射只保留冻结字段；详情/下载只接收候选 URL/candidate；候选 URL 与论文文本安全边界测试通过，文本不进入计划/Tool 参数。
6. 唯一 Orchestrator/SearchWorker 接线和既有 Spec015 目录能力复用通过。

## 真实服务探针

- `curl -sS -I --max-time 5 https://www.usenix.org`：退出码 0，HTTP 200。
- `curl -sS -I --max-time 5 https://dblp.org`：退出码 0，HTTP 200。
- 临时隔离 SQLite + 默认 `CatalogSourceFactory` 的真实 adapter smoke：
  - `sources=("usenix",)`：退出码 0，`SOURCE_DEGRADED`，`usenix=failed`，0 candidate。
  - `sources=("dblp",)`：退出码 0，`SOURCE_DEGRADED`，`dblp=failed`，0 candidate。
  - `sources=("all",)`：退出码 0，`SOURCES_UNAVAILABLE`，双源 failed，0 candidate。
  - 诊断保留 `source_status`、cache/fetch/empty_source；未伪造 completed。
- `ollama list`：退出码 0，列出 11 个本地模型；HTTP adapter `get_available_models()` 退出码 1，`httpx.ConnectError: [Errno 1] Operation not permitted`。
- `curl -sS -I --max-time 5 http://127.0.0.1:6333/collections`：退出码 7，Qdrant 未监听。

因此，USENIX/DBLP 公网页头可达不等于本次真实目录同步成功；真实 adapter smoke 没有产生候选，按实现契约返回 degraded/unavailable，Ollama HTTP 与 Qdrant 环境限制已如实记录。

## 后续与边界

- 上轮 `source_scope` 兼容性缺陷已修复；后续可接入下一 Task。
- 本次未运行全量 pytest；最终 Spec 收口仍需总控执行全量回归、可达环境真实 smoke、部署和状态台账。

## 日志

- 进展日志：[backend-tester 日志](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-034/task-06/backend-tester/20260913-140000.md)
