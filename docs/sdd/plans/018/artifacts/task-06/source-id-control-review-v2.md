# Task06 源 ID 控制字符修复独立复评 v2

## 评审结论

`GO`。本轮修复已关闭上一版 `source-id-safety-review-v2.md` 发现的控制字符
门禁缺口，可以继续 Task06 的真实数据 dry-run；本报告不替代真实 dry-run 或
Qdrant 切换门禁。

## 复评范围与限制

本次只读核对以下文件，并运行隔离测试/语法检查：

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
- `tests/test_kb_candidate_rebuild.py`
- `docs/sdd/plans/018/artifacts/task-06/source-id-control-fix-report.md`
- `docs/sdd/plans/018/artifacts/task-06/source-id-safety-review-v2.md`

未修改业务代码、测试代码、真实 `data/kb`、Qdrant、网络或服务进程。本报告是
唯一新增文件。

## 已确认的修复

1. `_safe_id()` 先比较原始值与 `strip()` 结果；首尾裁剪会改变 ID 时直接返回
   `METADATA_INVALID`，不会静默规范化损坏元数据。
2. `_safe_id()` 使用 `unicodedata.category(char).startswith("C")`，覆盖 Unicode
   `C*` 类别，包括 C0、ASCII DEL（U+007F）、C1（U+0080–U+009F）、不可见格式
   字符（如 U+200B/U+FEFF）、代理字符、私用字符和未分配字符；代表性探针均以
   `METADATA_INVALID` fail-closed。
3. `_load_metadata()` 在 `_source_path()` 和 `_sha256()` 之前校验文档 ID；无效
   ID 不会触发源文件读取。
4. 合法的 64 位十六进制 SHA-256 文档 ID 原样通过 `_safe_id()`，没有被修复逻辑
   改写。
5. `_source_path()` 仍保持路径安全：`stored_name` 优先，现存合法 `file_name`
   保留；展示名缺失时复用共享 `resolve_paper_path()` 的 legacy ID 文件名回退，
   未在 candidate rebuild 内复制第二套命名策略。路径分隔符、点段和非法 basename
   仍拒绝。

## 验证命令、退出码和结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py -k 'metadata_document_id or legacy_id_named_source or source_path_preserves_existing_legacy_file_name'` | 0 | 11 passed，48 deselected，5 warnings |
| `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` | 0 | 59 passed，5 warnings |
| `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| 只读 `_safe_id()` 代表性 `C*` 字符探针及 SHA-256 ID 探针 | 0 | C* 代表字符全部拒绝；合法 SHA-256 ID 原样保留 |

## 风险与后续门禁

- 使用完整 `C*` 类别会拒绝私用、代理和未分配字符，属于源 ID/路径边界的
  fail-closed 策略；当前真实哈希 ID 不受影响。
- 本复评未证明真实数据源齐全、Qdrant 拓扑可切换或 finalize 可完成；不得据此
  直接执行 `--confirm-replace`。
- 下一步按 Task06 顺序重新执行真实数据的只读 dry-run；dry-run 通过后，仍需在
  用户授权、服务停止且基线快照完成的前提下，才可进入真实 Qdrant 切换。

## 主 Agent 后续动作

1. 采纳本复评 `GO`，保留历史 `NO-GO` 报告作为问题发现记录。
2. 重新执行 `./.venv/bin/python -m backend.app.knowledge_base.rebuild_index --dry-run`。
3. 仅当 dry-run 通过后，继续 Task06 的真实切换与重启/查询验收门禁。

## 执行数据

- 开始时间：2026-09-10 11:40（Asia/Shanghai，约）
- 结束时间：2026-09-10 11:41（Asia/Shanghai）
- 总耗时：约 1 分钟
- 模型：`gpt-5.6-luna`，`high`（本次临时分派）
- token / 工具调用统计：当前子 Agent 环境未提供可靠统计，未伪造填报。
