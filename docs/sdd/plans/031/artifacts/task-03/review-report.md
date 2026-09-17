# Spec031 Task03 后端复审报告（修复后独立复审）

## 结论

**GO（附 P2 建议；不阻塞 Task03）**。

本轮只评审，不修改业务代码、不运行全量回归、不启动服务、不 commit/push。原两个阻塞 P1 均已关闭：值级敏感内容现在在 SQLite service/store 边界和 Langfuse routing seam 共享检查；`build_research_service()` 真实装配 `RoutingObservationService`，装配失败静默回退。outcome 自动记录按交接约定留给 Task06，不阻塞本 Task。

## 原两个 P1 复核

| P1 | 判定 | 证据 |
|---|---|---|
| 值级敏感内容不得进入 SQLite 或 Langfuse metadata | **已关闭** | `_contains_sensitive_value()` 同时检查原文和将 `_`/`-` 归一化为空格后的文本（`backend/app/research/application/routing_observation.py:38-47`），`_bounded_text()` 统一调用（`:54-61`）。service/store 直达校验走 `_validate_routing_decision()`（`:64-82`、`research_store.py:4475-4480`）；Langfuse routing seam 对 task/model/reason/policy/outcome 复用相同校验（`spans.py:296-325`）。新增 joined-value 测试覆盖 `PRIVATE_RESPONSE`、`PRIVATE_TOKEN`、`chain_of_thought`、`private-response`（`tests/test_spec031_shadow_observation.py:113-120`），Langfuse metadata 也覆盖同类值（`:152-157`）。独立 hostile probe 验证这些值及 `{"answer":"PRIVATE"}` 均未进入 SQLite/metadata。 |
| `build_research_service()` 真实装配 `RoutingObservationService` 且装配/观测故障静默降级 | **已关闭** | `entry.py:211-218` 创建 `RoutingObservationService(store, observability=record_routing_observation)` 并注入 `ModelRouter`；构造异常在 `entry.py:216-217` 回退 `None`。生产装配测试 `tests/test_spec031_shadow_observation.py:160-169` 验证实际 store/sink；手工将构造器改为抛错后 service 仍构建且 router observation 为 `None`。Langfuse config/client 异常由 `spans.py:323-325` 的 `safe_call` 兜底，独立 monkeypatch probe 未冒泡。 |

## 检查矩阵

| 检查项 | 结论 | 证据与说明 |
|---|---|---|
| SQLite/Langfuse 值级敏感内容 | **通过** | 原文、大小写变体、下划线/连字符拼接、JSON/键值表达式均被拒绝；拒绝日志只输出异常类型，不输出原值（`spans.py:319-321`）。service、ResearchStore 直达入口、policy 和 Langfuse seam 均复用共享检查。 |
| Langfuse 配置/客户端异常不冒泡 | 通过 | `record_routing_observation()` 将采样判断、客户端初始化及 SDK 上报包在 `safe_call(record_event, ...)` 内（`spans.py:323-325`）；`record_event()` 内部路径见 `spans.py:255-276`。手工让 `should_sample()` 和 `get_client()` 抛异常，调用均正常返回。 |
| Owner 隔离 | 通过 | 决策读取按 `decision_id AND owner_id`（`research_store.py:4526-4532`），列表按 owner 过滤（`:4534-4545`）；outcome 写入校验 decision 所属 owner（`:4557-4561`），读取同样带 owner（`:4588-4594`）。独立 probe 验证跨 owner 不可读且同 key 可分别建立记录。 |
| Idempotency | **部分通过，P2 建议** | 同 owner/key 重复写返回既有记录，跨 owner 不共享 key（`research_store.py:4484-4497`）。但冲突检查目前只比较 `task_type/chosen_model/policy_version`（`:4490-4494`）；features、candidate_models、reason 改变时仍静默返回旧记录。该问题不破坏敏感边界或生产路由，不阻塞 Task03，但建议后续改为比较完整 public contract，并补冲突测试。 |
| Shadow 不改生产选择 | 通过 | replay 只计算候选并返回 `ShadowReplay`（`routing_observation.py:414-437`）；router 由 `_pick_model()` 先完成生产选择，再旁路写观测并返回原 choice（`model_router.py:127-151`）。现有测试通过。 |
| 旧 router/FakeModelRouter 兼容 | 通过 | `ModelRouter.resolve()` 新参数均 optional（`model_router.py:122-124`）；`agent_runtime.py:1475-1484` 仅 observation sink 存在时追加新 kwargs，否则保持旧签名。Spec027 回归通过。 |
| SQLite 加性迁移 | 通过 | 初始化事务调用 `_ensure_spec031_schema()`（`research_store.py:419-427`）；四张表和索引全部 `CREATE ... IF NOT EXISTS`，不变更 schema marker（`:723-777`）。 |
| Production outcome 自动记录 | **按约定延期，非本 Task 阻塞项** | `record_outcome()` API 存在（`routing_observation.py:331-357`），当前没有稳定生产调用出口；`backend-report.md` 已明确留给 Task06，避免改变 Spec027/Task02 运行时契约。本复审不将其作为 Task03 NO-GO 原因，但 Task06 必须继续跟踪。 |

## 独立复现与测试

### 敏感值 hostile probe

临时 SQLite 与捕获 Langfuse metadata 的独立 probe 均得到拒绝/零事件：

```text
SQLITE REJECT PRIVATE_RESPONSE
SQLITE REJECT chain_of_thought
SQLITE REJECT private-response
SQLITE REJECT {"answer":"PRIVATE"}
LANGFUSE events 0
```

### 定向测试与静态检查

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest --noconftest -q tests/test_spec031_shadow_observation.py tests/test_spec027_runtime_contract.py tests/test_spec027_backend_research_slice.py` | 0 | **111 passed，5 subtests passed，3.05s** |
| `python -m py_compile backend/app/platform/observability/__init__.py backend/app/platform/observability/spans.py backend/app/research/application/routing_observation.py backend/app/research/application/model_router.py backend/app/research/application/agent_runtime.py backend/app/research/application/entry.py backend/app/research/infrastructure/research_store.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

Task03 单测独立计数为 16 passed（交接报告记录一致）；未运行全量 pytest、未部署/启动服务。

## P2 后续建议

1. idempotency 冲突应比较完整 `RoutingDecision.public()`，覆盖 features/candidate_models/reason/policy 等字段差异。
2. 将 joined-value hostile 样例再补到 ResearchStore 直达写入测试，并补 Langfuse config/client 异常的自动化测试；本轮已用独立 probe 验证行为。
3. Task06 按交接报告补齐 outcome 生产出口、Task02 benchmark 质量/provenance、全量回归和部署验证。

## 复审边界

本报告覆盖修复后 Task03 改动、`backend-report.md`、Spec031/Task03 约束及用户指定检查项；仅更新本复审报告，未修改业务代码、未 commit/push。
