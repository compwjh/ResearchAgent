# Task08 Semantic Scholar 限流只读诊断（候选 `134dce4`）

## 结论

本轮是**外部 Semantic Scholar 429 限流**，不是本地服务不可达或应用把响应误判为认证失败：真实地图创建、作业查询、事件查询、地图查询和 graph 查询分别取得 HTTP 202/200；作业唯一失败单元为 `SEMANTIC_SCHOLAR_RATE_LIMITED`，且 `retryable=true`。没有出现 401/403（应用会将其映射为 `SEMANTIC_SCHOLAR_AUTH_FAILED`），因此现有证据不支持把根因归为错误 API key/认证配置或地图业务异常。

本诊断没有发出任何新的 HTTP/provider 请求，没有创建新地图，没有读取或输出密钥值，也没有修改业务代码。

## 配置接缝（只保留布尔结果）

- 生产 client 的构造路径从 `SEMANTIC_SCHOLAR_API_KEY` 读取环境配置；只有非空时才发送 `x-api-key`，空值则走公共限流路径。
- 使用应用配置加载路径启动一个隔离的只读 Python 进程，仅输出布尔结果：`effective_key_present=true`。密钥值和 `.env` 内容未读取展示、未写入证据。
- 当前交互 shell 的环境变量本身为 `unset`，不能用它反推已运行服务；上面的 `effective_key_present` 才是应用配置加载后的布尔观察。该观察仍不暴露或证明配额状态。
- 本轮实际响应不是 401/403，而是 429；有无 key 可能影响 provider 配额，但不能把这次 429 证据改写成认证失败。

## 限速、退避与本 job

代码合同如下：

- 生产 client 共享进程级 `SemanticScholarRequestLimiter`，最小请求间隔为 1 秒；不是并发轰炸路径。
- `retries=1` 默认意味着一次逻辑调用最多 2 次 HTTP 尝试。429 后按 `max(base_delay * 2**attempt, numeric Retry-After)` 等待，默认 base delay 为 0.5 秒，等待上限为 30 秒；随后每次重试仍经过共享 1 RPS limiter。
- 非数字、负数或缺失的 `Retry-After` 使用指数退避；后续网络失败会清除上一响应，避免复用旧的 `Retry-After`。
- 证据中的 `provider_request_count=1` 是地图服务记账的一次**逻辑 provider 调用**，不是底层 HTTP 尝试数；本轮 evidence 未持久化 provider response headers 或内部 attempt 计数。因此不能声称具体的 `Retry-After` 秒数，也不能从 evidence 单独证明发生了 1 次还是 2 次底层尝试。可以确认的是：该逻辑调用已经返回终态 `SEMANTIC_SCHOLAR_RATE_LIMITED`，地图 job 已按有限重试合同结束为 `partial/finished`，没有由本验收脚本追加重试。

## 现有 job 的合法恢复入口

当前保留实体：

- map：`35a56c6f2da84fca85fc3c21dfa0055c`
- job：`270f948e1e924656a6d75371dc262759`

现有公开入口为：

```http
POST /api/literature-maps/35a56c6f2da84fca85fc3c21dfa0055c/jobs/270f948e1e924656a6d75371dc262759/retry
```

该入口只接受 `failed`/`partial`/`stopped` 作业，并且仅保留 `failed_units` 中 `retryable=true` 的单元；本 job 的 discovery 限流单元满足这一条件，所以从产品合同看可在 provider 冷却后受控重试。重试会复用原 map/job 的持久化状态，不应创建第二张图或覆盖本次不可覆盖 evidence。当前不调用该入口：root 正在处理前端暂停/服务协调，且 provider 条件尚未由外部确认。

## 最小恢复计划与停止条件

1. 等 root 完成 global nav CSS 修复及服务协调；本 agent 在此期间继续不发 API/provider 请求。
2. 由部署/账号侧确认 Semantic Scholar 配额或 provider 返回的冷却条件；若只能依据外部账号策略，则使用该策略，不以短间隔盲试替代 `Retry-After`。
3. 仅在服务 `ready=true`、冷却已结束且 root 明确授权后，对上述原 job 执行**一次** retry；按约 10 秒级别读取 job/events，保存新的追加证据，不覆盖本 run。
4. 若同一 discovery 单元再次返回 429，立即停止，不连续追加 provider 请求；保留 retryable 失败并回报 BLOCKED。

因此，**最早重试时点不是“现在”或固定的任意秒数**，而是同时满足“root 服务协调完成 + 服务 ready + provider 冷却/配额已确认结束 + root 明确授权”之后。由于本轮没有保存 `Retry-After` header，不能从本地 evidence 推导更早的精确时间。
