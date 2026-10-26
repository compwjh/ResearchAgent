# Spec032 登录恢复冻结清单复核与同步

> 当前收口状态：本次 inventory 窄门已完成并由独立 reviewer GO；它不改变 Spec032 整体暂停状态。

- 日期：2026-10-26（Asia/Shanghai）
- 角色：backend-dev
- 范围：只核对 `tests/kb/test_kb_upload_closure_matrix.py` 的冻结 inventory 门禁；不改登录恢复业务逻辑，不删除或弱化断言，不触碰生产数据、Qdrant、KB、服务部署或 Git 提交。
- 关联实现：[`2026-10-26-login-recovery-implementation.md`](./2026-10-26-login-recovery-implementation.md)
- 关联评审：[`2026-10-26-login-recovery-review.md`](./2026-10-26-login-recovery-review.md)
- 关联回归：[`2026-10-26-login-recovery-test.md`](./2026-10-26-login-recovery-test.md)

> 本次 inventory 窄门已完成：独立复审 GO，精确 gate `1 passed`；它只同步冻结清单，不代表 Spec032 整体完成，整体仍暂停。

## 门禁用途与注册范围

`test_inventory_hashes_are_stable_and_write_entrypoints_are_registered` 同时承担三项不可替代的闭包证明：

1. 逐项按冻结清单重算八个受控文件的 SHA-256，并重算排序摘要 `inventory_digest`；
2. 从矩阵 entry 注册写入口，再对受控文件 AST 中带 `upload/save/upsert/index/delete/reindex/import/startup/task` 的函数名做漏项检查；
3. 检查 `application.py`、`routes_kb.py` 不得直接导入/调用已退休写 helper，健康检查不得触发写操作。

本次没有改动矩阵 entries、写入口集合、退休 helper 集合、hash 比对、digest 比对或 AST/调用断言。

## 漂移逐项核对

### `backend/app/api/routes_paper.py`

该文件的工作树变化仅为登录恢复计划已授权的三行：在 `_paper_snapshot_for_item` 完成 item/batch 存在性检查后调用 `service.get_item_snapshot_candidates(item_id)`，快照可用时直接返回，从而在搜索 TTL 过期后仍优先使用已校验的 durable snapshot。`git diff --unified=0` 未发现其它 routes_paper 变更属于本次漂移。

- 冻结旧值：`44f344f8ced34f0dbfd310ffd9189ddc0ee3a4c8c8fcdb3d1ccb4bb0607508af`
- 当前实际值：`1525df74f0da9de1f9cb71e5304cad3414a4b52701da0b0e20c837ca99f4333f`
- 入口集合：未新增或删除；仅修改既有 `_paper_snapshot_for_item` 的调用顺序。

### `backend/app/knowledge_base/infrastructure/index.py`

该文件另有已独立评审/回归通过的 Spec018 reindex-entry 增量，证据见 `docs/sdd/plans/018/2026-10-26-reindex-entry-backend.md`、`docs/sdd/plans/018/2026-10-26-reindex-entry-backend-review.md` 和 `docs/sdd/plans/018/2026-10-26-reindex-entry-backend-test.md`。它不是登录恢复业务代码，不能盲目忽略其 inventory 漂移：

- 冻结旧值：`066dcbc027aa04f7d3a192d2a07f0d7466108d0e867d0987e3903e2faa1db952`
- 当前实际值：`536ef36bd0493e52b37c842331379f75a59765e3a7a3e4859bab0bff7b0919e1`
- 与 `HEAD` 的 AST 函数集合比较：唯一新增的 token 命中函数为 `_verify_index_snapshot`；既有写入口集合无新增、无删除。
- `_verify_index_snapshot` 只读取显式目标 collection 的 point 集合并校验 payload，不写 Qdrant、metadata、manifest 或 generation marker；因此将它加入测试内明确的只读 allowlist，而不是注册为写入口。原有 hash、AST、退休调用和 health 写调用断言全部保留。

其余六个冻结文件逐项匹配，未做批量重写：

```text
backend/app/main.py                                      MATCH
backend/app/api/routes_kb.py                             MATCH
backend/app/knowledge_base/application.py                MATCH
backend/app/knowledge_base/infrastructure/store.py       MATCH
backend/app/knowledge_base/infrastructure/tasks.py       MATCH
backend/app/paper_discovery/application/paper_import.py   MATCH
```

## 冻结证据更新

仅同步以下证据字段：

