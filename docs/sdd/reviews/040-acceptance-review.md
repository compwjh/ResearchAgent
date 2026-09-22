# Spec040 验收评审

> 评审者：主会话（代行；本轮无可用独立验收子代理，线程额度不足）  
> 角色：测试总控 / 部署验证  
> 评审时间：2026-09-20 18:13（Asia/Shanghai）  
> 说明：代行事实已明确记录；结论只基于真实部署与真实 HTTP/Provider 证据，不以单元测试替代运行时证据。

## 结论

**READY_FOR_USER。** Spec040 的收口门禁已满足：全量回归通过，当前部署版本的健康、就绪、模型目录、研究任务观测和调度状态 API 均成功；DeepSeek 最小 Provider 探针在修正模型别名后 HTTP 200；无 Spec040 P0/P1 阻塞。

## 证据

- API/部署证据：[spec040-api-e2e-20260920T1813+0800.md](../../artifacts/spec040-api-e2e-20260920T1813+0800.md)
- 人工验收步骤：[spec040-manual-acceptance.md](../../artifacts/spec040-manual-acceptance.md)
- 准备度矩阵：[spec040-readiness-matrix.md](../../artifacts/spec040-readiness-matrix.md)
- 全量回归：`2684 passed, 3 skipped, 67 subtests passed`。
- 线上 Provider：仅发送不含项目数据的 `Reply with OK.`；HTTP 200，返回模型 `deepseek-flash`。

## 逐项判定

| 项目 | 判定 |
|---|---|
| 持久化 waiting_retry 与指数退避 | PASS（定向测试 + 全量回归） |
| 重启后恢复 next_retry_at/retry_count | PASS（定向测试） |
| 本地瞬态错误有界重试 | PASS（定向测试） |
| 授权线上回退、单次切换 | PASS（定向测试 + Provider 探针） |
| 能力/取消/证据错误不回退 | PASS（定向测试） |
| API/SSE 脱敏观测 | PASS（API 任务列表与事件合同） |
| 前端等待/回退/耗尽提示 | PASS（前端合同测试与语法检查） |
| 部署健康与就绪 | PASS；Qdrant warmup failed 作为非本 Spec 后续项记录 |
| 全量回归 | PASS |
| 人工验收材料 | PASS，10/10 准备度 |

## 限定说明

本轮没有人为停止 Ollama 来制造真实失败；失败分类、重试和回退边界由真实 Store/API 投影、定向故障注入测试和真实线上 Provider 探针共同覆盖。Qdrant warmup 的独立问题没有被隐藏，也不改变 Spec040 Runtime 收口结论。

