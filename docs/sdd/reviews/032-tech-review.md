# Spec032 技术评审

## 评审元数据

- 评审者：Spec032 Task14 review-regression 子 Agent
- 角色：技术/复用/安全复核（临时 Luna high）
- 模型：Luna high
- 分派方式：主 Agent 直接分派
- 依据：当前 diff、Task06–13 交接物、751 项相关回归与静态检查

## 结论

**打回（P1 集成缺口）。** 统一合同、来源注册、URL/PDF 安全边界、批任务恢复和复用约束的离线证据充分；但 Planner/Research 的新来源执行路径没有接通，导致 Spec032 核心“多来源 Worker Skill”在实际 Research 任务中不可用。

## 通过项

- 相关集合 `751 passed`、15 subtests；Ruff、compileall、`git diff --check`、两个前端 `node --check` 均通过。
- `PaperDiscoveryToolFacade` 复用既有 Store、来源 Adapter、`paper_import` 和服务端固定 host allowlist；没有新建下载器、PDF 仓库、批状态机、embedding 或 RRF 实现。
- Task07 的官网字段缺失、未验证年份、目录阶段不探测 PDF 等边界在固定样本中有测试覆盖；CCS/NDSS 的 NO-GO 状态未被伪造为成功。

## P1 证据

- `backend/app/research/application/search_catalog_adapter.py:95-96` 的 `CatalogSourceFactory.build()` 只允许 `usenix|dblp|all`，而 `planner.py:83-107` 与 `map_catalog_tool_args():165-190` 接受 `ieee_sp/ccs/ndss/openalex/crossref`。实测 `CatalogSourceFactory().build(source_scope="ieee_sp")` 抛 `ValueError: invalid catalog source scope`。
- `search_catalog_adapter.py:344-348,454-455` 固定 `usenix-security`/`dblp` conference scope；新来源不会调用其 Adapter 或官网能力。
- `backend/app/skills/registry.py:51-90` 旧 `search_paper_catalog` schema 仍只有 `usenix/dblp/all`；`session_plan_generation.py:19-23,94` 默认能力仍只有 `usenix-catalog-orchestration` 与旧搜索/detail Tools，没有新增来源 Skill 或统一 `paper_discovery`。

## 修复验收要求

1. 对每个允许 source ID 明确装配对应 Registry Adapter/Skill/Tool，未知/未验证来源保持稳定 blocked/NO-GO。
2. 为 Planner→AgentRuntime→Tool dispatch 增加 source selection 测试，证明真实调用的是 `paper_discovery` 的 `worker-tool-v1`，而非旧 USENIX/DBLP fallback。
3. 保持既有安全链唯一性：下载、身份、KB 导入、批次恢复和 embedding 均只复用已有实现。
4. 启动服务做受控真实 smoke，并记录真实终态、重启恢复和失败队列；在此之前不得技术签字。

## Task08 follow-up 复评追记（2026-09-20）

Task08 的 P1 接线缺口已修复：`CatalogSourceFactory` 接受七来源；非
`usenix/dblp/all` 来源统一经 `PaperDiscoveryToolFacade` 和
`WorkerToolResult` validator，再落入既有目录、来源记录、字段 provenance 及冻结搜索快照。
USENIX/DBLP/all 仍保持原 Graph 路径。Task08/09/Spec034 合同 23 passed、相关来源/Graph
回归 215 passed，Ruff、compileall、`git diff --check` 通过。

该追记只关闭本评审中的 P1 接线项；真实外部目录、Ollama/Qdrant、部署和登录/导入 smoke
仍由 Task14 验证，故本技术评审在 Task14 完成前不改写最终签字结论。
