# Task06 manifest schema fix report

## 结果状态和摘要

PASS。修复了真实 PDF 重建在 `build_inspection_manifest` 阶段返回 `MANIFEST_SCHEMA_INVALID` 的问题。PDF provenance block 现在通过显式白名单投影到冻结 inspection manifest schema：block 顶层继续保留 `bbox` 与 `normalized_bbox`，PDF `locator` 继续使用 normalized bbox；每条 `lines` 只保留 schema 允许的 `ordinal`、`text`、`start`、`end` 字段。

真实 PDF `data/kb/papers/d4dfd2a620384ad5bece27320661f8f0.pdf` 已在只读探针中成功构建 manifest：504 blocks、1908 lines、107 chunks、53120 anchors；首个 PDF block 与 line 的字段集合均符合冻结 schema。未执行真实 `--confirm-replace`，未修改 `data/kb`、Qdrant 或索引代际。

## 改动文件

- `backend/app/knowledge_base/infrastructure/inspection.py`
  - PDF 与 Markdown block 均改为显式顶层字段白名单。
  - PDF line 显式投影为 `ordinal`、`text`、`start`、`end`，不再将 parser 的 bbox 字段带入 manifest line。
- `tests/test_kb_document_foundation.py`
  - 新增真实 fixture PDF manifest 回归测试，锁定顶层坐标、PDF locator 和 line 白名单契约。

## 测试命令、退出码和结果

- `python -m pytest -q tests/test_kb_document_foundation.py::test_pdf_inspection_manifest_projects_line_geometry_to_frozen_schema` — 退出码 0；1 passed（修复前为 `MANIFEST_SCHEMA_INVALID`）。
- `python -m pytest -q tests/test_kb_document_foundation.py` — 退出码 0；10 passed。
- `python -m pytest -q tests/test_kb_source_provenance_bundle.py` — 退出码 0；19 passed。
- `python -m pytest -q tests/test_kb_candidate_rebuild.py` — 退出码 0；62 passed。
- 真实 PDF 只读 manifest 构建探针 — 退出码 0；`manifest_ok blocks=504 lines=1908 chunks=107 anchors=53120`。
- `python -m py_compile backend/app/knowledge_base/infrastructure/inspection.py tests/test_kb_document_foundation.py` — 退出码 0。
- `git diff --check` — 退出码 0。

## 产物路径

- 实现：`backend/app/knowledge_base/infrastructure/inspection.py`
- 回归测试：`tests/test_kb_document_foundation.py`
- 本报告：`docs/sdd/plans/018/artifacts/task-06/manifest-schema-fix-report.md`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-000001.md`

## 决策依据

冻结 schema 的 `$defs.line` 明确只允许 `ordinal`、`text`、`start`、`end`，而 PDF parser 为定位诊断额外提供 `bbox`、`normalized_bbox`。因此不修改 schema、不放宽 `additionalProperties`，在 manifest 边界做显式 projection；block 顶层 bbox/normalized_bbox 属于冻结 PDF block 必需字段，必须保留。Markdown block 的 locator 与 start/end 行号逻辑保持不变。

## 风险与阻塞

- 风险：若未来 parser 新增需要进入 manifest 的字段，必须同步显式 projection 与冻结 schema；当前未知字段会被有意丢弃。
- 当前无本任务阻塞。保留 Task06/Spec018 既有真实 Qdrant、生产切换与 `--confirm-replace` 门禁，本修复不改变其放行状态。

## 主 Agent 后续动作

1. 读取本报告与进展日志，纳入 Task06 汇总交接。
2. 运行后端 reviewer/tester 的独立评审与验收；确认 candidate rebuild 主链可消费新 manifest。
3. 在所有生产前置门禁满足后，由主 Agent 决定是否进行真实候选重建；本任务本身不授权 `--confirm-replace`。

## 开始、结束和总耗时

- 开始：2026-09-10 15:29 CST（本轮任务执行起点记录）
- 结束：2026-09-10 15:38 CST
- 总耗时：约 9 分钟

## 模型、token、工具统计

- 模型：`qwen3.8:27b-mlx`（backend-dev 角色配置）
- Token 统计：当前运行环境未提供可核对的 token 用量
- 工具统计：完成上下文读取、测试先行、最小实现、真实 PDF 只读探针、定向 pytest、`py_compile` 与 diff 检查；精确工具计数未由运行时提供
