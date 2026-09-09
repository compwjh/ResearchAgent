# Spec018 Task06 backend-tester 当前实现验收报告

## 结论

```text
isolated_function_gate=PASS
production_cutover=BLOCKED / NOT EXECUTED
real_qdrant_touched=false
real_data_or_user_sources_touched=false
business_code_or_tests_modified_by_tester=false
```

当前 FinalizeBundle integration 与 retire fail-closed 实现通过定向后端回归、静态检查和独立临时故障探针。所有探针只使用 FakeQdrant、不联网 SDK stub 和一次性临时目录；没有连接真实 Qdrant、读取/写入真实 `data/kb`、用户索引、用户原件或生产服务。

## 验证命令与结果

| 检查 | 退出码 | 真实结果 | 耗时 |
|---|---:|---|---:|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_document_foundation.py` | 0 | **49 passed** | pytest 6.02s；wall 约 6.49s |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/infrastructure/candidate_index.py backend/app/knowledge_base/infrastructure/manifest_store.py backend/app/knowledge_base/rebuild_index.py tests/test_kb_candidate_rebuild.py tests/test_kb_document_foundation.py` | 0 | 通过 | 约 0.06s |
| `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/infrastructure/candidate_index.py backend/app/knowledge_base/infrastructure/manifest_store.py backend/app/knowledge_base/rebuild_index.py tests/test_kb_candidate_rebuild.py tests/test_kb_document_foundation.py` | 0 | `All checks passed!` | 约 0.01s |
| `git diff --check` | 0 | 通过 | 约 0.03s |
| `PYTHONPATH=. .venv/bin/python /tmp/spec018_task06_backend_probe.py` | 0 | **9/9 probes passed** | wall 约 2.57s |

临时探针脚本只存在于 `/tmp`，每个 case 的 FakeQdrant/临时目录均由 `TemporaryDirectory` 自动清理。

## 独立探针覆盖

| 场景 | 观测与断言 |
|---|---|
| alias create before-failure → 新 service `resume-switch` | 首次返回 `INJECTED_FAILURE`、状态保持 `switching`、live bundle/marker 未写入；新 service 恢复后 `completed` 且 generation marker 可读。 |
| alias create post-failure → 新 service `resume-switch` | 首次返回 `INJECTED_POST_FAILURE`；恢复后 alias 指向新候选、旧 collection 被 retire、状态 `completed`。 |
| marker write failure → 新 service `resume-finalize` | marker 原子写注入 `ATOMIC_WRITE_FAILED`，状态 `finalize_pending` 且 marker 不存在；恢复后 `completed`、marker 可读。 |
| FinalizeBundle tamper | 修改 staged bundle 但不更新 `bundle_sha256`；恢复返回 `FINALIZE_BUNDLE_HASH_MISMATCH`，进入 `finalize_pending`，不生成 marker。 |
| no-op retire | 授权方法和删除方法均谎报成功但保留目标 collection；返回 `RETIRE_EFFECT_NOT_OBSERVED`，状态 `switching`，finalizer 未调用，未继续 finalize。 |
| delete 后 topology unknown | 删除后 fresh inventory 注入失败；返回 `ACTION_RESULT_UNKNOWN`，状态 `switching`、observed=`unknown`，finalizer 未调用。 |
| dry-run 全写 spy | `ensure_collection/upsert_document/delete_collection/create_alias/delete_alias` 写计数均为 0，embedding 调用为 0，runtime 目录未创建。 |
| 正常 retire + finalize | 旧 alias target 删除、新 alias 指向候选、FinalizeBundle marker 写入，最终状态 `completed`。 |
| 构建失败状态 | v2 LLM 缺失返回 `V2_RULES_ONLY_LLM_NOT_USED`，状态为 `failed` 或 `cleanup_pending`，finalizer 未调用且 generation marker 不存在。 |

## 隔离功能门判定

**PASS。** 当前代码和测试共同证明：

- alias before/post failure 后，stage bundle 能被新 service 读取并恢复，不依赖首进程内存；
- FinalizeBundle 读取会校验 schema/hash/run/candidate/alias/fingerprint，篡改 fail-closed；
- marker 写入失败进入 `finalize_pending`，恢复路径幂等，marker 仍为最后提交物；
- retire 删除后必须读取 fresh topology，并证明目标 collection 不存在且没有 alias 引用；no-op 与未知结果不会进入 `finalizing`/`finalize`/`completed`；
- dry-run 对 embedding、collection、alias、metadata/source/manifest/runtime/lock 均保持零写；
- 正常 retire/finalize 路径可完成，失败状态不会调用 finalizer。

## 生产 cutover 仍阻塞的原因

本报告只给隔离功能门 PASS，不构成真实索引替换授权。当前仍必须保持 `NO-GO`，原因是：

1. `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` 当前仍是 `review_status=baseline_frozen`，17/17 entry 为 `open`，13 个 required test 中 12 个为 `pending`；不能改为 `verified`，也不能放行真实 dry-run、`--confirm-replace`、alias/Collection 写删。
2. 尚无真实 Qdrant 的 alias 原子切换、retire 删除 after-effect、网络中断/结果未知、cleanup 和 topology 漂移证据；本轮 FakeQdrant/stub 只证明隔离协议。
3. 尚无停服维护窗口、服务占用检查、正式 metadata/source 集合前后 hash 对账、真实候选 v1/v2 dense+sparse 查询和重启后的 generation gate 验证；因此不能声称生产索引或 marker 已更新。
4. Task04/Task06 前置审计列出的旧 upload/import/reindex/delete/startup closure 仍未收口；当前 49 项定向测试不能替代那些缺失或 pending 的入口边界测试。

## 边界与交接

- 未修改业务代码、测试或真实数据；工作树中 `candidate_rebuild.py`、`tests/test_kb_candidate_rebuild.py` 和既有 Task06 报告的未提交状态属于本轮开始前已有范围，需主 Agent 统一复核 diff。
- 进度日志：`.codebuddy/agent-logs/spec-018/task-06/backend-tester/20260910-015138.md`。
- 本报告：`docs/sdd/plans/018/artifacts/task-06/backend-test-current-report.md`。

