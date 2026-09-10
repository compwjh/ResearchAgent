# Spec018 Task06 FinalizeBundle 恢复修复报告

## 结论

```text
result=PASS
scope=isolated backend tests and temporary directories only
real_data_or_qdrant_touched=false
```

已修复 alias 切换前/后失败后新 service 实例无法恢复 FinalizeBundle 输入的问题。候选集合验证成功后，默认 FinalizeBundle 会先把 metadata 与 inspection manifests 原子 stage 到 run-scoped `.sdd/runtime/.../finalize/`，再进入 alias 切换；stage 阶段不写 live `data/kb`。恢复路径验证 bundle 的 schema、hash、run/candidate/alias/fingerprint 后才执行 commit，保留 marker-last、live metadata/manifest hash、obsolete manifest 校验和 fail-closed 行为。

## 代码与测试改动

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`
  - 在候选验证通过后持久化默认 finalizer 的 FinalizeBundle stage 输入。
  - 新 service 的 resume-switch/resume-finalize 仅消费已 stage bundle，不依赖首进程内存。
  - 增加 bundle 与当前 run payload 的一致性校验，防止错误 bundle 在 live 写入前被接受。
- `backend/app/knowledge_base/infrastructure/manifest_store.py`
  - 增加只读 `read_bundle()` 校验入口。
  - commit 后立即复核 live metadata hash，再允许生成 marker。
- `tests/test_kb_candidate_rebuild.py`
  - 增加 alias switch before-failure 的 stage 持久化、live 零写和新 service resume-switch 回归。
- `tests/test_kb_document_foundation.py`
  - 保留现有 marker-last/idempotency 回归及其写入追踪。

工作树中已有的 Task06 草稿、`docs/sdd/spec-status-changelog.md` 和 preflight 审计文件未回滚或改写。

## 验证记录

| 检查 | 退出码 | 结果 | 耗时 |
|---|---:|---|---:|
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_document_foundation.py` | 0 | **47 passed** | 约 6.17s wall（pytest 5.98s） |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/infrastructure/manifest_store.py` | 0 | 通过 | 约 0.12s |
| `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/infrastructure/manifest_store.py tests/test_kb_candidate_rebuild.py tests/test_kb_document_foundation.py` | 0 | All checks passed | 约 0.10s |
| `git diff --check` | 0 | 通过 | 约 0.10s |

失败基线：修复前相同 pytest 命令为 `45 passed, 1 failed`，失败码为 `FINALIZE_INPUT_MISSING`；修复后原有测试为 `46 passed`，加入新回归后为 `47 passed`。

## 风险与阻塞

- 未访问真实 `data/kb`、真实 Qdrant 或生产服务；本报告不构成生产 cutover 授权。
- 自定义 `finalizer` 仍按既有测试注入语义运行，不自动接管其外部持久化责任；FinalizeBundle stage 仅由默认 finalizer 路径负责。
- 工作树包含主 Agent/先前 Task06 的未提交改动，需主 Agent 在统一 diff 中复核边界后提交。

## 主 Agent 后续动作

1. 复核本报告对应 diff，确认与已存在 Task06 草稿的接口范围一致。
2. 按项目 SDD 门禁汇总 backend review/tester 证据，并决定是否补充更大范围回归。
3. 在用户授权且生产门禁满足后，再执行部署/运行时验证；本次未执行生产启动或真实索引操作。