- `routes_paper.py` SHA-256 → `1525df74f0da9de1f9cb71e5304cad3414a4b52701da0b0e20c837ca99f4333f`
- `infrastructure/index.py` SHA-256 → `536ef36bd0493e52b37c842331379f75a59765e3a7a3e4859bab0bff7b0919e1`
- 依据八个当前实际 SHA 按值排序后重算 `inventory_digest` → `643b081a9fe5493e2da9baaaa5d5f31a6fe9ad1f7586d9bae54da17c3ce90187`

`inventory_git_revision` 保持原值 `8b0cde1`：当前证据包含未提交工作树中的已授权变更，不能把当前 `HEAD=70b1af1f` 冒充为包含这些变更的提交。没有批量改写未漂移条目。

## 验证结果

运行解释器：`/Users/wjh/ResearchAgent/.venv/bin/python`。

| 命令 | 结果 |
|---|---|
| `python -m pytest -q tests/kb/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered` | `1 passed`，退出码 0 |
| `python -m pytest -q tests/kb/test_kb_upload_closure_matrix.py tests/kb/test_kb_index_publication_contract.py` | `7 passed`，退出码 0 |
| `python scripts/check_test_naming.py` | `test naming check passed`，退出码 0 |
| `python scripts/check_test_layout.py` | `test layout: ok`，退出码 0 |
| `python -m pytest --collect-only -q tests/kb/test_kb_upload_closure_matrix.py tests/kb/test_kb_index_publication_contract.py` | `7 tests collected`，退出码 0，无 collection error |
| `git diff --check -- docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json tests/kb/test_kb_upload_closure_matrix.py` | 退出码 0 |

未运行生产服务、真实 API POST、真实登录/浏览器、真实 Qdrant/KB 写入、部署或 Git commit/push。

## 最终门禁 inventory 独立审阅（backend-reviewer）

- 日期：2026-10-26（Asia/Shanghai）
- 审阅范围：主目录 `/Users/wjh/ResearchAgent` 当前候选的 inventory 最小更新；不修改代码、测试、真实记忆、部署或 Git。
- `backend/app/api/routes_paper.py` 相对 `HEAD` 仅有已授权的 3 行 durable snapshot 优先调用；未发现额外路由漂移。
- `backend/app/knowledge_base/infrastructure/index.py` 的发布校验增量与既有 Spec018 后端复审/回归报告一致。AST 独立核对显示 `_verify_index_snapshot` 只通过 `_read_document_chunker_points` 使用显式 collection 的 `collection_exists` 与 `scroll` 读取点集，并做 ID、身份、payload 和数量校验；未调用 Qdrant/metadata/manifest/generation 的写操作。其余 helper 调用也未命中 delete/upsert/update/insert/write/create/set/drop 等写操作词。
- `tests/kb/test_kb_upload_closure_matrix.py` 仅新增 3 行 `_verify_index_snapshot` 只读 allowlist，`git diff --numstat` 为 `3 0`；原有 hash、digest、AST 写入口登记、退休 helper 导入/调用和 health 无写调用断言均保留。
- 矩阵当前两项更新值复核通过：`routes_paper.py` SHA `1525df74f0da9de1f9cb71e5304cad3414a4b52701da0b0e20c837ca99f4333f`；`infrastructure/index.py` SHA `536ef36bd0493e52b37c842331379f75a59765e3a7a3e4859bab0bff7b0919e1`；八项排序摘要 `643b081a9fe5493e2da9baaaa5d5f31a6fe9ad1f7586d9bae54da17c3ce90187`。

### 独立验证

使用 `/Users/wjh/ResearchAgent/.venv/bin/python` 运行精确 inventory gate：

```text
PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false OTEL_SDK_DISABLED=true \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/kb/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered
```

结果：`1 passed in 2.31s`，退出码 0。独立 AST 核对结果：`inventory_hashes=8 verified`、`registered_write_candidates=complete`、`mutator_calls=none`；目标 diff `git diff --check` 通过。

### 最终结论

**Verdict: GO（Spec032 inventory 门禁最小更新）。** 未发现弱化安全断言、漏登记写入口或将有副作用 helper 错列为只读 allowlist 的问题；无新增 P0/P1。该结论只覆盖本 inventory 复核，不改变 Spec038 memory review 结论，也不替代 Spec032 的最终全量回归、真实 E2E、部署和收口门禁。

## 窄修收口说明

本文件所涉 inventory 同步已完成并作为登录恢复窄修的支撑证据；Spec032 整体暂停状态、认证后 resume/download/import 未验证边界保持不变。
