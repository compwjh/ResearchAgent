# Spec018 Task06 Finalize marker replacement 修复报告

## 结果

本轮修复已完成隔离验证，结论为 `PASS`。随后在停服维护窗口完成了对既有
`finalize_pending` run 的真实恢复，未重新构建或下载原件。

## 根因

`FinalizeBundleStore.commit()` 看到 live `index-generation.json` 后，只要 marker 的
`run_id`、candidate、bundle 或 collection fingerprint 与当前 bundle 任一不一致，
就直接返回 `INDEX_FINALIZE_REQUIRED`。这把“同一 run 的幂等恢复”和“新 run 的合法发布”
混为一谈：后续重建即使已经完成候选验证、alias 切换和旧集合退休，也永远无法发布新
marker。

## 改动

- 同一 run 且同一 bundle 的 marker 继续走只读幂等路径；`require_generation()` 会再次
  校验 live metadata/manifests digest，损坏时仍 fail-closed。
- 旧 generation marker 与新 bundle 不匹配时，允许进入下一代发布流程。Qdrant alias、
  candidate 存在性、候选验证和拓扑门禁仍由 `CandidateRebuildService` 在调用 commit
  前完成；`FinalizeBundleStore` 保持文件协议边界，不直接连接 Qdrant。
- 在任何 live metadata/manifest 写入前，预先读取并校验 bundle 引用的全部 staged
  metadata、manifest hash，以及 obsolete manifest 的当前 hash。发现 staged 或清理对象
  漂移时，不写 live 文件并返回稳定错误。
- marker 仍最后原子写入，所有 live hash 复核逻辑保持不变。

## 验证

- `.venv/bin/python -m pytest tests/test_kb_document_foundation.py -q`：`10 passed`
- `.venv/bin/python -m pytest tests/test_kb_candidate_rebuild.py -q`：`67 passed`
- `git diff --check`：通过
- `py_compile`：由本轮合并前主 Agent统一执行
- 真实恢复：`LANGFUSE_ENABLED=false .venv/bin/python -m backend.app.knowledge_base.rebuild_index --confirm-replace --resume-finalize 38efa91a33154fd097c61d1c745d408f`，退出码 `0`，状态 `completed`。
- 真实结果：`papers` alias 唯一指向 `papers_rebuild_38efa91a33154fd097c61d1c745d408f`；415 points；generation marker、metadata 与 manifest hash 一致；`/api/health`、`/api/kb/health`、`/api/kb/documents?limit=5` 均 HTTP 200。

## 边界

本修复不放宽 `resume_finalize` 的候选验证：resume 路径仍先验证 run state、validation
artifact、topology digest、候选 fingerprint，并由 `CandidateRebuildService` 确认 alias
唯一指向当前候选；不满足时不会调用 commit。

## 显式替换授权（追加修复）

首版修复虽恢复了第二代 marker 替换，但直接调用 `commit()` 也能绕过编排层授权。现已
收紧为：

- `FinalizeBundleStore.commit(run_id)` 默认只允许同 run/同 bundle 幂等，不允许旧 marker
  mismatch 替换，仍返回 `INDEX_FINALIZE_REQUIRED`。
- `CandidateRebuildService._authorize_finalize_topology()` 在 finalize 前重新读取真实
  index，要求 `papers` alias 恰好唯一指向当前 candidate、candidate 恰好唯一存在、候选
  point count 与已通过的 validation 一致，且拓扑矩阵安全；通过后才调用
  `commit(run_id, allow_replace=True)`。
- alias 漂移、候选缺失、多个候选、point count 不一致或拓扑不可读都会停止，不写 live
  metadata/manifest/marker。

追加验证：foundation 与 candidate rebuild 定向测试共 `78 passed`；`py_compile` 和
`git diff --check` 均通过。

## 交接

- 修改文件：`backend/app/knowledge_base/infrastructure/manifest_store.py`、
  `tests/test_kb_document_foundation.py`
- 真实恢复已由主 Agent 完成；最终 marker、alias、metadata/manifests hash 和服务健康状态
  已写入 Task06 执行结果与 spec-status-changelog。
