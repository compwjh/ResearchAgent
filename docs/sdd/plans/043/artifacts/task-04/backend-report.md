# Spec043 Task04 backend-dev 交接报告

## 状态

**PASS_WITH_LIMITATIONS（后端精准测试通过，待独立复审/真实 API）**。本轮仅实现并验证本地 SQLite + fake provider 组合；没有真实外部 provider、PDF、生产数据库、部署或提交。

## 实际改动

- `backend/app/literature_maps/domain/models.py`
  - 增加持久 `MapPreview` DTO；节点增加 `removed` 投影，保留既有文档、下载、位置和分组字段。
- `backend/app/literature_maps/infrastructure/store.py`
  - schema v3 增量迁移：preview/job、mutation idempotency、节点墓碑及保存关联边；旧库通过 `ALTER TABLE` 补列。
  - owner-scoped preview 创建/读取、revision-CAS apply、每批20/总200校验、remove/restore 原子写入；恢复只复活显式墓碑并恢复已保存边。
  - preview/apply/remove/restore 的持久幂等结果和 SQLite 事务边界均在 store 内完成。
- `backend/app/literature_maps/application/service.py`
  - topic/references/citations/refresh preview；候选使用服务端 metadata snapshot，预览不改节点集。
  - apply 仅接受当前 preview 的已验证新候选；引用方向保持引用者→被引用者；请求缓存复用既有 graph cache seam。
  - refresh apply 只更新允许的 metadata，保留位置、group、document/download 状态；remove/restore 委托原子 store。
- `backend/app/api/routes_literature_maps.py`
  - 新增 preview、preview GET/apply、node remove/restore 路由与固定错误映射；响应沿用 `literature-map-v1` envelope。
- 新增能力命名测试：
  - `tests/literature_maps/test_map_expansion.py`
  - `tests/literature_maps/test_map_revision_conflicts.py`

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_revision_conflicts.py` | 0 | 5 passed |
| `.venv/bin/python -m pytest -q tests/literature_maps` | 0 | 95 passed |
| `.venv/bin/python -m ruff check backend/app/api/routes_literature_maps.py backend/app/literature_maps` | 0 | passed |
| `.venv/bin/python scripts/check_test_naming.py` | 0 | passed |
| `.venv/bin/python -m pytest --collect-only -q tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_revision_conflicts.py` | 0 | 5 collected，无 collecting error |
| `git diff --check` | 0 | passed |

精准测试覆盖：预览不改图、持久 job/preview GET、选择性 apply、CAS 冲突、幂等重放、引用方向、墓碑 remove/restore、revision 持久化、owner/store 既有回归。

## 风险与未完成项

- 本轮没有真实 API E2E、外部 provider 调用或服务重启复核；因此不能替代 Task04 独立 backend-reviewer/backend-tester 和主会话的真实验收。
- refresh 当前保存现有节点的服务端快照并给出字段差异容器；没有新增 provider metadata 端点，不会把 provider 缺失误判为删除。
- preview 计算沿用现有服务 client/cache seam；真实运行时的限流、provider 部分失败和异步执行仍需独立复审确认，未在测试中伪造成功。
- 工作区有其他 agent 的 frontend/README 改动；本交付只涉及上列 backend/map 路由和测试文件，没有处理或覆盖它们。

## 产物与下一步

- 进展日志：`.codebuddy/agent-logs/spec-043/task-04/backend-dev/20261019-230242.md`
- 建议主会话先读取本报告和实际 diff，再交给独立 backend-reviewer/backend-tester；真实 API/部署留给主会话验收门禁。

## 2026-10-20 续接修复记录

主会话复核指出的合同缺口已在原实现上做最小增量补齐：

- refresh 现在复用既有 Semantic Scholar `batch` metadata seam，并对当前明确 S2 身份有界查询引用关系；只记录真实 metadata/关系新增差异，provider 缺失仅保留 warning，不把缺失当删除。
- refresh apply 会按快照补回已验证的图内 citation 边；节点 position、group、document、download 状态仍由 store 更新白名单保护。
- 运行时存在 executor 时 preview 先落盘 queued job，计算在后台执行；job claim、`preview:calculate` checkpoint、有限 60 请求预算、request cache 和进程恢复均复用已有 SQLite/CAS 边界。已完成 checkpoint 在恢复时直接重放，不重复 provider 计算。
- restore 响应补齐持久 completed job；stop/delete 后晚到 preview worker 不得通过 stopped/deleted 地图检查。

续接精准验证：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_revision_conflicts.py` | 0 | 9 passed |
| `.venv/bin/python -m pytest -q tests/literature_maps` | 0 | 99 passed |
| `.venv/bin/python -m ruff check backend/app/literature_maps backend/app/api/routes_literature_maps.py tests/literature_maps/test_map_expansion.py` | 0 | passed |
| `.venv/bin/python scripts/check_test_naming.py` | 0 | passed |
| `git diff --check` | 0 | passed |

