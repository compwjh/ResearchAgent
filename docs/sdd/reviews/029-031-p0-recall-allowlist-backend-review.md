# Backend Review — spec029/030/031 P0（fix/spec029-030-031-pipeline）

审查对象：未提交 4 文件（orchestrator.py + 3 测试）。评审只覆盖 backend/**。

## 六点结论

### 1. 红线是否守住（本地目录不扩大候选集）—— GO
- `orchestrator.py:220-230` `resolve_metadata`：当 `recall_allowlist is not None` 时，先 `if recall_allowlist is not None and ref_id not in recall_allowlist: return None`，resolver 只对白名单内 ID 调用；白名单外 ID 永不调 resolver，因此 resolver 返回的元数据不会进入 `effective_metadata`。
- `:286` 候选扩张要求 `ref_id in effective_metadata or (recall_allowlist is not None and ref_id in recall_allowlist)`。候选 ID 只能源自 evaluator 的 `evidence_refs`/`candidate_id` + 召回白名单，resolver 仅补元数据，绝不引入新 ID。
- 结论：本地目录只回填元数据，未参与"决定哪些 ID 是候选"，红线守住。

### 2. 聚合 vs per-candidate 区分是否正确 —— GO
- `:249` `if candidate_id and item.get("keep") is not True and item.get("verified") is not True: continue` —— 仅当 `candidate_id` 有值（per-candidate）才因 `keep`/`verified` 丢弃；聚合（`candidate_id=None`）不被 `keep=False` 整体丢弃，改由 `evidence_refs` 展开。
- `:1441` `if direct and entry.get("keep") is False: continue` —— 聚合 `direct=None` 不触发跳过；显式 per-candidate 拒绝（`direct` 有值且 `keep=False`）仍跳过。
- 两条路径语义一致。

### 3. 两条路径是否对称 —— GO（附 1 条低危建议）
- synth 路径 `:1060-1085` 与 selection/artifact 路径 `:1247-1253` 均调用 `_recall_allowlist_from_search_outputs(...)` + `self._catalog_metadata_resolver()`，绑定一致。历史"选集 0 条"成因（selection 路径未传 recall_allowlist/metadata_resolver）已修复。
- 建议（非阻塞）：selection 路径召回集取 `completed_outputs` 中全部 search-worker（`:1248-1252`），synth 路径取 `ancestors(item.work_item_id)` 内 search-worker（`:1062`）。selection 路径更宽，但仅影响报告填充（`:1261-1272`），持久化经 `:1464 allowed_candidates` 独立兜底，无 fail-open。

### 4. 是否引入第二套实现 —— GO
- `_recall_allowlist_from_search_outputs` `:93-116` 纯字段抽取（candidates/evidence_refs/citation_allowlist），无检索逻辑。
- `_catalog_metadata_resolver` `:1350-1384` 复用 `getattr(self._adapter,"_store").get_catalog_paper`（即 `PaperDiscoveryStore.get_catalog_paper`），与 spec029 search fallback 同一本地目录出口，无第二套检索实现。

### 5. 失败是否 fail-closed —— GO
- `recall_allowlist` 默认 `None`，`metadata_resolver` 默认 `None`（`_validated_evaluator_candidates` `:185-186`）。旧 2 参调用（仅 outputs+catalog_metadata）→ `:286` 要求 `ref_id in effective_metadata`，走"必须有元数据"严格路径，未被放宽。当前两个调用点（`:1080`、`:1244`）均显式传两者。
- `:1464` `_persist_agent_selections` 以 `allowed_candidates`（`:978-1025` 由 search-worker candidates/evidence_refs 构建，不查本地目录）兜底，白名单外 ID 一律丢弃。
- resolver 为 `None` 时 `:227` 返回 None，召回到的 ID 仍接受（空元数据），元数据属补充展示不门控候选（与 test_local_directory_missing_accepts_with_empty_metadata 一致）。

### 6. 测试质量 —— GO（无弱化）
- `test_validated_evaluator_candidates_metadata_backfill.py`：含 fail-closed 用例（test_id_outside_recall_allowlist_rejected_even_if_directory_has_it）、模型元数据不外泄（test_metadata_never_taken_from_evaluator_model_output 断言 MODEL-FAKE-* 不在记录）、per-candidate 拒绝仍丢（`:172-189`）、真实聚合 `keep=False` 形状（`:121-169`）。断言为逐字/集合比较，无恒真。
- `test_agent_work_item_failure_visibility.py`：将 `evidence_refs` 由 `catalog:paper-1` 改为 `catalog:paper-not-recalled`，属构造修正（新设计下被召回 ID 缺元数据也会展开，须用白名单外 ID 才能触发 NO_VALIDATED_EVIDENCE），断言 `synth.status=="failed"` / `error_code=="NO_VALIDATED_EVIDENCE"` 未弱化。
- `test_agent_selection_persistence.py`：新增用例断言为具体 ID 集合与 `evidence_level=="catalog"`，并含 replace_selections 抛异常不崩流水线用例。

## 其他低危建议（非阻塞）
- A. `_persist_agent_selections` `:1441` 仅认 `keep is False`，而 `_validated_evaluator_candidates` `:249` 还要求 `verified`。对 per-candidate 记录 `keep` 缺失 + `verified False`：synth 丢弃但 persist 落库，两条路径不一致。属历史既存（本次仅加 `direct` 守卫），建议后续统一为"显式拒绝"语义。
- B. `resolve_metadata` 在 `recall_allowlist is None` 时对任意 `ref_id` 调 resolver（`:225` 短路被跳过），存在"传 metadata_resolver 却漏传 recall_allowlist"时本地目录扩大候选集的潜藏面；当前无调用点触发，仅需在未来新增调用时留意。

## Review Summary
| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH     | 0 | pass |
| MEDIUM   | 0 | pass |
| LOW      | 2 | note |

Verdict: APPROVE（GO）—— 六点全部通过，无 P0/P1；2 条 LOW 建议非阻塞，可后续处理。
