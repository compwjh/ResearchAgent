# Spec018 Task04-D backend-reviewer 最终最小复签

## 范围与约束

本轮只复核上一轮指出的 inspection claim、reindex source hash、未知文档 404，
以及 backend-tester 指出的两个统一 400 请求形状；同时核对 closure matrix 是否
仍保持事实状态。未修改业务代码、前端、用户 `data/kb`、真实 Qdrant 或 Git 历史。

## 双 verdict

### A) Task04 功能门：GO，可放行 Task05

本轮六个功能检查均已关闭，且当前工作树的定向/相关回归通过。这里的 GO 仅表示
Task04 用户可见功能门通过，不代表 production closure 已完成。

### B) Task06 production cutover/closure：NO-GO，仍然阻塞

`upload-closure-matrix.json` 仍保持 `review_status=baseline_frozen`，17/17
entry 为 `open`，13 个测试中 12 个为 `pending`。因此没有把 production closure
伪造为 `verified`。startup legacy recovery、固定 Collection/index/delete 直连、
CandidateIndexPort、paper-import 唯一边界及全库 finalize/rebuild 仍需 Task06
继续收口。

## 最小复签逐项证据

1. **inspection 真实 claim：PASS**

   manifest 缺失时 `routes_kb.py:398-431` 先计算稳定 task id，再调用
   `InspectionManifestStore.claim(document_id, chunker, owner=...)`。首次请求建立
   durable claim，重复请求遇到 `MANIFEST_CLAIMED` 后仍返回同一 202/task id，不会产生
   第二份 claim；claim 失败则收敛为 503 `MANIFEST_FAILED`。临时 TestClient probe
   结果：两次均 202、task id 相同、claim 调用路径已实际触发。

2. **reindex source hash：PASS**

   `application.py:228-237` 读取 source 后重算 SHA-256，并与 canonical metadata
   `source_sha256` 比较；不一致抛出 `SOURCE_HASH_MISMATCH`。tempfile probe 使用
   错误 metadata hash 时稳定拒绝，不再返回 `submitted=True`。

3. **未知文档 404 优先级：PASS**

   `routes_kb.py:488-495` 先检查 canonical document，再进入 generation gate。未知
   document 在未完成 generation 时仍返回 404 `DOCUMENT_NOT_FOUND`，不会被维护状态
   覆盖为 `INDEX_REBUILD_REQUIRED`。

4. **reindex 非 object 请求：PASS**

   `POST .../reindex` 的 JSON 数组/字符串/整数进入原始 body 校验，统一返回 400
   `INVALID_REQUEST`，不再返回 FastAPI 的 422 `detail`。

5. **upload 缺少 multipart file：PASS**

   canonical upload 与 legacy alias 均允许先接收空 file，再统一返回 400
   `INVALID_REQUEST`，响应不含 `detail`。

6. **closure matrix 真实性：PASS（保持未关闭）**

   matrix 仍为 17 open、12 pending、`baseline_frozen`；本轮没有修改其状态、
   inventory digest 或 evidence 欺骗放行。

## 验证命令与退出码

| 验证 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_document_routes.py tests/test_kb_routes.py` | 0 | 47 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_*.py tests/test_paper_import*.py` | 0 | 394 passed，5 warnings，29 subtests passed |
| changed backend/test 文件 `ruff check` | 0 | All checks passed |
| changed backend/test 文件 `py_compile` | 0 | 通过 |
| Draft 2020-12 `check_schema(api-schema.json)` | 0 | schema 合法 |
| inspection claim / unknown 404 / hash mismatch tempfile probes | 0 | 全部符合固定契约 |

## 后续动作

- Task05 可按当前 Task04 功能契约继续。
- Task06 必须继续完成 startup recovery、CandidateIndexPort/显式 destination、
  paper-import 单一 application 边界、删除/向量边界、全库 rebuild/finalize 与
  closure matrix 逐 entry 证据；在所有 entry closed、required tests passed、
  evidence 完整前，保持 `baseline_frozen`，不得签 production cutover。
