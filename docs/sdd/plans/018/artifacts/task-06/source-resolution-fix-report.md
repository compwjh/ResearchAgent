# Task06 source resolution 修复报告

## 结果状态

`PASS（隔离验证）`

真实知识库原件未改动，未连接或写入 Qdrant，未发起网络请求。修复解决了
dry-run 对旧记录的 `SOURCE_MISSING` 误报：当 `stored_name` 为空、`file_name`
只是展示名且不存在时，重建流程现在复用既有 `resolve_paper_path`，回退到
`{document_id}.pdf`。

## 改动文件

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - `_source_path` 保留安全 basename 校验和 canonical `stored_name` 优先级。
  - 对没有 `stored_name` 的旧记录，只有在安全的 `file_name` 实际存在时才使用它。
  - `file_name` 不存在时调用 `resolve_paper_path(record, papers_dir)`，兼容
    `{document_id}.pdf` 旧布局。
- `tests/test_kb_candidate_rebuild.py`
  - 增加人类可读 `file_name` + 仅存在 `{paper_id}.pdf` 的真实样本式 dry-run。
  - 增加既有安全 `file_name` 命中行为回归测试。

## 决策依据

- `store.resolve_paper_path` 是现有论文物理路径策略的唯一共享入口，不能在
  candidate rebuild 中复制一套 legacy 命名规则。
- canonical `stored_name` 继续作为权威物理文件名；不因其缺失而猜测其他文件。
- 旧 `file_name` 仅在 basename 安全且文件确实存在时使用，避免把展示名误当成
  文件名；否则按现有 store 策略回退到 `document_id.pdf`。
- 不修改真实 `data/kb`、元数据、Qdrant、服务进程或任何外部资源。

## 测试命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py -k 'legacy_id_named_source or existing_legacy_file_name'` | 0 | `2 passed, 48 deselected` |
| `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 0 | `50 passed` |
| `git diff --check` | 0 | 通过 |

测试中的 PDF 写入发生在 pytest 临时目录，dry-run 没有创建 runtime 目录或执行
任何 Qdrant 写操作。

## 风险与阻塞

- 本修复只覆盖源文件路径解析；真实 PDF 是否全部可解析、embedding、候选
  Collection、alias 切换和 finalize 仍需由 Task06 生产门禁验证。
- 源文件目录中的符号链接语义沿用既有 `resolve_paper_path`/读取链路，本次不扩展
  安全模型。
- 真实 dry-run 需由主 Agent 在确认服务停机、锁空闲且其他生产门禁满足后执行。

## 主 Agent 后续动作

1. 复核本 diff 和本报告，并由独立 reviewer/backend-tester 复核路径安全与 fallback。
2. 在服务保持停止且不改动真实原件的前提下重新运行真实 dry-run：
   `./.venv/bin/python -m backend.app.knowledge_base.rebuild_index --dry-run`
3. dry-run 通过后再依据 Task06 的授权和基线快照执行真实 `--confirm-replace`。

## 执行数据

- 开始时间：2026-09-10 11:24（Asia/Shanghai，约）
- 结束时间：2026-09-10 11:28:20（Asia/Shanghai）
- 总耗时：约 4 分 20 秒
- 模型：`gpt-5.6-luna`，`high`（本次临时分派）
- token / 工具调用统计：当前子 Agent 运行环境未提供可靠统计，未伪造填报。
