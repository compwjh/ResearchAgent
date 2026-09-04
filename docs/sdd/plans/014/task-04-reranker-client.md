# 任务 04 — 实现 Reranker 客户端

> 关联：[spec-014](../../specs/014-kb-reranker.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 02 Go；当前状态：`待执行`

## 一句话目标

实现一个与检索流程解耦的批量 `/v1/rerank` 客户端，对返回协议做严格校验，并把所有运行故障转换为可解释的降级结果。

## 输入输出

- 输入：问题、按 RRF 排序的 `Hit` 列表、base URL、模型名和超时。
- 成功：返回稳定排序后的 hits、耗时和 `used=true`。
- 降级：返回原 hits、`used=false/degraded=true` 和枚举化原因，不抛到 API 层。
- 原因至少区分：disabled、too_few_candidates、connection、timeout、http_status、invalid_json、invalid_schema、invalid_index、invalid_score、unexpected。

## 实施步骤

1. 建立独立客户端模块，集中构造 URL、请求体、超时和响应解析。
2. 每次只发送一个批量请求，documents 顺序与输入 hits 完全一致。
3. 校验结果项数量、唯一 index、索引范围及有限数值分数。
4. 根据 index 映射原对象；按分数降序、原 RRF 位置升序稳定排序。
5. 不把固定探针的“分数必须不同”规则套到真实业务批次；业务同分合法。
6. 对不可达或质量失败设置至少 30 秒负状态缓存/熔断，使用单调时钟；当前问答不重试。
7. 校验 base URL 只使用 HTTP loopback，拒绝远程 host。
8. 捕获可预期网络/协议错误并生成结构化结果；只记录摘要，不记录完整 query/documents。
9. 为客户端编写 mock HTTP 单元测试，不依赖真实模型。

## 涉及文件与子代理拆分

- 分派 A（`junior-dev`）：客户端模块单文件。
- 分派 B（`tester` 或实现期 `junior-dev`）：对应单元测试单文件。
- 架构师核对异常边界、对象映射和日志脱敏；不得先写代码再补分派记录。

## 边界

- 空 URL、末尾斜杠、非正超时应规范化或回退默认值。
- 0/1 条候选不发请求。
- 返回结果顺序可以任意，必须按 index 映射。
- bool 虽是 Python int 子类，但不得接受为 index 或 score。
- 熔断期间直接返回已缓存降级原因，不发送网络请求。
- 不修改输入列表的原有顺序，成功结果返回新列表。

## 明确不做

- 不查询 Qdrant、不负责候选截断、不生成答案。
- 不自动拉起 llama-server，不在单次问答内反复重试。
- 不兼容自定义聊天打分协议，只支持 spec 约定的 `/v1/rerank`。

## 验收标准

- 覆盖正常、乱序结果、同分稳定性、连接/超时/HTTP/JSON/schema/index/score 异常。
- 所有失败返回输入原顺序和明确原因。
- 一批 N 条候选只产生一次 HTTP 请求。
- 单元测试无需 Ollama 或 llama-server 即可运行。

## 风险、回滚与产出

- 风险：llama.cpp 版本返回字段差异；只在 Task 02 实测协议范围内实现，差异视为 invalid_schema。
- 回滚：检索层不调用客户端即可恢复原行为。
- 产出：客户端模块、单元测试和执行记录。
- 执行结果：待执行后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-02 | 架构师(自身) | 创建任务计划，状态为待执行 |
