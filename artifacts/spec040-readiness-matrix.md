# Spec040 收口准备度矩阵

| 门禁 | 证据 | 结果 |
|---|---|---|
| 需求评审 | `docs/sdd/reviews/040-requirement-review.md` | 通过 |
| 技术评审 | `docs/sdd/reviews/040-tech-review.md` | 通过 |
| 定向重试测试 | `tests/test_retry_policy.py`、`tests/test_retry_observability.py` | 通过 |
| 定向线上回退测试 | `tests/test_online_provider_fallback.py` | 通过 |
| 前端状态合同 | `tests/test_retry_observability_frontend.py`、Node syntax | 通过 |
| 全量回归 | 2684 passed，3 skipped，67 subtests | 通过 |
| 部署首页/健康 | `/`、`/api/health` 均 200 | 通过 |
| 就绪检查 | `/api/ready` 200，`ready=true` | 通过（Qdrant warmup 单独降级） |
| 线上 Provider | DeepSeek 最小探针 HTTP 200，模型 `deepseek-flash` | 通过 |
| 运行时投影 | 任务列表含脱敏 `runtime_observability`，调度状态 200 | 通过 |

综合准备度：10/10；无 Spec040 P0/P1 阻塞。Qdrant warmup failed 已明确记录为非 Spec040 的后续问题，不伪装为知识库健康。

