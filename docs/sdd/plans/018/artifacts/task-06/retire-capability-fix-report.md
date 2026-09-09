# Spec018 Task06-B Retire capability fail-closed 修复报告

## 结论

```text
result=PASS
scope=isolated backend tests and temporary directories only
real_data_or_qdrant_touched=false
```

已修复 Task06-B 审计发现的 CandidateIndexPort retire authorization 绕过：service 不再把“授权方法可调用 + topology 可读”当作删除成功。每次 retire 删除后必须重新读取 fresh topology，并同时证明目标 collection 已不存在、且没有任何 alias 仍引用该目标；no-op/无效删除稳定返回 `RETIRE_EFFECT_NOT_OBSERVED`，fresh topology 不可读稳定返回 `ACTION_RESULT_UNKNOWN`，均不会进入 `finalizing`、`finalize` 或 `completed`。

## 代码与测试改动

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - 为 `_action` 增加 retire 目标 postcondition 参数。
  - retire action 的 fresh topology 保留完整观察摘要，并检查目标 collection 与所有 alias target。
  - after-observation 缺失时统一持久化 `ACTION_RESULT_UNKNOWN`；目标仍存在或仍被 alias 引用时持久化 `RETIRE_EFFECT_NOT_OBSERVED`。
  - `_retire_authorized` 在受控授权和删除后启用上述 postcondition；失败停留在 `switching`，不继续 finalize。
- `tests/test_kb_candidate_rebuild.py`
  - 新增恶意/弱 port 空授权 + no-op delete 回归：目标 collection 保留、finalizer 未调用、状态不完成。
  - 新增删除后 topology 读取失败回归：返回 `ACTION_RESULT_UNKNOWN`，不伪造完成态。
  - 既有 FakeQdrant 正常物理 current/旧 alias retire 回归继续覆盖删除成功路径。

## 验证记录

| 检查 | 退出码 | 结果 | 耗时 |
|---|---:|---|---:|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_document_foundation.py` | 0 | **49 passed** | 约 6.8s wall（pytest 6.02s） |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/infrastructure/candidate_index.py tests/test_kb_candidate_rebuild.py` | 0 | 通过 | 约 0.10s |
| `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/infrastructure/candidate_index.py tests/test_kb_candidate_rebuild.py` | 0 | All checks passed | 约 0.10s |
| `git diff --check` | 0 | 通过 | 约 0.10s |

## 风险与边界

- 未访问真实 `data/kb`、真实 Qdrant、用户原件或生产服务；本报告不构成真实 Collection 切换/删除授权。
- 修复保留 current collection、unknown collection、dry-run 零写和现有 CandidateIndexPort allowlist 保护；未修改 `candidate_index.py` 的真实 Qdrant 调用面。
- 真实 Qdrant 网络中断、服务端删除 after-effect 和 closure matrix 仍需独立 Task06-C/D 门禁验证。

## 主 Agent 后续动作

1. 复核本报告及两处实现/测试 diff，确认只包含 Task06-B retire fail-closed 范围。
2. 汇总 backend reviewer/tester 证据，继续保持真实 Qdrant 与 production cutover 阻塞，直至 closure matrix 和维护窗口门禁完成。

