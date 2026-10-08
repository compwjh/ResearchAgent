# Reasoning capability 诊断（只读运行时核对）

## 结论

本轮 `REASONING_EFFORT_UNSUPPORTED` 的直接原因已经确定为**失败时命中了仅含 `low` 的 24 小时 SQLite 能力缓存**，而不是 `qwen3.5:9b` 不在模型目录，也不是当前 provider 实际不支持 `off`。同时存在一个独立的代码契约缺陷：`/api/models` 对每个本地模型静态宣称五档能力，未读取实际能力缓存/探针，因此会把 `off` 广告给用户，而消息解析器可依据缓存拒绝同一请求。

当前受控 refresh 对同一部署的 provider 探针返回五档，随后无 refresh 读取也命中五档。因未保留 20:29 的 provider 原始探针响应或历史 Ollama 配置，不能进一步证明 provider 当时发生过版本/配置变更；能证明的是，失败时的非空部分缓存被当作 24 小时权威结果使用，未在显式 `off` 失败前重新确认。

## 范围与基线

- 当前仓库 HEAD：`6bacc2903a40ec2f7823b6d2fa13b3bc715fc8cb`。
- 当前服务地址：`http://127.0.0.1:8000`；本地 Ollama provider 版本只读查询为 `0.34.4`。
- 复核时间：本地时间 `2026-10-09 05:16–05:17`（UTC `2026-10-08 21:16–21:17`）。
- 参考失败证据：[current-research-e2e-required-matrix-report.md](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-required-matrix-report.md)、[current-research-e2e-required-matrix-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-required-matrix-evidence.json)。
- 失败 run：`spec032-task14-required-matrix-20261008T210806Z`，部署 HEAD 同上；请求 `model=qwen3.5:9b`、`reasoning_effort=off`，SSE 返回 `REASONING_EFFORT_UNSUPPORTED` / `retryable=false`，未进入业务研究阶段。
- 未读取 `.env` 或输出任何密钥；未发起业务 POST、未重试失败 run、未变更全局模型/配置/代码/部署。

## 运行时证据

| 只读请求 | 结果 | 诊断含义 |
|---|---|---|
| `GET /api/ready` | HTTP 200，`ready=true`；`jieba`、`ollama_tags`、`embedding`、`qdrant` 均 `ready` | 当前服务和 Ollama tags 依赖可达 |
| `GET /api/models` | HTTP 200；目录含 `qwen3.5:9b`，其 `capabilities.reasoning_efforts` 为 `off/low/medium/high/xhigh` | 不是 requested model 不在目录；但这是静态广告，不能证明每档可用 |
| `GET /api/chat/reasoning-options?model=qwen3.5:9b`（refresh 默认 0） | HTTP 200；`supported_efforts=["low"]`、`default_effort="low"`、`source="cache"`、`cached_at="2026-10-08T20:29:10.333526+00:00"` | 失败窗口的 resolver 实际只接受 `low`；该缓存约 47 分钟新，仍在 24 小时缓存门禁内 |
| `GET /api/chat/reasoning-options?model=qwen3.5:9b&refresh=1` | HTTP 200；`supported_efforts=["off","low","medium","high","xhigh"]`、`default_effort="xhigh"`、`source="ollama_probe"`、`cached_at="2026-10-08T21:17:14.660935+00:00"` | 当前 provider 的五档探针均成功，`off` 当前真实可用 |
| 上述 reasoning-options（refresh 后再次默认读取） | HTTP 200；五档、`source="cache"`，同一 `cached_at` | refresh 结果进入当前服务缓存并被正常复用 |
| `GET http://127.0.0.1:11434/api/version` | HTTP 200，版本 `0.34.4` | 记录当前 provider 状态；没有历史版本/配置基线，不能据此推断当时发生变更 |

本轮唯一的 refresh 是一个有界 GET 探针入口；它更新了能力缓存 SQLite 行，但没有写业务会话、研究实体、论文、导入或报告，也没有改变 env、模型配置或代码。当前脱敏读取到的 `data/model_capabilities.sqlite3` 行已是：`qwen3.5:9b`、五档、默认 `xhigh`、`source=ollama_probe`、五个 effort evidence key、24 小时内新鲜。

## 失败链路与代码依据

1. `backend/app/api/routes_models.py:33-53` 的 `_build_local_models()` 只调用 `/api/tags` 的 `get_available_models()`；对每个本地模型直接填 `list(REASONING_EFFORTS)`（`routes_models.py:50`）。因此 `qwen3.5:9b` 在目录中且显示 `off`，只表示目录存在和 UI 广告，不是能力证据。
2. `backend/app/platform/ollama.py:109-139` 的实际探针逐档调用 provider：`off` 映射 `think=false`，`xhigh` 映射 `think=true`，其余档位传字符串；只有返回内容满足对应 `thinking` 形状才加入支持集。
3. `backend/app/platform/ollama.py:149-166` 在未 refresh 时优先读取进程缓存，进程未命中再读取 `model_capabilities.sqlite3`；只要记录在 24 小时内就以 `source=cache` 返回，不重新探测。失败窗口返回的 `cached_at=20:29:10` 与此路径一致。
4. `backend/app/platform/ollama.py:209-223` 要求请求档位属于实际 `supported_efforts`；不在集合中即抛 `REASONING_EFFORT_UNSUPPORTED`。所以当缓存集合仅为 `("low",)` 时，显式 `off` 必然被拒绝。
5. `backend/app/api/routes_conversations.py:614-627` 只有能力集合为空（`unknown`）时才允许 `off` fallback；非空但不含 `off` 的缓存会按“确实不支持”返回 409。这解释了 E2E 的不可重试错误，也说明该请求不是能力未知分支。

