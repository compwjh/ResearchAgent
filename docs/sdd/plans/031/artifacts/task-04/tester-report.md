# Spec031 Task04 后端验收报告

## 固定字段

- spec：031 — 动态模型路由与资源调度优化
- task：Task04 — 内存感知 Worker 扩缩与策略激活
- 角色：backend-tester
- 执行模型：Luna high（临时执行）
- 验收范围：当前工作树的后端改动与 Task04 指定验收集合；不修改业务代码、不提交/推送、不启动 Ollama、不跑全量 pytest。
- 结论：**通过（GO）**。指定回归、语法/差异检查和四项 P1 fake-probe smoke 均通过；Task04 无阻塞项。

## 命令、退出码与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest --noconftest -q tests/test_spec031_adaptive.py tests/test_spec031_shadow_observation.py tests/test_spec028_scheduler_lease_recovery.py tests/test_spec027_runtime_contract.py tests/test_spec028_runtime_contract.py tests/test_spec027_backend_research_slice.py tests/test_spec028_hitl.py tests/test_spec028_recovery_api_ui.py tests/test_spec028_scheduler_status.py tests/test_spec034_task07_backend.py` | 0 | **154 passed，5 subtests passed，3.66s** |
| `.venv/bin/python -m py_compile backend/app/platform/ollama.py backend/app/research/application/model_router.py backend/app/research/application/routing_observation.py backend/app/research/application/scheduler.py backend/app/research/application/adaptive_routing.py backend/app/research/infrastructure/research_store.py backend/app/api/routes.py backend/app/api/routes_research_routing.py tests/test_spec031_adaptive.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| `.venv/bin/python` 内联固定 `FixedFakeProbe` 四项 P1 smoke（不启动 Ollama） | 0 | **FAKE_PROBE_SMOKE PASS** |

## P1 smoke 证据

1. **strong race**：两个 `ResearchScheduler` 实例共享同一 SQLite store 并发申请 strong worker；结果为 grants `[1, 0]`，原因包含 `STRONG_WORKER_BUSY`，最终仅一条 live reservation。
2. **expiry quota**：cap=1 下 task-b 初始 grant 为 `0`；回收 `1` 条过期 reservation 后，task-b grant 为 `1`，证明 durable expiry 同步释放 probe quota。
3. **same-task grant isolation**：同一 task 的两个 grant 中，释放第一个后第二个 reservation 仍存活；重复释放结果不变；释放第二个后 live reservation 为 `0`。
4. **fake gate rejection**：激活接口传入 `quality_gate=True/resource_gate=True` 但不提供服务端 evidence handle，被稳定拒绝为 `GATE_EVIDENCE_REQUIRED`。

## 边界与阻塞

- 未运行全量 pytest；未启动或修改 Ollama；未下载/卸载模型；未做跨机器调度验证。
- Task02 benchmark 的质量/provenance 增强、Task06 runtime smoke 与控制面权限边界仍是后续项，不阻塞本 Task 的后端验收。
- smoke 首次误用系统 `python` 导入了环境中的同名 `tests` 包并因其日志路径权限失败；改用项目 `.venv/bin/python` 并内联 FakeProbe 后通过。该失败属于 harness 环境问题，不属于项目测试或业务失败。

## 产出与工作树纪律

- 本轮仅新增本验收报告；未修改 `backend/**`、`frontend/**` 或测试业务逻辑。
- 当前工作树中的后端改动仍保持未提交状态，符合调用方要求。
