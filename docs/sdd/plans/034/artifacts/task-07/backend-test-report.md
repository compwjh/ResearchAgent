# Spec034 Task07 后端验收报告

## 结论

**GO**。Task07 后端合同及 Task02–06/Spec027/conversations 定向回归全部通过；三级树、legacy v1、ResearchEvent 投影幂等、SSE 安全边界、retry drain、分页、跨会话归属和四级原子拒绝均有测试证据。py_compile、聚焦 Ruff、diff-check 全部通过，未发现阻塞。

本次仅验收，未修改业务代码或 Spec，未执行 commit/push/merge/reset/stash/clean。

## 命令与结果

| 检查 | 命令摘要 | 退出码 | 结果 |
|---|---|---:|---|
| Task07 + Task02–06 + Spec027/conversations 定向 pytest | `.venv/bin/python -m pytest -q tests/test_spec034_task07_backend.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py tests/test_conversations_api.py tests/test_memory_repositories.py` | 0 | **227 passed, 5 subtests passed**，8.03s |
| Task07 合同 | `.venv/bin/python -m pytest -q tests/test_spec034_task07_backend.py` | 0 | **9 passed**，0.74s |
| Python 语法 | `.venv/bin/python -m py_compile`（Task07 routes/memory/projector/store/service/orchestrator/runtime/entry 及合同测试） | 0 | 通过 |
| 聚焦 Ruff | `.venv/bin/ruff check [Task07 改动文件] --select E9,F63,F7,F82,I001 --output-format concise` | 0 | All checks passed |
| diff 空白检查 | `git diff --check 1879fb3 --`（Task07 改动文件及合同测试） | 0 | 通过 |

## 验收覆盖

1. **三级树与 v1 兼容**：additive migration 保留旧行并以 `schema_version=1` 根节点读取；Phase → Agent → Skill/Tool 三层可写，第四层、非法父链、跨 message 父节点和 cycle 均拒绝。
2. **ResearchEvent 投影**：parent-first replay、canonical `source_event_id`/`node_key` 幂等、乱序重放、终态屏障通过；重复事件不生成重复 processing step，迟到 running 不覆盖 completed。
3. **Skill/Tool 事件与安全**：ResearchEvent payload 白名单过滤，Prompt/凭据/Authorization/token/cookie/URL 等敏感值和异常细节不泄漏；Tool/Skill 节点保持树类型边界。
4. **SSE 与稳定失败帧**：projector 先落库再发送；投影失败保留稳定 `TRACE_PROJECTION_FAILED`/`trace_syncing` 标记，不暴露内部异常；upsert 帧不改变 legacy raw event 游标语义。
5. **retry drain**：投影失败写入 retry marker，后台启动可在没有新事件时执行有界 drain，成功后清除 Memory/ResearchStore pending marker。
6. **分页 >1000**：ResearchStore replay 分页至 `last_event_seq`，1001 个事件完整重放。
7. **跨会话/归属**：绑定的 task/conversation/activity/session/owner 不匹配会拒绝，不能把事件投影到其他会话消息；显式 research session 启用 strict tree，未绑定 legacy model 事件仍走宽松兼容路径。
8. **四级原子拒绝**：批量预校验在落库前三层前拒绝非法第四级，既有节点不被部分写入。

## 阻塞与边界

- 验收阻塞：无；定向测试无失败。
- 5 个 warning 来自既有依赖类型弃用提示，不影响测试结果。
- 本轮未运行全量 pytest 或真实跨端浏览器/SSE smoke；最终 Spec 收口仍需总控执行全量回归、跨端运行时验证、部署及状态台账。

## 日志

- 进展日志：[backend-tester 日志](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-034/task-07/backend-tester/20260913-160000.md)
