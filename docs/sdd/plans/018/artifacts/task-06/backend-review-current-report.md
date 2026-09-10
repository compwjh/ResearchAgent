# Spec018 Task06 backend-reviewer 当前修复轮评审

## 评审元数据与范围

- 角色：Task06 backend-reviewer（只读评审）
- 时间：2026-09-10（Asia/Shanghai）
- 评审对象：已提交 `c28a3e2` FinalizeBundle integration，以及当前未提交的 retire fail-closed diff
- 重点文件：`candidate_rebuild.py`、`manifest_store.py`、`candidate_index.py`、`tests/test_kb_candidate_rebuild.py`、`tests/test_kb_document_foundation.py`
- 交接材料：`task06b-preflight-audit.md`、`finalize-recovery-fix-report.md`、`retire-capability-fix-report.md`
- 约束：未修改业务代码、测试或真实数据；未访问真实 `data/kb`、真实 Qdrant 或生产服务。评审报告与进度日志属于本角色交付物。
- 进度日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-000001.md`

## 结论

```text
isolated_functional_gate=GO
new_P0=none
new_P1=none
production_cutover=NO-GO (not granted by this narrow review)
real_data_or_qdrant_touched=false
```

本轮隔离功能门可放行：默认 finalizer 已不再是 no-op；stage 在 alias 操作前完成且不写 live metadata/manifest/marker；generation marker 保持 marker-last；新 service 的 resume-finalize 可幂等完成；retire 删除 no-op 或 fresh topology 不可观测时不会进入 finalize/completed；正常 FakeQdrant 物理 current、alias current 与 dry-run 路径均无定向回归。

该 GO 只覆盖当前修复的隔离功能，不等价于 Task06-C/D 真实切换授权。Task06-B 交接材料仍记录 closure matrix 为 `baseline_frozen`、17 个 entry open、12 个 required test pending；真实 Qdrant alias/server after-effect、停服门禁、原件全集 hash、服务重启和生产 topology 仍需独立门禁，故 production cutover 继续 NO-GO。

## 逐项核对

### 1. 默认 finalizer 不再 no-op：PASS

- `CandidateRebuildService.__init__` 在未提供自定义 `finalizer` 时绑定 `_finalize_bundle`，并创建 `FinalizeBundleStore`；只有显式传入的 custom finalizer 才保留原有注入语义（`candidate_rebuild.py:529-531`）。
- `_invoke_finalize_and_commit` 对默认路径要求 finalizer 返回的 run、alias target 和 collection fingerprint 与当前验证结果一致，再写 run commit（`candidate_rebuild.py:1318-1349`）。
- 隔离成功 run 真实生成 `index-generation-v1` marker，marker 的 run、candidate alias target、bundle hash 和 collection fingerprint 与验证结果一致。

### 2. stage 在 alias 之前且不写 live：PASS

- `_validate()` 通过后、`ready_to_switch` 前调用 `_stage_finalize_inputs()`（`candidate_rebuild.py:1148-1151`）。
- stage 写入 run-scoped `.sdd/runtime/spec-018/rebuild/<run-id>/finalize/` 的 metadata、manifests、bundle；`FinalizeBundleStore.stage()` 不触碰 `data/kb` live 路径（`candidate_rebuild.py:1254-1276`、`manifest_store.py:315-367`）。
- alias switch failure 的新 service resume 测试确认 stage bundle 可从持久化目录读取，且 alias 失败时 live `data/kb` 目录尚未创建（`tests/test_kb_candidate_rebuild.py:165-178`）。

### 3. marker-last 与 live hash 校验：PASS

- `FinalizeBundleStore.commit()` 先读取并校验 staged metadata/manifests，写入并复核 live metadata/manifest，删除已验证 obsolete manifests，计算 live manifest digest，最后原子写 `index-generation.json`（`manifest_store.py:397-475`）。
- `require_generation()` 重新读取 marker 并校验 schema、live metadata hash 与 live manifest digest；默认 finalizer 在返回前再次执行该校验（`candidate_rebuild.py:1278-1316`、`manifest_store.py:480-495`）。
- 独立临时目录记录到 live 原子写顺序为 metadata → manifest → `index-generation.json`，marker 是最后一次写；现有 marker-last/idempotency 回归通过。

### 4. 新进程 resume 与幂等：PASS（隔离）

- `resume_switch`/`resume_finalize` 通过 `_resume_state()`、validation artifact、fresh topology 和 run-scoped bundle 恢复，不依赖首进程的 `_finalize_metadata` / `_finalize_manifests` 内存（`candidate_rebuild.py:1448-1502`）。
- marker 写入前失败会进入 `finalize_pending`；新 service 在 marker 缺失时重新执行 commit，marker 存在且匹配时 `FinalizeBundleStore.commit()` 直接复核并返回，不重复 live 写（`manifest_store.py:397-414`）。
- 独立临时 probe：首个 service 完成后删除 `commit.json`、将状态置为 `finalize_pending`，新 service `resume_finalize("run-test")` 返回 `completed`，marker/run/alias 一致。
- 该证据仍仅为隔离恢复，不覆盖真实 Qdrant 服务端动作或跨主机崩溃恢复。

### 5. retire fail-closed：PASS（隔离）

- 当前 diff 为 `_action()` 增加 retire target postcondition；删除回调返回后重新读取 fresh topology，目标 collection 仍存在或任一 alias 仍引用目标时返回 `RETIRE_EFFECT_NOT_OBSERVED`；topology 读取失败返回 `ACTION_RESULT_UNKNOWN`（`candidate_rebuild.py:655-713`）。
- 这两个错误都在 `_retire_authorized()` 的 action 内抛出，状态停留在 `switching`，不会调用 finalizer、不会进入 `finalizing` 或 `completed`。
- `test_noop_retire_delete_fails_closed_before_finalize` 证明 no-op delete 保留 current collection、finalizer 未调用；`test_retire_requires_fresh_topology_observation` 证明删除后 topology unknown 不伪造完成态（`tests/test_kb_candidate_rebuild.py:491-544`）。
- 正常 FakeQdrant 路径仍覆盖 physical current retire、alias current switch 后旧 collection retire，以及 post-effect alias recovery；定向回归全部通过。

### 6. dry-run 零写：PASS

- `run(dry_run=True)` 在 preflight 后直接返回 completed，不创建 runtime state、candidate collection、alias、live metadata、manifest 或 generation marker；不会调用 embedder（`candidate_rebuild.py:1391-1417`）。
- `test_dry_run_has_no_write_side_effects` 与并发 dry-run 回归中的 Qdrant write spy 均为 0，metadata 内容保持不变（`tests/test_kb_candidate_rebuild.py:67-79,326-333`）。

## 验证命令与结果

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_document_foundation.py` | 0 | **49 passed** |
| `.venv/bin/python -m py_compile`（candidate rebuild / manifest store / candidate index / 相关 tests） | 0 | 通过 |
| `.venv/bin/ruff check`（上述实现与测试） | 0 | All checks passed |
| `git diff --check` | 0 | 通过 |
| 新 service finalize resume 临时目录 probe | 0 | `completed`，marker/run/alias 一致 |
| marker 写顺序临时目录 probe | 0 | marker 为最后一次 live 原子写 |

## P0/P1 裁决

- **本轮针对的 FinalizeBundle integration 与 retire fail-closed diff：未发现新增 P0 或 P1。**
- preflight 审计中已有的 closure matrix、旧 upload/import/reindex/delete/startup 边界、真实 Qdrant/生产拓扑与停服授权问题未被本轮修复，也未因隔离测试绿灯而重新标记为关闭；它们属于 production cutover 的既有阻塞，不改变本轮窄范围 functional GO。
- 没有把本报告写成真实索引切换授权，也没有修改 `upload-closure-matrix.json` 或任何生产状态。

## 后续动作

1. 主 Agent 可将本报告作为 Task06 当前修复的 backend review 交接物，与 `retire-capability-fix-report.md`、`finalize-recovery-fix-report.md` 汇总。
2. 在 closure matrix 全部 closed、required tests 全部 passed、真实维护窗口与用户确认满足前，继续禁止 `--confirm-replace`、真实 alias/Collection 写删和生产服务验收。
3. 若扩大评审范围到 production cutover，应另行执行 Task06-B/C/D 的真实门禁与验收，不把本报告的隔离 GO 复用为 production GO。
