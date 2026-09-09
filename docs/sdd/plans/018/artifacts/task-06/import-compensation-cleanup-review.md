# Spec018 Task06：import compensation cleanup fail-closed backend review

## 评审元数据与范围

- 角色：`backend-reviewer`（Task06，Luna high）
- 时间：2026-09-10（Asia/Shanghai）
- 评审对象：`import-compensation-cleanup-failclosed-report.md`、`import-compensation-implementation-report.md`、当前 diff，以及 `backend/app/paper_discovery/application/paper_import.py`、`backend/app/knowledge_base/infrastructure/store.py`、`tests/test_import_compensation.py`、`tests/test_paper_import.py`。
- 只读约束：未修改业务代码、测试、matrix 或 spec；未访问真实 `data/kb`、用户原件、Qdrant、服务、网络或 `confirm-replace`。
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-063200.md`

## 结论

```text
cleanup_failclosed_hardening_gate=GO
new_P0=0
new_P1=0
allow_commit_as_hardening_subgate=true
import_compensation_gate=NO-GO
production_cutover=NO-GO
real_data_or_qdrant_touched=false
```

本轮修复已关闭此前 `_cleanup_download` 的“检查后仍按 pathname unlink”竞态：该函数现在对任何带路径的下载结果只返回 `cleanup_pending`，完全不执行单文件 `unlink`。显式 `temp_dir` 保持 caller-owned，`temp_dir=None` 使用本次创建的私有 attempt root，并且只有调用方成功记录 root token、当前对象仍为非 symlink 目录且运行平台声明 `shutil.rmtree` 具备 symlink-attack resistance 时才整体回收。source compensation 在无法证明 compare-and-unlink 时保留 source/metadata orphan 并记录 `cleanup_pending`，不误报完成；ledger 写入包含临时文件 fsync、原子替换和父目录 fsync。

因此允许把本轮 hardening 作为明确“已关闭 cleanup fail-closed 子门”的增量提交，但不得把它宣称为整个 import compensation 或 Task06 生产门已完成。

## 逐项核对

| 检查项 | 裁决 | 证据 |
|---|---|---|
| `_cleanup_download` 无单文件 pathname unlink | **PASS** | `paper_import.py:182-207` 只读取返回路径并返回 `cleanup_pending`；`attempt_root`、递归 inventory、file token 仅保留为兼容/审计参数，不授权单路径删除。 |
| explicit caller `temp_dir` 绝不清理 | **PASS** | `paper_import.py:412-418` 仅解析、创建并记录 caller root；finally 只调用 `_cleanup_download`（不删路径），不调用 `_cleanup_attempt_root`。 |
| private root 只在安全条件下整体回收 | **PASS** | `paper_import.py:395-411,210-238,491-492` 记录 root dev/ino；回收前要求 `avoids_symlink_attacks`、`lstat` 为真实目录且 token 相等；symlink、替换目录或无法取证时保留。 |
| root/content symlink 不越界删除 | **PASS** | 使用 `shutil.rmtree` 的 symlink-attack-resistant 实现；root 先 `lstat` 且拒绝 symlink。隔离测试验证被替换为外部 symlink 时 root 与外部 sentinel 均保留。 |
| `temp_dir=None` 无正常泄漏 | **PASS** | `paper_import.py:395-407` 每次建立 `paper-import-*` child root；成功、下载异常和导入异常均进入 finally，拥有 token 时整体移除 root，父 `article_download_dir` 保留。 |
| source compensation fail-closed | **PASS** | `store.py:283-327` 使用 `O_NOFOLLOW`、regular-file、nlink、dev/ino 和完整 hash 校验；fd 关闭后不再尝试 pathname 删除，统一写 `cleanup_pending`，只在 source 已不存在时允许完成。replacement 注入测试保留 replacement。 |
| metadata compensation 语义 | **PASS（fail-closed）** | source 仍在时 metadata record 与 source 一并保留；source 已不存在时才按本次 `document_id` 移除 metadata，再将 capability 标记 completed。metadata 失败路径按新 UUID 过滤，不按 caller path/paper id 删除既有资源。 |
| compensation ledger durability | **PASS** | `store.py:153-173` 对临时 ledger 写入并 fsync 文件，`os.replace` 后 fsync 父目录；异常不会被转换为 completed。测试通过至少两次 fsync 的隔离断言。 |
| old tests 与新 fail-closed contract | **PASS** | `test_paper_import.py` 已将 index failure / metadata failure 断言改为保留 orphan、`cleanup_pending`；explicit temp root 成功和直接委托测试均断言下载文件保留。 |
| public/API secret boundary | **PASS（本轮回归）** | `PaperImportResult.to_dict()` 只包含稳定字段和 cleanup 状态，不序列化 `resource_capability` 的 owner/token/inode；本轮未扩大 HTTP payload。 |

## P0/P1 结果

本轮 **P0=0、P1=0**。未发现会使当前 cleanup fail-closed 子门不成立的新增高严重问题。

`_cleanup_attempt_root` 的 `expected_token` 参数保留了可选兼容形态，但生产调用受 `attempt_root_owned` 守卫，只有成功记录 token 才进入回收；这不是本轮新增 blocker。后续若扩大该私有 helper 的调用面，应将 token 改为强制参数并增加“token 记录前 root 被替换”的故障注入覆盖。

## Deferred（仍阻止整体门与生产切换）

以下项目不属于本轮 cleanup 修复，必须继续留账，不得随本报告标记为完成：

1. **batch compensation**：batch failure、cancel、expired lease、retry/resume 尚未持久化并驱动 `resource_capability` / `cleanup_status`；不能证明跨 batch 或重启后的 source/metadata/vector 补偿闭合。
2. **generation binding**：`ImportResourceCapability.destination_collection` 尚未绑定并校验实际创建/索引 generation；默认 deleter 仍按补偿时 active generation 解析，不能作为向量补偿安全证明。
3. **private-root creation race hardening**：`mkdtemp` 返回后再 `lstat` 取 token，若未来 threat model 要覆盖 parent-directory 并发替换，应改为更强的创建/句柄级 ownership 证明；当前 root 被替换后已 fail-closed，不跟随 symlink。
4. **真实生产门**：closure matrix、真实 `data/kb`、用户原件、Qdrant、服务维护窗口和 `confirm-replace` 均未执行；production cutover 继续 NO-GO。

## 验证证据

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py tests/test_paper_import.py` | **21 passed**，退出码 0 |
| `.venv/bin/python -m pytest -q tests/test_import_compensation.py -k 'cleanup or compensation'` | **11 passed**，退出码 0 |
| `.venv/bin/ruff check backend/app/paper_discovery/application/paper_import.py backend/app/knowledge_base/infrastructure/store.py tests/test_import_compensation.py tests/test_paper_import.py` | 通过 |
| `.venv/bin/python -m py_compile backend/app/paper_discovery/application/paper_import.py backend/app/knowledge_base/infrastructure/store.py tests/test_import_compensation.py tests/test_paper_import.py` | 通过 |
| `git diff --check` | 通过 |
| `shutil.rmtree.avoids_symlink_attacks` 隔离检查 | `True` |

## 提交裁决

- **本轮 cleanup hardening 子门：GO。** 可作为增量 hardening 提交，提交说明必须明确只关闭 cleanup fail-closed，不得声称整个 import compensation 已闭合。
- **整体 import compensation / Task06 生产门：NO-GO。** batch compensation、generation binding、root creation race 的后续加固和真实生产门仍需独立交接与验收。
- **允许的提交边界：** 仅允许纳入本轮已实现的 cleanup fail-closed、private-root 生命周期、ledger fsync 及对应测试/报告；禁止借此变更 closure matrix、spec 状态或连接真实资源。

**最终裁决：cleanup hardening 子门 GO；整体生产切换 NO-GO。**