新增测试证明：真实 fake `batch` 返回非空 refresh metadata diff、布局/分组/导入句柄保护、queued executor、重开恢复和已有 preview checkpoint 不重复计算。仍未进行真实 provider/API、部署或提交；交独立复审前保持 PASS_WITH_LIMITATIONS。

## 2026-10-20 P1 修复追加

独立 backend-review 指出的四个阻断分支已做最小增量修复：

- `delete_map` 在删除 worker job 前先删除其 preview 子行，避免 SQLite 外键回滚；保留 deleted/stopped owner guard，晚到 worker 仍不能复活地图。
- retry 只把 `retryable=true` 的 failed units 写回 queued job；混合失败会丢弃不可重试单元，全部不可重试时返回稳定 `MAP_NO_RETRYABLE_UNITS`，HTTP 固定 409，不再重入队 `INVALID_RESPONSE` 或预算耗尽单元。
- refresh 将 metadata `batch` 与 graph 请求共享同一个持久 60-request budget；cache hit 不计数，checkpoint/job counts 持久化 `provider_request_count`。60 个已有节点的边界实测为 1 次 batch + 59 次 graph，总计 60，带 `MAP_GRAPH_BUDGET_EXCEEDED` warning。
- restore 保留 saved edge tombstone，并只在 source/target 都 active 时插边；A/B 同时墓碑时只恢复 A 不产生边，显式恢复 B 后才恢复原边。

本轮精准验证：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_job_recovery.py tests/literature_maps/test_map_api_errors.py tests/literature_maps/test_map_job_store.py tests/literature_maps/test_map_store.py` | 0 | 42 passed |
| `.venv/bin/python -m pytest -q tests/literature_maps` | 0 | 104 passed |
| `.venv/bin/ruff check backend/app/literature_maps/application/service.py backend/app/literature_maps/infrastructure/store.py backend/app/api/routes_literature_maps.py tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_job_recovery.py tests/literature_maps/test_map_api_errors.py` | 0 | passed |

验证仍限于真实 SQLite + fake provider；没有真实外部 provider、PDF、生产数据库、部署或提交。Task04 仍需独立复审与主会话验收门禁，不能据此宣称最终完成。

## 2026-10-20 refresh 空选择合同修复

复现并修复了独立验收报告指出的真实 SQLite/API 组合缺口：refresh apply 的合法
`selected_candidate_ids=[]` 现在只从服务端持久 preview diff 推导全部允许的节点，实际写入 metadata 与已验证的图内新增 citation 边，并递增 revision；不会按客户端字段清空关系或扩大新节点批次。

- provider 返回缺失作者、年份、venue、abstract、citation count 时，refresh 预览保留本地已有值；关系 provider 缺失/失败/空页只产生 warning，不删除已有边。
- store refresh 更新白名单仅包含 metadata 字段，不覆盖 external identity、source URL、provenance/import diagnostics、catalog/document/download 状态、position/group；关系变更也参与 revision CAS，job 持久化 `updated_count` 与 `relation_count`。
- refresh apply 增加节点 identity 再核对，防止冻结 preview 后节点身份漂移；空选择超过 20 个差异节点不受“新增节点批次 20”限制，但仍受 owner/revision/tombstone 守卫。

本轮精准验证：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest tests/literature_maps/test_map_expansion.py -q` | 0 | 15 passed |
| `.venv/bin/python -m pytest tests/literature_maps -q` | 0 | 108 passed |
| `.venv/bin/ruff check backend/app/literature_maps/application/service.py backend/app/literature_maps/infrastructure/store.py tests/literature_maps/test_map_expansion.py` | 0 | passed |

新增组合证据覆盖：HTTP POST refresh preview → 空选择 apply → GET 节点 → 关闭并重开 SQLite；幂等重放不重复递增，过期 revision 不写；metadata 非空 diff 实际落库，关系新增落库；provider 缺字段不清空本地值，已有关系不因空/失败响应删除。未发起真实 provider/PDF/API 部署调用，未提交；需主会话独立复审后再验收。
