# Spec024 可见推理控制：Task05 验收复盘

## 结论

最新 HEAD `b00e098` 后最终验收为 **PASS with environment-deferred**。前一轮 FAIL 的两类问题均已闭环：显式 reasoning terminal 终态已修复，13 项旧回归合同已迁移并通过最终全量回归。唯一延期项是外部 Ollama chat 通道超时；Spec 是否收口由架构师裁决。

## 事实记录

- 主 Agent 在最新 HEAD 执行唯一一次全量 pytest：1341 passed、1 skipped、47 subtests passed，退出码 0。
- 前端语法退出码 0，全部合同 96 passed。
- 8010 实例 health/home 均 HTTP 200；Chromium 实际资源版本为 v35，五档选择器存在；最新 HEAD 未改前端。
- Ollama `/api/tags` HTTP 200 且包含 `qwen3.8:27b-mlx`，但 capabilities 与固定问题短预热均无响应（curl 28/20s）；真实 xhigh/low/off telemetry 记为环境延期。
- Fake adapter 全矩阵通过。修复后的显式 `reasoning_completed` 场景只发送一次 completed，随后 `CHAT_FAILED → done.failed`，持久化 reasoning 保持 completed、正文为空。

## 本轮修复带来的经验

1. Provider 的 reasoning terminal 必须进入统一状态机；收到显式 completed 后，首 token 前异常应保持 reasoning completed，不能由通用异常分支回退或重复发终态。
2. 全量回归合同迁移应同步保留安全约束：观测只保留 reasoning allowlist 和阶段耗时，prompt 内容脱敏，Ollama 地址跟随运行配置，schema v7 断言保持 owner/Unicode/fail-closed 覆盖。
3. tags/health 成功不能代表 Ollama chat 通道可用；真实性能验收必须以 bounded `/api/chat` 响应和 SSE 阶段字段为准，并区分冷启动、忙和不可达。
4. 服务端持久化状态和前端终态可以分层（例如 event gap 时 server failed、client interrupted），验收报告需同时记录两者。
5. 资源版本必须读取浏览器实际解析 URL；本 Task 已确认 v35 被真实加载。

## 复验待办

- Ollama chat 通道恢复后，使用固定问题完成 xhigh/low/off，补齐 request_sent_at、reasoning_started_at、首个过滤后非空 delta、reasoning_completed_at、first_answer_token_at、done_at、effort、event_seq、冷/热和忙状态。
- 补做真实 Chromium 普通消息顺序、自动折叠和错误终态交互；当前静态合同和 fake adapter 已通过。
- 架构师依据项目门禁决定：将当前结果以 environment-deferred 收口，或保持实施中等待真实 smoke。
