# Task 02：验证动态规划、模型路由和资源调度协议

> 关联：[Spec 027](../../specs/027-research-task-dynamic-orchestration-mvp.md) ｜ 索引：[README](./README.md)
> 依赖：Spec027 用户确认、需求/技术评审通过；被依赖：Task03–06；当前状态：`待执行`

## 一句话目标

在不实现业务代码的前提下，用固定样本和局域网 Ollama 冻结 Planner Schema、动态 fan-out/fan-in、模型升级、9B 并发额度和停止规则，给出 Go/No-Go。

## 当前证据与前置门禁

- Spec015 已有固定九节点目录图、USENIX/DBLP 缓存和 RAG；现有聊天图只有单节点。
- 2026-09-12 局域网 Ollama 清单包含 `qwen3.5:9b` 与 `qwen3.8:27b-mlx`。
- 记录分支、commit、工作树与现有接口；所有探针使用固定样本、临时库和受控请求。

## 执行阶段与文件边界

1. 定义五种 WorkItem 的 JSON Schema、无环依赖和预算拒绝样本。
2. 用 Fake Adapter 验证两路并行、fan-in、覆盖不足和一次 Re-plan。
3. 验证 fast 输出非法时重试并升级 strong。
4. 记录单 Ollama 服务 1–4 个 9B 请求的资源/吞吐证据；本 Task 不启多实例。
5. 产出 GO/NO-GO 报告和后续接口冻结结果。

允许修改：`docs/sdd/plans/027/artifacts/task-02/**`、`tests/test_spec027_runtime_contract.py`。禁止修改 `backend/**`、`frontend/**`、Ollama 配置、真实数据库和论文文件。

## 完整分派 Prompt

```text
角色：architect + backend-tester，模型按 Spec027 执行配置。
读取：Spec027、本 Task、Spec015 的 catalog graph/domain 接口、现有 Ollama adapter 和 MODEL_REGISTRY。
目标：冻结 Planner/WorkItem/事件/资源额度合同并给出 Go/No-Go，不写业务代码。
允许修改：docs/sdd/plans/027/artifacts/task-02/**、tests/test_spec027_runtime_contract.py。
禁止：修改 backend/frontend、真实库、模型部署；下载论文；reset/stash/clean/push/merge。
验证：固定计划 Schema、环依赖、预算、fan-out/fan-in、Re-plan、fast→strong、1–4 Worker 探针、git diff --check。
完成状态：报告明确哪些为确定性证据、哪些为环境延期，并给出 GO/NO-GO。
返回：状态摘要；改动文件；命令/退出码/结果；产物；决策依据；风险阻塞；主 Agent 后续动作；开始/结束/耗时；可用的模型/token/工具统计。
信息不足则阻塞，不得自行扩展范围。
```

## 主 Agent 校验与验收

- 读回报告和 diff，确认无业务代码或真实数据变化。
- 重跑 Schema/Fake Adapter 最小测试；真实 Ollama 超时只能标环境延期。
- GO 必须证明稳定 Graph + 动态任务可行、停止条件确定、资源失败能单 Worker 降级。

## 风险、回滚与产出

- Schema 无法表达 Re-plan 或现有接口必须被复制时为 NO-GO。
- 仅新增合同测试/报告，回滚删除本 Task 新增产物。
- 产出：`artifacts/task-02/runtime-gate-report.md`；执行结果初始为“待执行后填写”。

## 变更日志

- 2026-09-12：创建协议 Go/No-Go Task。
