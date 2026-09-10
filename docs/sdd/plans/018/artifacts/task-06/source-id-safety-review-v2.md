# Task06 源 ID 安全修复独立复评 v2

## 评审结论

`NO-GO（发现控制字符门禁缺口）`。

本次修复已正确关闭上一轮发现的路径分隔符/点段问题：`/`、`\\`、`.`、`..`
及嵌套路径会在 `_load_metadata()` 阶段以 `METADATA_INVALID` 拒绝，且拒绝发生在
`_sha256()` 读取源文件之前。当前 9 个真实元数据记录的 32 位十六进制 ID 也都
保持原值通过校验。`_source_path()` 的优先级和 legacy 回退行为符合预期：安全
且存在的 `stored_name` 优先；没有 `stored_name` 时，存在的安全 `file_name` 保留；
展示名不存在时复用 `resolve_paper_path()` 回退到 `{document_id}.pdf`。

但 `_safe_id()` 仍只拒绝 `ord(char) < 32`，并且先执行 `strip()`。因此 ASCII
DEL (`U+007F`) 和 C1 控制字符 (`U+0080`–`U+009F`) 可出现在 ID 中，部分前后位置
的 C0 控制字符还会被静默裁掉，而不是拒绝。Task06 要求源 ID 的控制字符
fail-closed；在修复并补充回归测试前，不得执行真实 Qdrant 切换。

## 复评范围

只读核对：

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
- `tests/test_kb_candidate_rebuild.py`
- `docs/sdd/plans/018/artifacts/task-06/source-id-safety-fix-report.md`
- `docs/sdd/plans/018/artifacts/task-06/source-resolution-fix-review.md`

未修改业务代码、测试代码、真实 `data/kb`、Qdrant、服务进程或外部资源，未发起
网络请求。复评报告是本次唯一新增文件。

## 已确认的正确行为

1. `_load_metadata()` 先调用 `_safe_id(record_id(item))`，所以无效 ID 在源路径
   解析和哈希读取前被拒绝。
2. `../escape`、`sub/escape`、Windows 风格反斜杠路径、`.` 和 `..` 都返回
   `METADATA_INVALID`；目录外 sentinel 没有被读取。
3. `stored_name` 和 `file_name` 的 basename 检查保持现有安全语义；有效且存在
   的 legacy `file_name` 不会被错误替换。
4. 当展示名不存在时，`_source_path()` 调用共享的 `resolve_paper_path()`，不在
   candidate rebuild 内复制 legacy 命名策略。
5. 真实现有的 9 个文档 ID 均通过 `_safe_id()`，没有误伤当前知识库记录。

## 发现的问题与复现证据

对 `_safe_id('x' + chr(code) + 'y')` 的只读探针结果：

| 字符类别 | 示例 | 当前结果 | 期望 |
|---|---|---|---|
| C0 控制字符（中间位置） | `U+0000`、`U+000A`、`U+001F` | 拒绝 | 拒绝 |
| ASCII DEL | `U+007F` | 接受 | 拒绝 |
| C1 控制字符 | `U+0080`、`U+0085`、`U+009F` | 接受 | 拒绝 |

此外，`strip()` 会把前后位置的制表符、换行符等字符去掉并继续接受，例如
`'\\t' + 'x'` 变成 `'x'`。这会把损坏元数据静默规范化，不能满足“控制字符必须
拒绝”的明确契约；建议先检查原始字符串中的控制字符，再做（如仍需保留的）
空白校验，或直接禁止会改变 ID 的裁剪。

## 验证命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py -k 'metadata_document_id_must_be_a_portable_basename or legacy_id_named_source or source_path_preserves_existing_legacy_file_name'` | 0 | 5 passed，48 deselected |
| `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 0 | 53 passed，5 warnings |
| `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| 只读 `_safe_id()` 控制字符与现有 ID 探针 | 0 | 现有 9 个 ID 全部通过；DEL/C1 未拒绝，确认门禁缺口 |

## 阻塞与建议

1. 收紧 `_safe_id()` 的控制字符判定，至少覆盖 C0、DEL 和 C1；不要让
   `strip()` 在校验前静默吞掉控制字符。
2. 增加 `U+007F`、`U+0080`、`U+009F` 以及前后 C0 控制字符的回归测试，并确认
   `_preflight()` 在 `_sha256()` 前以 `METADATA_INVALID` fail-closed。
3. 修复后重新执行本报告中的全部命令，由另一名独立 reviewer 复评；复评 GO 后
   才能继续真实 dry-run。该报告不授予真实 Qdrant 切换许可。

## 主 Agent 后续动作

- 不执行 `--confirm-replace`。
- 让实现 Agent 仅修复 `_safe_id()` 与对应隔离测试，保持当前 source resolver
  和真实数据不变。
- 独立复评通过后，再恢复 Task06 的真实 dry-run 门禁流程。

## 执行数据

- 开始时间：2026-09-10 11:33（Asia/Shanghai，约）
- 结束时间：2026-09-10 11:35:42（Asia/Shanghai）
- 总耗时：约 3 分钟
- 模型：`gpt-5.6-luna`，`high`（本次临时分派）
- token / 工具调用统计：当前子 Agent 环境未提供可靠统计，未伪造填报。
