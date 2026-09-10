# Task 06E-C：Inspection Manifest 版本门禁报告

## 固定回传字段

- 结果状态和摘要：`completed`。Inspection manifest 的构建、schema、存取和 API 错误协议已统一到 `source-anchor-v2`；旧 `source-anchor-v1` 清单不会继续进入前端。
- 改动文件：
  - `backend/app/knowledge_base/infrastructure/inspection.py`
  - `backend/app/knowledge_base/infrastructure/manifest_store.py`
  - `backend/app/api/routes_kb.py`
  - `docs/sdd/plans/018/artifacts/task-03/inspection-manifest.schema.json`
  - `tests/test_kb_document_foundation.py`
  - `tests/test_kb_document_routes.py`
- 测试命令、退出码和结果：
  - `git diff --check`：0，`passed`
  - `python -m py_compile backend/app/knowledge_base/infrastructure/inspection.py backend/app/knowledge_base/infrastructure/manifest_store.py backend/app/api/routes_kb.py`：0，`passed`
  - `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/inspection.py backend/app/knowledge_base/infrastructure/manifest_store.py backend/app/api/routes_kb.py tests/test_kb_document_foundation.py tests/test_kb_document_routes.py`：0，`passed`
  - `.venv/bin/python -m pytest -q tests/test_kb_document_foundation.py tests/test_kb_document_routes.py`：0，`31 passed`
- 产物路径：本报告；进展日志：`.codebuddy/agent-logs/spec-018/task-06e/backend-dev/20260910-manifest-version-gate.md`
- 决策依据：`source-anchor-v2` 是新的稀疏真实来源区间映射协议。`schema_version` 继续保持 `inspection-manifest-v1`，只提升 `mapping_algorithm_version`，避免把协议版本和算法版本混为一谈。读取旧算法清单时必须显式提示重建，而不能按“清单不存在”触发后台重建。
- 风险与阻塞：现有真实磁盘清单仍可能是 v1；在真实 manifest 重建完成前，检查 API 会按设计返回 409。未执行真实数据、Qdrant、下载或索引操作。上游 provenance bundle/schema 的变更仍需主 Agent 在合并前复核。
- 主 Agent 后续动作：审查本报告及 diff；确认 source-provenance bundle 的 v2 schema 与 provenance 实现一致；再派前端同步/回归任务；完成后对测试数据执行受控 manifest 重建和浏览器双向点击验收。
- 开始时间：2026-09-10（父 Agent 分派时间未透传，未伪造具体时间）
- 结束时间：2026-09-10T12:07:20Z（UTC）
- 总耗时：未由子 Agent 计时器采集
- 模型：Luna xhigh（按父 Agent 临时分派）
- token 和工具调用统计：当前子 Agent 未获得可靠统计

## 追加契约同步

- 结果状态和摘要：`completed`。将 Task02/02A 的活动 schema、fixture 索引及 Spec018 固定 expected fixtures 的 `mapping_algorithm_version` 机械同步为 `source-anchor-v2`，移除测试中临时修改 schema const 的代码。
- 追加改动文件：
  - `docs/sdd/plans/018/artifacts/task-02a/source-provenance-bundle.schema.json`
  - `docs/sdd/plans/018/artifacts/task-02/provenance-dto.schema.json`
  - `docs/sdd/plans/018/artifacts/task-02/fixture-index.json`
  - `docs/sdd/fixtures/spec-018/*.expected.json`
  - `tests/test_kb_source_provenance_bundle.py`
- 追加验证：两个 Draft 2020-12 schema `check_schema` 通过，8 个 JSON fixture 的 mapping version 校验通过；provenance 定向测试 `22 passed`；`git diff --check` 通过。
- 追加决策依据：仅同步当前有效的契约和固定样本；历史评审/探针报告保留原值作为迁移证据，未修改生产代码。
- 追加风险与阻塞：expected fixture 的 anchor 内容仍由稀疏映射实现负责验证；本次只同步版本字段，没有重写 fixture 的 chunk 或 anchor 内容。
- 追加主 Agent 后续动作：审查活动 schema 与 provenance 实现的版本一致性，确保历史报告不被误当作当前 schema。
- 追加结束时间：2026-09-10T12:16:12Z（UTC）

## 实现要点

1. `inspection.py` 暴露统一的 `MAPPING_ALGORITHM_VERSION`，构建 manifest 前拒绝 bundle 版本不匹配，并继续生成 `inspection-manifest-v1` schema。
2. `manifest_store.py` 在 schema 校验前检查映射算法版本。旧版本返回 `MANIFEST_MAPPING_VERSION_MISMATCH`（HTTP 409），因此不会被 schema 错误或不存在分支掩盖。
3. `routes_kb.py` 把该版本错误转换为稳定的 `INDEX_REBUILD_REQUIRED`（HTTP 409），并返回 `details.cause=MAPPING_VERSION_MISMATCH`，不自动重建、不返回旧 anchors。
4. 固定 manifest schema 将 `mapping_algorithm_version` 的 const 更新为 `source-anchor-v2`。
5. 测试覆盖 v2 manifest 生成与存取、旧 manifest 文件读取、bundle 版本不匹配、API 旧版本重建门禁。
