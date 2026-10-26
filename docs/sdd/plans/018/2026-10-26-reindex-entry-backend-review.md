# Spec018 KB 重建入口后端独立复审

> 当前收口状态：本次单文档发布一致性后端窄修已完成；以下历史 GO 与未覆盖边界保留，最终范围签字见 [`../../reviews/018-acceptance-review.md`](../../reviews/018-acceptance-review.md)。

复审日期：2026-10-26
复审分支：`codex/fix-kb-reindex-contract`
复审范围：只评审 `backend/app/knowledge_base/infrastructure/index.py` 与 `tests/kb/test_kb_index_publication_contract.py` 的当前实际 diff；不修改业务代码，不执行生产 Qdrant 写入、网络/模型调用、真实 reindex 或部署。

## 复审结论

**GO（P0=0，P1=0，P2=0；仅限本次后端重建入口增量）**。

当前改动满足本任务的删除与发布前一致性契约：删除失败不再被吞掉；真实 Qdrant client 的当前文档+chunker point 集合会在 manifest 发布前按显式 collection 读取，并严格校验 point ID、连续 chunk index、身份/来源字段、文本/页码/section 和 `is_citation` 类型；不一致时以稳定的 `INDEX_FINALIZE_REQUIRED` 失败，不发布 ready/partial。未发现高置信度安全、数据泄漏、范围扩大或真实 Qdrant API 兼容性问题。

## 通过项与证据

- `delete_paper_chunker()` 的异常会传播到 `index_paper_chunker()` 的稳定 `QDRANT_UNAVAILABLE` 失败路径；删除失败时不会执行 upsert，也不会进入 manifest/ready/partial 发布。
- `_read_document_chunker_points()` 使用传入的 `destination`，过滤条件严格为 `paper_id + chunker`，分页读取且不扩大到其他文档或其他 chunker。
- `_verify_index_snapshot()`（`index.py:529-588`）拒绝缺失/重复/非连续 index、错误 deterministic point ID、错误 document/source/chunker、payload 内容漂移、非布尔 `is_citation` 以及额外目标 point；通过后将核对过的实际 payload 传入 manifest builder。
- 5→3 缩容测试确认旧尾点被清理，同时保留其他文档和同文档另一 chunker；额外 point、payload 漂移和删除异常均有 fail-closed 测试。
- 真实本地 `QdrantClient(path=<临时目录>)` 实测通过 `scroll`、过滤、point ID 校验和 2-point snapshot 核对；同一真实 client 实测删除后仅保留其他文档/另一 chunker 点。临时目录与项目生产数据无关。
- 代码保留了既有 write-only test double 的兼容分支（无 `scroll` 时返回 `None`）；真实 `QdrantClient` 暴露 `scroll`，因此生产 canonical 路径不绕过一致性门禁。该边界与后端交接计划一致。

## 独立验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --noconftest tests/kb/test_kb_index_publication_contract.py -q` | 0 | 5 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --noconftest tests/kb/test_kb_index_publication_contract.py tests/kb/test_kb_tasks.py tests/kb/test_kb_pdf_safety_publication.py tests/kb/test_kb_document_reindex.py -q` | 0 | 50 passed，5 warnings |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest --noconftest tests/kb/test_kb_services.py tests/kb/test_kb_application_boundary.py tests/kb/test_kb_document_boundary.py -q` | 0 | 99 passed，4 subtests passed，5 warnings |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/index.py tests/kb/test_kb_index_publication_contract.py` | 0 | 通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_naming.py` | 0 | 通过；无 spec/task 编号测试名 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m ruff check backend/app/knowledge_base/infrastructure/index.py tests/kb/test_kb_index_publication_contract.py` | 0 | All checks passed |
| `git diff --check`（目标文件）与冲突标记扫描 | 0 | 通过 |

测试使用 `--noconftest` 是为了绕开当前默认入口缺少 `langchain_ollama` 的环境收集限制；这不改变本次目标测试结果。第二组测试的 OTEL localhost 导出重试属于既有测试观测器，未进行产品网络调用，且退出码为 0。

## 未覆盖与交接边界

- 本复审没有执行真实生产 reindex，也没有验证指定文档当前 297 manifest 与生产 Qdrant 的最终数量；该项仍由 root 按 Spec018 计划执行一次受控真实 API E2E，并落盘请求、响应、实体 ID、终态和产物路径。
- GO 不代表 Spec018 已完成，也不替代跨端验收、最终全量回归、部署和验收签字。
- 未修改任何业务源文件或测试文件；本报告为本角色独立复审产物。

## Review Summary

| Severity | Count | Status |
|---|---:|---|
| P0 / CRITICAL | 0 | pass |
| P1 / HIGH | 0 | pass |
| P2 / MEDIUM | 0 | pass |

Verdict: **GO** — 本次后端重建入口增量可进入后续受控真实验收。