## 四种候选原因判定

| 候选 | 判定 | 证据 |
|---|---|---|
| requested model 不在 `/api/models` | **排除** | 当前 `/api/models` 明确含 `qwen3.5:9b`，`/api/ready` 的 `ollama_tags` 也 ready |
| `off` 在当前 provider 实际不支持 | **排除（当前时点）** | `refresh=1` 的真实 provider probe 返回 `off` 及其余四档；随后默认读取也为五档 |
| advertised capabilities 与 resolver 矛盾 | **确认** | `/api/models` 无条件广告五档；失败时 `/api/chat/reasoning-options` 实际缓存仅 `low`，同一请求因此 409 |
| provider/环境曾发生外部变化 | **未证实** | 当前 provider 版本可读为 0.34.4，但没有 20:29 的 provider 响应或历史版本基线；不能把“之前多次通过、这次缓存为 low”冒充版本变更证据 |

最强可复核解释是：20:29 的一次探测只持久化了非空部分能力 `low`（可能是 provider 冷启动/瞬时探测结果，也可能是外部状态变化），随后 24 小时 SQLite freshness 规则把它当作完整权威集合；同时 `/api/models` 的静态广告仍宣称五档。`refresh=1` 之后，当前真实探针已恢复五档，但本报告不把这次诊断 refresh 当作原失败 run 的成功重试。

## 精确可用请求

在本次复核结束时，已证明下列请求级组合被当前 resolver/provider 接受：

```json
{
  "model": "qwen3.5:9b",
  "reasoning_effort": "off"
}
```

同一模型的 `low`、`medium`、`high`、`xhigh` 也在本次 refresh 返回的支持集内；`off` 的 provider 传值是布尔 `false`，不是字符串 `"off"`。但不能把这组结果外推为永久能力：调用方应以同一部署当前的 `GET /api/chat/reasoning-options?model=qwen3.5:9b` 返回集为准。若该接口在未 refresh 时再次返回只有 `low`，精确安全请求只能是 `reasoning_effort=low`；此时 `off` 会按当前代码稳定返回 409，而不是被静默降档。

## 最小后续 backend-dev 工作

不在本诊断中修改业务代码。下一项最小工作应限定为能力广告/缓存一致性，并补定向测试：

1. 检查 `backend/app/api/routes_models.py:_build_local_models` 与 `backend/app/platform/ollama.py:get_reasoning_capabilities` 的单一能力来源边界；至少不能继续把 `/api/models` 的五档静态列表作为真实能力证据，避免 UI 诱导用户选择 resolver 会拒绝的档位。若出于首屏性能不做逐模型探针，应明确返回“未知/待探测”，而不是五档。
2. 针对 `model_capabilities.sqlite3` 中“非空但不完整/瞬时”的缓存策略加定向测试：缓存集合为 `("low",)`、显式请求 `off` 时，验证是否按产品契约执行一次受控重新确认；provider 真支持时应解析为 `off -> think=false`，provider 真不支持时才保留 409。不得通过省略 `reasoning_effort`、替换模型或放宽 validator 掩盖问题。
3. 测试文件建议：更新 `tests/research/test_online_models_api.py` 覆盖目录广告与实际能力不可矛盾；在现有 reasoning capability/stream 测试域补“部分 SQLite 缓存 + refresh 后全档”和“off 的 `think=false` 映射”用例。测试名按功能命名，不添加 spec/task 编号。

建议的验收顺序是：先通过定向单测证明能力广告与 resolver 取值一致，再由验收 agent 用**全新** conversation 复现原始 `qwen3.5:9b/off` 自然语言入口；本报告不代替该 E2E。

## 风险与操作记录

- 风险 P1：静态 `/api/models` 可能对 embedding/reranker 等非 chat 模型也显示五档；这是比本次 qwen3.5 失败更广的误导面。
- 风险 P1：24 小时 freshness 把一次部分探测结果延长为长时间拒绝，且失败响应 `retryable=false`，用户没有自助恢复路径。
- 本轮未运行 pytest（诊断没有代码变更）；未执行业务 POST、未重试历史任务、未下载/同步论文、未启停服务。
- 受控命令均为只读 HTTP、脱敏 SQLite 查询和代码定位；唯一运行时副作用是 `reasoning-options?refresh=1` 更新能力缓存，不涉及业务数据。
- 交付耗时：约 20 分钟（从收到本轮诊断任务到报告落盘）。

