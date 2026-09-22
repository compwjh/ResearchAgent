# Spec040 技术评审

> 评审者：当前主会话分派的架构评审 Agent  
> 角色：架构师（技术评审）  
> 模型：Luna high（本次临时使用）  
> 分派方式：由主 Agent 按 Spec040 Task06 收口门禁分派；仅审查当前 Spec、Task 文档、运行时/API/前端实现和定向测试，不修改业务代码。  
> 评审时间：2026-09-20

## 结论

**技术方案有条件通过；收口阻塞。**

当前实现复用了既有 `ResearchAgentRunner`、`ModelRouter`、`ResearchStore`、研究事件流和前端任务投影，没有建立第二套调度器或 Provider 注册表。指数退避、持久化恢复、单次线上回退和脱敏观测的接口边界与 Spec 一致。由于 Task06 尚未完成真实 API E2E、全量回归和部署验证，本评审不签署 Spec040 完成，不声称运行时已经通过生产式验证。

## 审查范围

已读取并核对：

- `docs/sdd/specs/040-research-runtime-retry-and-online-fallback.md`；
- `docs/sdd/plans/040/README.md`、Task02–Task06；
- `backend/app/research/application/agent_runtime.py`；
- `backend/app/research/application/orchestrator.py`、`scheduler.py`；
- `backend/app/research/infrastructure/research_store.py`；
- `backend/app/api/routes_research.py`；
- `frontend/research-tasks.js`；
- `tests/test_retry_policy.py`、`tests/test_online_provider_fallback.py`、`tests/test_retry_observability.py`、`tests/test_retry_observability_frontend.py`。

## 技术门禁检查

| 检查项 | 结果 | 依据与判断 |
|---|---|---|
| 分层与复用边界 | PASS | 重试策略在 research application 层，状态持久化在既有 Store，模型回退复用 ModelRouter/模型目录，前端只消费现有任务投影。 |
| 指数退避公式 | PASS | `RetryPolicy` 默认 `max_attempts=5`、`base=2s`、`max=120s`、`jitter=20%`；`compute_retry_delay` 对延迟和输入做有界处理。 |
| 持久化与重启恢复 | PASS（定向验证） | WorkItem 具有 `retry_count`、`next_retry_at`、`last_error_code`，Store 提供 `waiting_retry` 的调度/到期重新入队；测试覆盖重启读取和完成态迟到重试保护。 |
| 并发与幂等 | PASS（定向验证） | Store 的重试调度和 WorkItem 状态更新走现有事务/状态机；已有完成状态不会被迟到重试重新打开。真实双进程验证仍留 Task06。 |
| 错误分类 | PASS | `AgentRuntimeError` 和模型异常映射到稳定码；瞬态错误进入重试集合，能力、取消和证据边界错误不进入线上回退。 |
| 线上 Provider 选择 | PASS | `_online_choice` 通过现有 ModelRouter/`get_online_models` 获取注册别名，不在运行时硬编码 API Key 或具体 Provider 凭据。 |
| 回退次数与边界 | PASS（定向验证） | `_build_online_fallback` 受显式配置控制，运行循环通过 `fallback_attempted` 限制单次回退；回退事件只记录别名、原因和尝试编号。 |
| 原始错误保留 | PASS | 运行输出的模型元数据保留 `original_error_code`、`fallback_error_code`、`fallback_attempted`；事件和 API 投影不输出底层异常详情。 |
| API 投影 | PASS（定向验证） | `routes_research.py` 的 `runtime_observability` 使用稳定白名单字段和安全值校验，任务列表与详情使用同一投影形状。 |
| SSE / 前端状态 | PASS（定向验证） | 前端识别 `waiting_retry`、重试次数、下一次重试时间和 Provider 回退信息；复用 event_seq 链路，未新增第二事件源。 |
| 敏感信息保护 | PASS（静态与定向测试） | 测试明确检查投影不含 `api_key`/`prompt`；代码中的 Provider/模型字段被截断并按别名写入事件。仍需在真实配置下检查部署日志。 |
| 既有回归风险 | PARTIAL | 当前定向测试通过，但工作树同时存在 Spec032/039 等其它未提交改动；尚未完成 Spec040 收口要求的全量回归，不能据此排除集成回归。 |
| 真实 API / 部署证据 | BLOCKED | Task06 为待执行；目前没有本次实现对应的真实请求、事件序列、最终任务状态、Artifact 路径和 health/ready 运行证据。 |

## 已执行的定向验证

```text
.venv/bin/python -m pytest -q \
  tests/test_retry_observability.py \
  tests/test_retry_observability_frontend.py \
  tests/test_online_provider_fallback.py \
  tests/test_retry_policy.py
结果：17 passed
```

这些测试覆盖：退避计算与持久化恢复、完成态迟到重试、默认关闭线上回退、授权后的线上别名回退、非瞬态错误不回退、API 脱敏投影和前端状态契约。它们不覆盖真实 Ollama/DeepSeek 网络调用，也不替代全量回归。

## 配置与安全检查意见

`.env` 中已由用户配置 DeepSeek 相关变量；本评审只确认配置入口存在，不读取或记录密钥值。Task06 必须验证：

- `DEEPSEEK_API_KEY` 不被日志、事件、前端或 Artifact 回显；
- `DEEPSEEK_BASE_URL` 与已注册 Provider 的调用配置一致；
- `ONLINE_MODELS=deepseek:...` 能映射到已注册模型别名，而不是将原始配置字符串直接信任为模型对象；
- `RESEARCH_ONLINE_FALLBACK_ENABLED=true` 时只在允许的瞬态错误触发一次回退；
- 回退失败保留本地与线上稳定错误码，并进入可诊断的 `failed/partial/waiting_retry` 状态；
- 关闭配置或无可用线上注册项时不进行网络外发。

## 阻塞项与后续动作

1. **真实 API E2E**：注入/复现本地模型瞬态错误，验证任务先进入 `waiting_retry`，之后恢复；再在已配置的线上回退路径验证一次 `provider_fallback` 和最终状态。不得把 mock 或内部函数调用当作 E2E。
2. **全量回归**：按项目收口规则运行全量测试，失败则定向修复；不把当前 17 个定向通过数写成全量通过。
3. **部署验证**：停止旧服务、按部署文档启动当前版本，检查首页、health/ready、任务查询和事件流；记录实际端口与命令。
4. **验收报告**：由 tester 生成 `docs/sdd/reviews/040-acceptance-review.md`，附请求/响应/实体 ID/最终状态/产物路径、人工操作步骤和准备度评分。
5. **状态收口**：Task06 完成并且验收评审签字后，才更新 Spec040、README、Task06 和 `spec-status-changelog.md` 为完成。

## 是否允许进入下一步

**允许进入 Task06 收口验证；不允许直接交付或标记 Spec040 为已完成。** 技术实现本身没有发现需要打回重构的 P0/P1，但缺少真实运行和全量回归证据是硬阻塞。

## Task06 复审补充（2026-09-20）

真实部署/API 检查、DeepSeek 最小 Provider 探针和全量回归已完成：`2684 passed, 3 skipped, 67 subtests passed`。Qdrant warmup 降级已明确标注为非 Spec040 后续项。最终技术门禁：**通过**，详见 `040-acceptance-review.md`。
