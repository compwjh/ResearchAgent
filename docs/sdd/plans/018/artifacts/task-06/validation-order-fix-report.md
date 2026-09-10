# Task06 候选校验顺序修复报告

## 结果状态摘要

`PASS（隔离回归）`。修复了候选校验从 Qdrant scroll 结果直接计算顺序敏感 digest 的问题：每个 `(document_id, chunker)` 分组现在按 `(chunk_index, point.id)` 稳定排序后计算 payload/text/dense/sparse digest；`point_ids` 与 `chunk_indexes` 展示也复用同一顺序。

真实 Qdrant、真实索引、真实 `--confirm-replace` 均未执行。

## 改动文件

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - `_validate()` 在建立 `by_point` 后对每个分组稳定排序。
  - 顺序敏感 digest 与展示字段使用排序后的分组点。
  - 未修改 `_recompute_candidate_fingerprint()`、schema、data/kb、Qdrant 或索引代际。
- `tests/test_kb_candidate_rebuild.py`
  - 新增可控 FakeQdrant scroll 顺序回归测试；插入顺序与 scroll 顺序相反，使用多 chunk 文档验证 v1/v2 digest 不误报。
  - 调整既有 import 顺序以通过 ruff。

## 测试命令与退出码

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py::test_validation_sorts_scroll_points_before_order_sensitive_digests` | 0 | 1 passed |
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_rebuild_cli.py` | 0 | 66 passed，10.48s pytest wall（外层约 10.97s） |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | 0 | 通过 |
| `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | 0 | All checks passed |
| `git diff --check` | 0 | 通过 |

## 决策依据

- `_build()` 按 chunk 生成顺序计算 expected digest。
- `_validate()` 原先使用 `_scroll_all()` 返回顺序，FakeQdrant/Qdrant scroll 顺序不属于稳定契约，导致同一组 points 的顺序敏感 digest 可能不同。
- `_recompute_candidate_fingerprint()` 已按 `(document_id, chunker, chunk_index, point_id)` 排序，本次保持不变，避免破坏恢复路径的信任根。
- 分组中 `chunk_index` 是主排序键，`point.id` 是稳定 tie-break；展示的两个数组均从同一排序后的 points 生成，避免彼此不一致。

## 风险/阻塞

- 本次仅验证 FakeQdrant 隔离路径；真实 Qdrant 的 scroll 分页跨页顺序仍由生产维护窗口验证，但排序逻辑在 `_scroll_all()` 汇总后统一生效。
- 工作树开始时已有其他 Task06 文件未提交改动；本任务未修改或清理这些改动。
- 未执行真实 `--confirm-replace`，无生产索引或用户数据变更。

## 主 Agent 后续动作

1. 复核本报告及两处限定文件 diff。
2. 将本任务代码/测试与验收产物纳入同一 Spec018 Task06 提交，避免验收文档游离。
3. 按既有 Task06 生产门禁继续决定真实候选运行；不得将本隔离 PASS 解释为真实 Qdrant cutover 授权。

## 时间、模型与工具统计

- 开始：2026-09-10 约 16:08（Asia/Shanghai）
- 结束：2026-09-10 16:14（Asia/Shanghai）
- 总耗时：约 6 分钟
- 模型：`qwen3.8:27b-mlx`（backend-dev 角色配置）
- Token 统计：当前工具环境未提供精确 token 用量
- 工具统计：约 19 次工具调用（读取、补丁、测试与静态检查）

## 进展日志

`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-validation-order-fix.md`
