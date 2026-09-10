# Task06 源 ID 路径安全修复报告

## 结果状态

`PASS（隔离验证）`

修复了候选重建对文档 ID 的路径逃逸缺口。文档 ID 现在必须是可移植的单一
basename；空值、`.`、`..`、控制字符、`/`、`\\` 以及
`Path(name).name != name` 的值都会以 `METADATA_INVALID` 拒绝。这样旧记录
回退到 `{document_id}.pdf` 时不会读取 `papers_dir` 之外的路径。

## 改动文件

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - 收紧 `_safe_id`，统一覆盖文档 ID 与运行 ID 的 basename 边界。
- `tests/test_kb_candidate_rebuild.py`
  - 增加 `../escape`、`sub/escape`、Windows 风格 `\\escape` 的 fail-closed
    回归测试。
  - 测试确认拒绝发生在源文件哈希读取前，且目录外 sentinel 文件保持不变。

## 决策依据

- `_load_metadata` 是文档 ID 进入 `_source_path` 和既有
  `resolve_paper_path` 回退逻辑的统一入口，因此在 `_safe_id` 建立边界即可
  避免重复实现路径策略。
- 明确拒绝反斜杠是为了不依赖当前 POSIX 行为，保证账本在其他 IDE/平台上
  仍使用同一 basename 契约。
- 合法的单段 ID 行为不变；错误使用既有 `METADATA_INVALID` 语义，保持维护
  CLI 的稳定错误分类。

## 测试命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py -k 'metadata_document_id_must_be_a_portable_basename or legacy_id_named_source or source_path_preserves_existing_legacy_file_name'` | 0 | 5 passed，48 deselected |
| `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 0 | 53 passed |
| `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 数据与范围声明

未修改真实 `data/kb`、Qdrant、服务进程或外部资源；未发起网络请求。测试仅在
pytest 临时目录创建 sentinel 文件和元数据。

## 主 Agent 后续动作

1. 复核当前代码 diff 与本报告，并由独立 reviewer 复核 basename/path traversal
   语义。
2. 在其他 Task06 生产门禁满足后重新运行真实 dry-run；本报告本身不授予真实
   Qdrant 切换许可。

## 执行数据

- 开始时间：2026-09-10 11:30（Asia/Shanghai，约）
- 结束时间：2026-09-10 11:32:50（Asia/Shanghai）
- 总耗时：约 3 分钟
- 模型：`gpt-5.6-luna`，`high`（本次临时分派）
- token / 工具调用统计：当前子 Agent 环境未提供可靠统计，未伪造填报。
