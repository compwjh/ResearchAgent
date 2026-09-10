# Task 06 Dense Digest 精度调整报告

## 结论

通过。dense digest 继续采用“先单位归一化、再量化”的存储无关表示，但量化精度由 5 位调整为 4 位，以吸收 Qdrant cosine 写入/序列化后的微小读回误差。

## 改动范围

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - `_DENSE_DIGEST_DECIMALS = 4`。
  - 更新说明，明确该 digest 只容忍归一化与微小序列化误差，不放宽明显向量篡改检测。
  - build、逐点候选指纹和 validation 聚合指纹继续统一调用 `_dense_vector_digest_input`。
- `tests/test_kb_candidate_rebuild.py`
  - 增加约 `2e-6` 级 Qdrant 读回扰动仍保持相同 digest 的回归断言。
  - 保留 cosine 归一化等价性断言，并用 `0.01` 级方向变化验证明显篡改仍被检测。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `./.venv/bin/python -m pytest tests/test_kb_candidate_rebuild.py` | 0 | 66 passed |
| `./.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

未执行真实重建，符合本次任务边界。

## 决策依据

实测该样本在 5 位量化下，约 `2e-6` 读回扰动会跨越量化桶；4 位仍保持 digest 一致，而 `0.01` 级变化仍产生不同 digest。因此 4 位在当前 Qdrant cosine 读回场景下更稳，同时保留对明显篡改的检测能力。

## 风险与后续

- 量化 digest 不是逐浮点审计；它用于识别重建候选是否发生实质变化。非有限值、维度错误和结构错误仍由 validation fail-closed。
- 本报告没有证明真实 Qdrant 全量重建成功；主 Agent 仍需在服务停止、锁释放的维护窗口执行真实 rebuild，并记录 run id、validation 和运行时健康结果。

