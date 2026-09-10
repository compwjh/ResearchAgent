# Task 06：Dense digest 稳定性修复报告

## 结果状态和摘要

通过。候选重建的 dense 向量指纹现在使用统一的存储无关规范：每个向量先做 L2 单位归一化，再量化到 5 位小数。这样兼容 Qdrant cosine collection 写入时的归一化和微小浮点差异，同时仍能识别明显的向量篡改。

## 改动文件

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - 新增 `_dense_vector_digest_input`。
  - `_build()`、`_validate()` 和 `_recompute_candidate_fingerprint()` 的 dense digest 统一使用该 helper。
  - sparse、payload 指纹及查询向量语义未改变。
- `tests/test_kb_candidate_rebuild.py`
  - 新增 cosine 归一化风格 Qdrant 回归。
  - 验证归一化前后指纹一致，并验证明显向量改变仍被区分。

## 测试命令、退出码和结果

- `./.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py` — 退出码 `0`，`66 passed`。
- `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py` — 退出码 `0`。
- `git diff --check` — 退出码 `0`。

## 产物路径

- 本报告：`docs/sdd/plans/018/artifacts/task-06/dense-digest-fix-report.md`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-dev/20260910T000000-dense-digest.md`

## 决策依据

真实重建已证明 Qdrant cosine collection 会将写入 dense 向量单位归一化，导致对原始 embedding 和读回 embedding 做精确 digest 时出现误报。五位小数量化足以吸收存储层浮点噪声，而对明显篡改仍产生不同指纹。聚合 dense digest 对每个点独立归一化，避免把多个 embedding 展平后改变语义。

## 风险与阻塞

- 量化会忽略小于约五位小数精度的变化，这是为适配 Qdrant cosine 存储语义作出的明确取舍。
- 本轮未执行真实重建；真实重建仍需在服务停止、Qdrant 锁释放的维护窗口执行。

## 主 Agent 后续动作

1. 清理失败运行 `204517871840429f8d8ab830dbf42572`。
2. 在服务停止且 `LANGFUSE_ENABLED=false` 时重新执行真实候选重建。
3. 验证状态、候选集合、alias、generation marker 和服务健康状态后，再更新 Task 06 及提交。

## 执行时间

- 开始：2026-09-10（会话时间未提供精确时分）
- 结束：2026-09-10（会话时间未提供精确时分）
- 总耗时：约 15 分钟（含一次测试反馈后的聚合输入修正）
- 模型：临时 `gpt-5.6-luna` high
- token / 工具调用统计：当前执行环境未提供可靠统计，未伪造。
