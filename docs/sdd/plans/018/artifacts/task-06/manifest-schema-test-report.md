# Spec018 Task06 Manifest Schema 回归测试报告

## 结果状态

**PASS（隔离/只读验证）**。最新 Manifest schema projection 修复通过指定后端回归、Python 编译检查、差异检查，以及 5 个 Spec018 PDF fixture + 1 个现有项目 PDF 的内存 manifest 构建。未执行真实 `--confirm-replace`，未连接或写入 Qdrant，未修改 `data/kb`、原件、metadata、manifest 或索引代际。

## 测试命令、退出码与结果

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_document_foundation.py tests/test_kb_candidate_rebuild.py` | 0 | **72 passed**, 5 个第三方 SWIG 弃用警告，8.14s |
| `tests/test_kb_provenance.py` | — | 文件不存在，未执行（`rg --files tests` 未发现） |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/inspection.py backend/app/knowledge_base/infrastructure/parse.py backend/app/knowledge_base/infrastructure/provenance.py tests/test_kb_document_foundation.py tests/test_kb_candidate_rebuild.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

定向回归按文件拆分计数为：`test_kb_document_foundation.py` 10 passed，`test_kb_candidate_rebuild.py` 62 passed。

## 真实 PDF 离线 manifest 构建

探针仅执行 `extract_pdf_provenance` → `build_source_provenance_bundle` → `build_inspection_manifest`，输出留在内存，不调用维护命令、confirm-replace、Qdrant 或 manifest store。

| 样本 | 结果 | 统计 |
|---|---|---|
| `pdf-single-column-v1.pdf` | ready | 1 页 / 3 blocks / 1 chunk / 3 anchors |
| `pdf-two-column-v1-overlap.pdf` | ready | 1 页 / 3 blocks / 2 chunks / 6 anchors |
| `pdf-v2-cross-page.pdf` | ready | 2 页 / 2 blocks / 2 chunks / 4 anchors |
| `pdf-hostile-features.pdf` | partial | 1 页 / 2 blocks / 1 chunk / 2 anchors；保留 fail-closed partial |
| `pdf-no-text-layer.pdf` | 拒绝构建 | `INDEX_REBUILD_REQUIRED`；无文本层不伪装为 ready |
| `data/kb/papers/d4dfd2a620384ad5bece27320661f8f0.pdf` | ready | 18 页 / 504 blocks / 107 chunks / 53,120 anchors |

样本计数：**6 个总样本，4 个 ready，1 个 partial，1 个预期 fail-closed**。所有可构建样本均通过 `inspection-manifest-v1` 内置 Draft 2020-12 schema 校验。现有 PDF 的 source SHA-256 为 `71f8829f2e1d36ab2695ebcf1c1697e301e429eb1aea5225981f526be98a14a1`，与只读读取到的 `data/kb/papers.json` 记录一致。

## 风险

- `tests/test_kb_provenance.py` 缺失，无法提供该文件名对应的额外回归证据；当前 provenance 路径由基础测试及真实 PDF 探针间接覆盖。
- 现有 18 页 PDF 构建 53,120 条 anchors，离线耗时约 76.3s；大规模真实全库重建的时间、内存和 Qdrant 行为仍未验证。
- Manifest block 采用显式白名单；未来 parser 新增字段不会自动进入 manifest，若字段属于冻结契约必须同步更新 projection 与 schema。
- 本报告不构成真实索引切换授权；真实 Qdrant、生产维护窗口、`--confirm-replace` 和 alias/Collection 写删仍保持 NO-GO。

## 主 Agent 后续动作

1. 将本报告与进展日志纳入 Task06 交接，复核工作树中仅有既有业务/测试修改与报告产物。
2. 由后端 reviewer 对 projection/schema 边界做独立评审，并在验收总控中汇总本轮 72 项回归与 6 个 PDF 样本结果。
3. 在 Spec018 全部生产前置门禁明确放行前，继续禁止真实 `--confirm-replace`、Qdrant 写删和索引代际提交。

## 耗时

- 开始：2026-09-10 15:41:37 CST
- 结束：2026-09-10 15:45:39 CST
- 总耗时：约 **4 分 02 秒**（其中现有 PDF 离线 manifest 构建约 76.3s）

## 进展日志

`.codebuddy/agent-logs/spec-018/task-06/backend-tester/20260910-154137.md`
