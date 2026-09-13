# Spec034 Task05 后端验收报告

## 结论

**GO**。Task05 Fake/Store runtime 合同、Task02–04/Spec027/Skill/Tool 定向回归、语法检查、聚焦 Ruff、diff-check 和指定运行时探针均通过；未发现 P0/P1/P2 阻塞。本次仅验收，未修改业务代码或 Spec，未执行 commit/push/merge/reset/stash/clean。

## 验收范围

- Role/Skill/Tool snapshot 校验与未知/伪造/漂移能力 fail-closed。
- 递归安全输出及 ToolResult 脱敏，非法 Tool 批次原子拒绝、Tool 异常稳定失败。
- owner/session/task/work-item 绑定的 checkpoint、跨绑定拒绝、续跑和 generation/CAS 取消写屏障。
- 预算 0–3 次批准扩容、Run/Task hard caps、四次独立 attempt 与 Router metadata。
- 唯一 Orchestrator WorkItem→Runner 路径和 ResourceProbe lease 在成功、早期失败、取消、异常出口的释放。
- 真实 Ollama 仅做环境可达性记录，不以 Fake 结果替代真实模型调用结论。

## 命令与结果

| 检查 | 命令摘要 | 退出码 | 结果 |
|---|---|---:|---|
| Task05 + Task02–04 + Spec027 + Skill/Tool 定向 pytest | `.venv/bin/python -m pytest -q tests/test_spec034_task05_contract.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_skill_registry.py tests/test_skill_intent.py tests/test_tool_registry.py tests/test_tool_executor.py tests/test_spec027_runtime_contract.py` | 0 | **211 passed, 6 subtests passed**，11.66s |
| Task05 目标 py_compile | `.venv/bin/python -m py_compile`（Task05 application/domain/store 及 `tests/test_spec034_task05_contract.py`） | 0 | 通过 |
| Task05 聚焦 Ruff | `.venv/bin/ruff check`（Task05 改动文件及合同测试） | 0 | All checks passed |
| Task05 改动 diff-check | `git diff --check 1879fb3 --`（Task05 改动文件及合同测试） | 0 | 通过 |
| Fake/Store 运行时目标探针 | `.venv/bin/python -m pytest -q tests/test_spec034_task05_contract.py -k '...'`（下方 29 项目标测试） | 0 | **29 passed, 1 deselected**，0.39s |
| Ollama CLI 环境枚举 | `ollama list` | 0 | 列出本机 **11 个模型** |
| Ollama HTTP adapter 可达性 | `.venv/bin/python -c 'from backend.app.platform.ollama import get_available_models; print(get_available_models())'` | 1 | 沙箱 `httpx.ConnectError: [Errno 1] Operation not permitted`；未伪造成功 |

## Fake/Store 运行时探针明细

目标探针共 29 项，均通过：

1. 快照 fail-closed：注册 Tool schema/Skill snapshot 伪造拒绝；未批准 Skill snapshot 拒绝；PlanApproval envelope 可适配既有 registry；生产 fallback 使用既有 default dispatch。
2. 安全输出与 Tool：递归 Prompt/CoT/凭据/URL 等敏感字段在 checkpoint 前拒绝；非法 Tool batch 一个 Tool 都不执行；ToolResult 只保留安全摘要与计数；Tool 异常返回稳定失败。
3. checkpoint/取消/CAS：Store 绑定与计数 checkpoint；实例重启后 checkpoint 可验证；跨终态 generation 的 checkpoint 写入拒绝；续跑只接受前序 `limit_reached` Run 且使用持久 handoff；取消屏障拒绝迟到模型结果。
4. 预算：`max_model_loops=0` 稳定返回 limit 信号；caller budget 不能抬高 hard cap；批准扩展 0/1/2/3 次按授权绑定累加；第 4 次扩展稳定拒绝。
5. attempt/Router/Orchestrator：四次独立持久 Run/attempt 均写入 Router metadata；唯一 Orchestrator 为每个 WorkItem 创建完整绑定 Run 并只走注入 Runner。
6. ResourceProbe lease：成功生命周期、ResourceProbe 失败单 worker、model factory 失败、Store binding 失败、checkpoint store 失败均释放 lease。

## 阻塞与边界

- **验收阻塞：无。**
- 真实 Ollama HTTP 探针受当前沙箱禁止访问 `localhost:11434` 阻塞，已如实记录；`ollama list` 仅证明 CLI 本地模型清单可读，不证明真实推理/HTTP function-calling 成功。
- 本次按 Task 回归边界未运行全量 pytest；Ruff 为 Task05 受影响文件聚焦检查。最终 Spec 收口仍需由总控执行全量回归、真实可达环境端到端 smoke、部署及状态台账。

## 日志

- 进展日志：[backend-tester 日志](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-034/task-05/backend-tester/20260913-100000.md)
