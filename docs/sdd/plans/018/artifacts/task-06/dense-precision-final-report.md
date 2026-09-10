# Task 06 Dense Digest Precision 修复报告

- 角色：backend-dev
- 模型：临时 Luna xhigh
- 结果状态：成功
- 摘要：将 Qdrant cosine 归一化及浮点读回噪声的 dense digest 量化精度从 4 位调整为 3 位；保留对 0.01 级明显向量篡改的检测。
- 开始时间：2026-09-10 17:28:00 +0800（约）
- 结束时间：2026-09-10 17:29:40 +0800
- 总耗时：约 2 分钟（不含并行子代理等待）

## 改动文件

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - `_DENSE_DIGEST_DECIMALS = 3`。
  - 更新常量注释和 `_dense_vector_digest_input` 文档，说明 3 位精度用于容忍 Qdrant 归一化/序列化读回误差。
- `tests/test_kb_candidate_rebuild.py`
  - 更新 dense digest 回归测试注释，明确 3 位容忍语义。
  - 明确断言 0.01 级向量变化仍必须产生不同 digest。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `./.venv/bin/python -m pytest tests/test_kb_candidate_rebuild.py -q` | 0 | 66 passed，5 warnings |
| `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | 0 | 通过 |
| `git diff --check -- backend/app/knowledge_base/infrastructure/candidate_rebuild.py tests/test_kb_candidate_rebuild.py` | 0 | 通过 |

## 决策依据

诊断报告已确认 payload、text、sparse 和 anchor digest 一致，失败集中在 1024 维 dense 向量的 Qdrant 归一化/浮点序列化读回边界。3 位量化吸收已观测的约 `1e-4` 级存储噪声，同时现有 0.01 级 tamper 断言仍失败闭环，避免改用过宽的相似度阈值掩盖真实篡改。

## 风险与阻塞

- 风险：3 位量化比 4 位降低了 dense digest 的敏感度；当前针对性测试确认 0.01 级变更仍可检测。
- 未执行真实重建，按任务要求留给主 Agent 在 Qdrant 锁释放且服务停止的维护窗口执行。
- 未修改 schema、索引数据、服务配置或其他文件。

## 主 Agent 后续动作

1. 审阅本报告和两份指定文件的 diff，并与滚动顺序修复一起运行候选测试。
2. 清理失败 run `204517871840429f8d8ab830dbf42572`。
3. 在服务停止状态执行一次真实 rebuild，记录 run、validation 和 generation marker。
4. 若真实重建成功，再启动服务并验证 `/api/health`、`/api/kb/health`。

## 产物路径与日志

- 报告：`docs/sdd/plans/018/artifacts/task-06/dense-precision-final-report.md`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910-dense-precision-final.md`

## 统计

- token 统计：当前执行环境未提供。
- 工具调用统计：当前执行环境未提供；实际执行了候选 pytest、py_compile 和 diff 检查。
