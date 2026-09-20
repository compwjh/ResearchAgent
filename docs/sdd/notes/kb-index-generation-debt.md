# 知识库索引代次：架构债记录（P2 关闭说明）

结论：**P2 不复现，就此关闭，不做全量重建。** 本文只记录遗留的架构债。

## 交接文档当时的描述

`/api/kb/health` 报 `qdrant: false`、`chunks: 0`，主集合 `papers` 不存在。

## 当前实测（2026-09-18）

```
qdrant = True      chunks = 4527      papers = 14
embedding = True   generation.ready = True   error_code = None
```

功能完全正常，**不需要**全量重建。

## 真实成因（不是配置遗漏，也不是索引没建）

1. **空 bootstrap 是刻意设计，不是"重建跑不通"。**
   spec-020 的 BUG-05（`docs/sdd/specs/020-misc-bug-fixes.md:84-91`）明确裁决：
   首次部署时库是空的，本就无索引可"重建"，初始化应当自动完成。
   唯一写入点是 `FinalizeBundleStore._bootstrap_empty_generation()`
   （`backend/app/knowledge_base/infrastructure/manifest_store.py:612-651`），
   由上传端点以 `allow_bootstrap=True` opt-in 触发（`routes_kb.py:558-563`）。
   非空库 marker 缺失仍 **fail-closed** 抛 `INDEX_REBUILD_REQUIRED`，绝不自动 bootstrap。

2. **文档是后来陆续索引进去的。**
   bootstrap marker 提交于 `2026-09-11T09:50:21`，而 `data/kb/papers.json` 的 14 条记录
   与 `manifests/` 下 6 个文档的 v1/v2 manifest 都在其后产生。
   所有常规建索引写入都取 marker 的 `alias_target`（`application.py:223-242`
   `_active_generation_collection`，明确注释"never fall back to fixed `papers`"），
   因此数据实际落在 `papers_rebuild_empty_bootstrap` 这个集合里（storage.sqlite 54.28 MB）。

3. **marker 的 `run_id` / `bundle_sha256` / `alias_target` 永远不会更新。**
   后续写 metadata / manifest 只走 `refresh_live_digests()`
   （`manifest_store.py:434-471`），它只更新 `metadata_sha256` 与 `manifests_digest`。
   所以 marker 永久停留在 `run_id: "empty-bootstrap"` 的 bootstrap 状态。

## 遗留架构债

| 项 | 现状 | 为何不在本次修 |
|---|---|---|
| **没有 `papers` 别名** | `data/kb/qdrant/meta.json` 的 `aliases` 为 `{}` | 功能正常；补别名涉及索引拓扑变更 |
| **集合名语义错误** | 名为 `papers_rebuild_empty_bootstrap`，实际装着全量数据 | 纯命名问题，改它需要动 marker/bundle 校验 |
| **marker 停在 bootstrap 状态** | `run_id` / `bundle_sha256` 恒为 bootstrap 值 | 只有跑真实重建才会被覆盖 |

## 为什么不建议现在跑全量重建

- **从未有过"多文档"全量重建成功的记录**。历史两次真实重建
  （`docs/sdd/plans/018/task-06-legacy-backfill-and-resilience.md:229-279`）
  都只针对 **1 篇**权威文档，且该文档集合后来被 spec-020 Task07 验收"移走 `data/kb`"时挪走了。
- **静态推导会先撞 `INDEX_TOPOLOGY_AMBIGUOUS`**：当前 `active_generation=None` 不在候选集合内
  （`candidate_rebuild.py:816-821` + `topology_inventory:598-614`），未实跑验证。
- **代价不成比例**：14 篇 × (v2 LLM 判边界 + 每 chunk embedding)，量级可能是数十分钟到数小时，
  且必须停服（Qdrant 本地存储独占）。为命名整洁冒这个风险不划算。
- **重建后旧 bootstrap 集合不会被自动退休**（`_switch_and_finalize:1707-1725` 的 else 分支），
  会留下约 54 MB 孤儿集合。

建议：若要处理，另开 spec/分支专门做索引治理，不要塞进业务 PR。
