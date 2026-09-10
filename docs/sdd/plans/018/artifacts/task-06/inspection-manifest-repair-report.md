# Spec018 Task06：索引完成后切片检查清单修复报告

## 结果状态

```text
task=06-inspection-manifest-repair
result=IMPLEMENTED-AND-TARGETED-VERIFIED
canonical_upload_index_manifest=pass
canonical_missing_manifest_requeue=pass
legacy_claim_compatibility=pass
full_regression=not-run-by-request
```

上传接口此前已经能把 v1/v2 向量写入 Qdrant 并把状态更新为 `indexed`，但这条路径没有发布 `InspectionManifest`。切片检查接口遇到清单缺失时只写入 claim，没有实际 worker，因此页面会一直停留在“生成中”或看不到切片。

## 改动文件

- `backend/app/knowledge_base/infrastructure/index.py`
  - canonical 文档（带 `document_id` 与 `source_sha256`）先通过现有 PDF/Markdown provenance parser 和 `build_source_provenance_bundle` 生成一次 chunks。
  - Qdrant 与 manifest 复用同一批 `Chunk`；v2 不在 manifest 阶段再次调用 LLM，避免两次切分结果不一致。
  - 直接索引 payload 补充 `document_id`、`source_sha256`，并在索引成功后发布对应版本的 manifest。
  - manifest 发布后刷新现有 generation digest；旧调用未提供源摘要时保留原有兼容 payload 与索引路径。
- `backend/app/api/routes_kb.py`
  - canonical 文档缺少 manifest 时，提交已有 `submit_document_reindex(document_id, chunker)` 单线程任务，任务完成后由索引路径发布 manifest。
  - 无 source hash 的 legacy/test 记录继续使用原 claim-only 202 语义；generation gate、稳定错误码和重复领取冲突语义保持不变。
- `tests/test_kb_document_reindex.py`
  - 新增 canonical Markdown 重建测试，验证 manifest chunk 文本与 Qdrant 写入 payload 同批一致，并验证 source hash/文档身份进入 payload。
- `tests/test_kb_document_routes.py`
  - 新增缺失 manifest 时 canonical 文档实际排队重建测试；确认不遗留 claim 文件。

后端代码文件仅修改 2 个；未修改前端、Qdrant 真实数据或用户原件。

## 决策依据

1. 检查器的事实来源必须是实际索引的切片快照，不应在 GET 请求中临时切片或伪造锚点。因此 canonical 索引在同一流水线内构建 bundle、写向量并发布 manifest。
2. `build_source_provenance_bundle` 已包含既有 PDF/Markdown parser、v1/v2 chunker 与 source-anchor-v2 映射；直接复用它避免创建第二套切片/锚点实现。
3. v2 的 LLM 结果不可在索引后重新生成，否则可能因非确定性或服务状态变化造成 manifest payload mismatch。新路径只调用一次 bundle builder，并把返回 chunks 同时提供给 Qdrant 和 manifest。
4. manifest 缺失属于派生数据缺失。对于拥有完整 immutable source hash 的 canonical 文档，使用已有 reindex worker 补齐；没有 source hash 的 legacy 记录没有安全依据，继续保留 claim 并等待正式迁移，避免伪造历史索引关系。

## 验证命令、退出码与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `python -m py_compile backend/app/knowledge_base/infrastructure/index.py backend/app/api/routes_kb.py` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/index.py backend/app/api/routes_kb.py tests/test_kb_document_reindex.py tests/test_kb_document_routes.py` | 0 | `All checks passed!` |
| `git diff --check` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/test_kb_document_reindex.py tests/test_kb_document_routes.py tests/test_kb_services.py` | 0 | **118 passed**，5 个既有 PyMuPDF deprecation warnings |

按用户要求未运行全量回归测试，也未执行真实 Qdrant 全库重建。

## 风险与停止条件

- 现有旧记录若没有 `source_sha256`，仍不会被自动伪造 manifest；需完成正式迁移或显式重建后才可进入 source-anchor-v2 检查器。
- v2 仍受已有 LLM 可用性和降级语义影响；本修复保证 manifest 使用实际同批 bundle chunks，不新增模型调用。
- 本轮未连接真实用户数据做重建；主 Agent 应在审查 diff 后重启服务，并用一个已完成索引的 canonical 文档请求 inspection，确认返回 200 且 `chunks` 非空。

## 主 Agent 后续动作

1. 审查 `index.py` 的 payload 字段与现有 generation marker 约束，确认只发布 canonical 文档 manifest。
2. 重启正在运行的本地服务以加载后端改动。
3. 对用户的 `2105.07447.pdf` 或新上传且已完成索引的文档调用 `/api/kb/documents/{document_id}/inspection?chunker=v1`；若此前无清单，首次请求应为 202，随后应为 200 且包含非空 `blocks/chunks/anchors`。
4. 再按需为 v2 请求同一接口，并确认页面选择文件/版本后能看到切片。

## 时间、模型与工具统计

- 开始：2026-09-10 22:56（Asia/Shanghai）
- 结束：2026-09-10 23:05（Asia/Shanghai）
- 总耗时：约 9 分钟（不含主 Agent 后续运行时验证）
- 角色/模型：backend-dev，临时 Luna xhigh
- Token：当前工具环境未提供精确统计
- 工具：读取角色/技能/必要代码，apply_patch，定向 pytest、py_compile、ruff、diff 检查

## 进度日志

`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-225615.md`
