# Task 06 清理产物缺失修复报告

## 结果状态和摘要

- 结果状态：通过。
- 修复了验证阶段失败后已经写入 `validation.json`、但尚未写入 `topology.json` 的清理路径。
- 候选已不存在时，先通过实时拓扑确认候选未被 alias 引用且不存在竞争候选，再幂等标记为 `cleaned`。
- 候选仍存在时，必须先通过候选点数和独立重算的候选指纹校验，校验通过后才允许删除；校验失败则保持候选和 `cleanup_pending` 状态，拒绝越权删除。
- `resume_switch` 与 `resume_finalize` 仍使用原严格产物校验，没有放宽生产切换门禁。

## 改动文件

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - 新增失败清理专用的 `_load_cleanup_validation_artifact()`。
  - `cleanup_failed()` 仅在 `topology.json` 缺失且严格加载返回产物不匹配时使用该专用校验。
  - 候选存在时统一进行结构校验和指纹重算；候选不存在时保持幂等清理。
- `tests/test_kb_candidate_rebuild.py`
  - 增加缺失 topology 且候选已删除的回归测试。
  - 增加缺失 topology 且候选仍存在时严格验证后删除的回归测试。

## 测试命令、退出码和结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest tests/test_kb_candidate_rebuild.py -q` | 0 | 65 passed |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 产物路径

- 本报告：`docs/sdd/plans/018/artifacts/task-06/cleanup-artifact-fix-report.md`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-000000.md`

## 决策依据

验证产物的写入顺序允许 `validation.json` 先于 topology 产物落盘；因此清理阶段必须区别“缺少 topology 的已知 pre-switch 失败窗口”和“完整切换/恢复路径”。放宽仅封装在 `cleanup_failed()` 中，并保留运行状态、候选集合、文件 SHA、点数、拓扑摘要及候选内容指纹约束。

## 风险与阻塞

- 未执行真实生产重建，符合任务要求；主 Agent 需要在服务停止、Qdrant 锁释放的维护窗口再次运行真实重建。
- 当前工作树可能同时包含 Task06 其他子任务的并行改动；本子任务未修改 schema、数据或其他文件。

## 主 Agent 后续动作

1. 复核本报告与两处限定文件的 diff，并与其他 Task06 改动合并测试。
2. 清理已知失败运行目录后重新执行真实 rebuild。
3. 完成服务健康检查和全量回归，再更新 Task06 文档并进行本地提交。

## 开始、结束和总耗时

- 开始：2026-09-10 00:00（Asia/Shanghai）
- 结束：2026-09-10 00:06（Asia/Shanghai）
- 总耗时：约 6 分钟

## 可用时记录模型、token 和工具调用统计

- 模型：Luna high（临时任务分派）
- token：未提供
- 工具调用统计：读取/定位 4 次，补丁 5 次，测试与静态校验 3 次，报告/日志落盘 2 次。
