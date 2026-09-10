# Task06 源文件解析修复独立评审

## 评审结论

`NO-GO（发现路径逃逸门禁缺口）`。

本次修复正确解决了“旧记录的 `file_name` 是展示名、实际原件使用
`{document_id}.pdf`”这一真实 dry-run 阻塞，且没有在测试中修改真实
`data/kb`、Qdrant 或网络资源。但 `_source_path()` 在进入共享
`resolve_paper_path()` 的 id 回退时，没有验证 `document_id` 是安全的
basename；当前 `_safe_id()` 也只限制控制字符和长度。因此恶意或损坏元数据
中的 `document_id=../escape` 会被解析为 `papers/../escape.pdf`，重建流程可能
读取配置目录外的文件。Task06 的生产门禁明确要求 basename/path traversal
防护，故在修复该缺口并补回归测试前不能将本修复判为 GO，也不能执行真实
索引切换。

## 已核对文件

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - `_source_path()`：`stored_name` 优先；无 `stored_name` 时安全且存在的
    `file_name` 优先，否则调用 `resolve_paper_path()`。
  - `_load_metadata()`：生成 `document_id`，但 `_safe_id()` 当前未拒绝路径
    分隔符。
- `backend/app/knowledge_base/infrastructure/store.py`
  - `resolve_paper_path()`：只校验 `stored_name` basename，id 回退直接拼接
    `{paper_id}.pdf`。
- `tests/test_kb_candidate_rebuild.py`
  - 新增 legacy id 命名原件 dry-run 样本，以及已有 legacy `file_name` 命中
    回归。
- `docs/sdd/plans/018/artifacts/task-06/source-resolution-fix-report.md`
- `docs/sdd/plans/018/task-06-legacy-backfill-and-resilience.md`

## 验证记录

| 命令/检查 | 退出码 | 结果 |
|---|---:|---|
| `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py -k 'legacy_id_named_source or existing_legacy_file_name'` | 0 | `2 passed, 48 deselected` |
| `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/infrastructure/store.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| 只读 `_source_path({'document_id': '../escape', 'stored_name': None, 'file_name': None})` 探针 | 0 | 返回 `papers/../escape.pdf`，确认路径逃逸缺口 |

## 正确部分

- `stored_name` 非空时作为 canonical 物理文件名，非法绝对路径和带目录
  的 basename 返回 `SOURCE_PATH_INVALID`。
- 没有 `stored_name` 时，安全且实际存在的 `file_name` 继续兼容旧布局。
- 展示名不存在时复用既有 `resolve_paper_path()`，没有在重建模块复制第二套
  `{document_id}.pdf` 命名策略。
- 固定样本在临时目录内生成 PDF；报告声明的真实数据零副作用边界得到遵守。

## 阻塞与建议

1. 在 `_safe_id()` 或共享 `resolve_paper_path()` 入口建立统一的 id basename
   校验，至少拒绝 `/`、`\\`、`.`、`..`、空值和控制字符；保持稳定的
   `METADATA_INVALID` 或 `SOURCE_PATH_INVALID` 错误码。
2. 增加 candidate rebuild 回归：`document_id=../escape`、绝对/Windows
   风格路径和 `stored_name`/`file_name` 组合均必须 fail-closed，且不会读取
   `papers_dir` 外的文件。
3. 重新运行本评审中的定向测试、`py_compile` 和 `git diff --check`，再由独立
   reviewer 复核后，才重新执行真实 dry-run。不得通过手动重命名、删除或覆盖
   `data/kb` 原件绕过该门禁。

## 改动范围与真实数据声明

- 本次评审只新增本报告；未修改业务代码、测试代码、`data/kb`、Qdrant、
  服务进程或外部资源。
- 未执行网络请求、真实 dry-run 或 `--confirm-replace`。

## 执行数据

- 开始时间：2026-09-10（Asia/Shanghai）
- 结束时间：2026-09-10（Asia/Shanghai）
- 总耗时：约 5 分钟
- 模型：`gpt-5.6-luna`，`high`（本次临时分派）
- token / 工具调用统计：当前子 Agent 环境未提供可靠统计，未伪造填报。
