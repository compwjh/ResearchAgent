# Spec040 需求评审

> 评审者：当前主会话分派的架构评审 Agent  
> 角色：架构师（评审）  
> 模型：Luna high（本次临时使用）  
> 分派方式：由主 Agent 按 Spec040 Task06 收口门禁分派，仅读取 Spec、Task 文档、运行时实现、API/前端投影和定向测试结果；本评审只修改本评审文档。  
> 评审时间：2026-09-20

## 结论

**需求定义通过；Spec040 收口阻塞。**

Spec040 的目标、用户可见边界、失败分类和“不自动外发”的产品约束是清楚且可验收的。当前实现已经覆盖 Task02–05 的主要需求，但 Task06 尚未完成：没有在当前部署版本上完成真实 API E2E 成功案例、全量回归、部署/健康检查、人工验收准备度和最终复盘。因此本评审不批准将 Spec040 标记为 `已完成`，也不替代验收评审。

## 需求逐项核对

| 检查项 | 结论 | 当前事实与证据 |
|---|---|---|
| 一句话目标可测 | PASS | Spec 明确要求资源争用进入持久化等待、按指数退避恢复，并在明确授权时切换线上 Provider。 |
| 资源竞争用户体验 | PASS（实现已覆盖） | `ResearchAgentRunner`/WorkItem 调度新增 `waiting_retry`、`retry_count`、`next_retry_at`；前端有“等待重试”和下一次时间提示。 |
| 本地模型瞬态失败 | PASS（实现已覆盖） | `agent_runtime.py` 将超时、429/5xx、模型不可用映射为稳定错误码，并由有界重试策略处理。 |
| 线上模型回退授权 | PASS（边界清晰） | `RESEARCH_ONLINE_FALLBACK_ENABLED` 默认关闭；仅从现有注册表解析线上别名，且最多回退一次。 |
| 安全/权限/取消边界 | PASS（契约清晰） | Spec 明确能力未授权、取消、证据越界不得自动重试或换模型；对应测试覆盖非瞬态错误不回退。 |
| 敏感信息边界 | PASS（实现与测试覆盖） | 事件和 API 投影只保留 Provider/模型别名、错误码和尝试信息；定向测试检查不含 `api_key`、`prompt`。 |
| 用户等待与恢复提示 | PASS（实现已覆盖） | `frontend/research-tasks.js` 识别 `waiting_retry`、重试次数、下一次时间和 Provider 回退提示。 |
| 不改变论文业务链路 | PASS | Spec 和 Task 边界没有增加下载、来源或论文证据逻辑；运行时复用既有 ModelRouter、Store、事件流。 |
| 失败仍可诊断 | PARTIAL | 运行时保留稳定错误码和尝试链，但 Task06 尚未在当前部署版本执行真实失败→恢复/回退闭环并落盘证据。 |
| 收口验证与交付 | BLOCKED | Task06 仍为“待执行”；尚未证明全量回归、真实 API E2E、部署 health/ready 和人工验收案例。 |

## 当前实现证据

- Spec：`docs/sdd/specs/040-research-runtime-retry-and-online-fallback.md`。
- 计划：`docs/sdd/plans/040/README.md` 与 Task02–06 文档；README 当前将 Task02–05 标记为完成，Task06 仍待执行。
- 运行时：`backend/app/research/application/agent_runtime.py`、`orchestrator.py`、`scheduler.py`、`research_store.py`。
- API 投影：`backend/app/api/routes_research.py` 提供脱敏 `runtime_observability`，包含等待/重试/Provider 信息。
- 前端：`frontend/research-tasks.js` 已有 `waiting_retry`、重试提示和 Provider 回退文案。
- 当前定向测试：

  ```text
  .venv/bin/python -m pytest -q \
    tests/test_retry_observability.py \
    tests/test_retry_observability_frontend.py \
    tests/test_online_provider_fallback.py \
    tests/test_retry_policy.py
  17 passed
  ```

  该结果只证明当前定向契约，不等于 Spec 收口所需的全量回归或真实 API E2E。

## 产品配置风险

当前工作树的 `.env` 已出现线上 Provider 配置痕迹，且 `RESEARCH_ONLINE_FALLBACK_ENABLED=true`。这符合“显式开启才允许回退”的设计，但收口前必须在部署验证中确认：

1. API Key 只被 Provider 客户端读取，不进入日志、事件、Artifact、前端响应或评审文档；
2. `ONLINE_MODELS` 中的别名能被现有模型注册表解析；
3. 未配置或关闭回退时仍保持本地重试，不发生外发；
4. 真实线上调用证据只记录脱敏别名和错误码，不记录密钥、Cookie、Token、完整 Prompt 或论文正文。

本评审不读取、不复制、不展示 `.env` 中的凭据。

## 收口前必须完成

1. 用当前部署版本跑通一条真实 HTTP API E2E：本地模型瞬态失败进入等待并恢复，或在显式开启配置下完成一次受控线上回退；记录请求、响应、任务 ID、最终状态、事件和产物路径。
2. 验证关闭线上回退、能力错误、取消和证据越界路径均不外发且错误码稳定。
3. 执行全量回归；失败时先定向修复并重跑。
4. 直接部署当前候选，检查首页、`/api/health`、`/api/ready` 和相关任务 API。
5. 生成十项人工验收准备度和逐步操作案例，达到项目要求的至少 9/10，且无 P0/P1、关键产物缺失或 API E2E 失败。
6. 完成 `040-acceptance-review.md`、Task06 执行结果、Spec 变更日志和复盘后，才可将 Spec040 改为 `已完成`。

## 评审裁决

**允许继续执行 Task06；不允许现在收口。** 当前没有需求层面的打回，阻塞原因是收口证据尚未执行，而不是目标或产品边界不清。

## Task06 复审补充（2026-09-20）

Task06 已补齐真实部署/API 证据、全量回归、Provider 探针、人工验收步骤和准备度矩阵；原“收口阻塞”条件已解除。最终需求门禁：**通过**。详见 `040-acceptance-review.md`。
