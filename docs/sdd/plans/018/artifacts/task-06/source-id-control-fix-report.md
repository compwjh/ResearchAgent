# Task06 源 ID 控制字符门禁修复报告

## 结果状态和摘要

`GO`。`_safe_id()` 现在保留既有 `str(value or "")` 转换语义，但在裁剪前后值不一致时直接以 `METADATA_INVALID` fail-closed，并拒绝所有 Unicode `C*` 控制/格式字符，覆盖 ASCII C0、DEL（U+007F）和 C1（U+0080–U+009F）。无效 ID 在 `_load_metadata()` 阶段被拒绝，因此不会读取源文件。

## 改动文件

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - 引入 `unicodedata`。
  - `_safe_id()` 拒绝原始值被 `strip()` 改变的边界。
  - 使用 Unicode 类别 `C*` 拒绝控制/格式字符。
- `tests/test_kb_candidate_rebuild.py`
  - 新增 U+007F、U+0085、U+009F、中间/边界控制字符和普通首尾空格回归覆盖。
  - 断言返回 `METADATA_INVALID` 且 `_sha256()` 未被调用。

## 验证命令、退出码和结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py -k 'metadata_document_id'` | 0 | 9 passed，50 deselected |
| `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 0 | 59 passed，5 warnings |
| `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 决策依据

- 保留 `str(value or "")`，避免改变现有合法调用方的类型转换行为。
- 不再静默裁剪边界；任何原始 ID 与裁剪结果不同的值都视为损坏元数据。
- 使用 Unicode `unicodedata.category(char).startswith("C")` 覆盖 C0、DEL、C1 及不可见格式控制字符；当前真实 32 位十六进制文档 ID 不受影响。

## 风险与阻塞

- 可能拒绝此前依赖首尾空白或不可见格式字符的异常 ID；这是源文件路径/运行目录边界的明确 fail-closed 要求。
- 未修改真实 `data/kb`、Qdrant、网络或服务进程。
- 未发现阻塞。

## 主 Agent 后续动作

1. 由独立 reviewer 复评本修复并运行针对性测试。
2. 复评 GO 后重新执行 Task06 真实数据的只读 dry-run。
3. dry-run 通过且用户已授权时，才进入真实 Qdrant 切换门禁。

## 执行数据

- 开始时间：2026-09-10（Asia/Shanghai）
- 结束时间：2026-09-10（Asia/Shanghai）
- 总耗时：约 10 分钟
- 模型：`gpt-5.6-luna`，`high`（本次临时分派）
- token / 工具调用统计：当前子 Agent 环境未提供可靠统计，未伪造填报。
