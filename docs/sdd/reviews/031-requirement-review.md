# Spec031 需求评审：动态模型路由与资源调度优化

## 评审元数据

- 评审对象：`docs/sdd/specs/031-dynamic-model-resource-routing.md` 与 Task02 交接物
- 评审任务：Task02 — 单实例/多实例与 Worker 基准门
- 评审角色：开发主管 / SDD Gate Reviewer
- 评审模型：Luna high
- 评审范围：目标、边界、Task02 用户可验收性、1–4 Worker 指标口径、多实例 Go/No-Go、Task03 前置条件
- 评审时间：2026-09-17（Asia/Shanghai）

## 结论

**有条件通过；Task03 允许按单实例路径放行。**

Spec031 的目标、明确不做、20% 资源余量、ResourceProbe 失败降级、多实例必须以证据放行等需求边界清楚。Task02 已提供 qwen3.5:9b 在单 Ollama 服务上 1–4 Worker 的真实历史 raw、复现 harness、汇总报告和定向合同测试；多实例没有第二实例实测证据，因此保持 **NO-GO** 是符合需求门的保守结论。

本结论不表示所有可复现性缺口已修复。以下 P1/P2 必须在 Task06 收口前补齐或明确记录为人工证据限制：

- P1：固定 JSON 输出未被 harness 校验，当前“失败率 0%”只能解释为 HTTP/传输失败率，不能作为质量门结论。
- P1：raw 未包含 ResourceProbe 内存快照、listener/备用端口探针、Ollama/平台环境等关键 provenance，报告中的多实例 blocked 证据无法仅凭 raw+harness 自动复现。
- P2：harness 未拒绝 0、负数、重复或 5+ Worker，也未拒绝非正 warm wave。
- P2：合同测试未核对逐请求样本、summary、一致性和 provenance，仍偏结构性。

## 需求核对

| 需求项 | 判定 | 依据 |
|---|---|---|
| 目标与范围 | 通过 | Spec031 要求先测单服务 1–4 个 9B Worker，只有证据明确收益才允许多实例；不训练、不下载、不改 Ollama 安装、不做跨机器集群。 |
| 1–4 Worker 可测性 | 通过（有条件） | report/raw 覆盖四档 cold/warm 请求，固定输入与参数，TTFT、吞吐、失败率、`/api/ps` 驻留数据可复核；质量内容校验仍需 Task06 补齐。 |
| 指标口径 | 通过 | TTFT 为客户端首 token，服务时延使用 Ollama 原生纳秒字段，热吞吐按并发波次最长墙钟时间聚合，冷/热分离。 |
| 资源与安全边界 | 通过 | 既有 ResourceProbe 保留至少 20% 余量；探针失败降为单 Worker 并标记 `RESOURCE_PROBE_FAILED`。Task02 未把 2–4 Worker HTTP 200 解释成生产放行。 |
| 多实例门 | 通过（NO-GO） | 仅发现 11434 listener；11435–11438 无服务，无第二实例吞吐/内存/局域网入口证据；不能从单实例外推多实例收益。 |
| Task03 依赖 | 有条件通过 | 可继续单实例决策/结果观测和 shadow policy；不得提升生产并发或启用第二实例。P1/P2 不得被静默写成已修复。 |

## 产品/验收可操作性

Task02 当前没有用户 UI 流程，属于内部基准门。其可验收输出应是：固定输入、环境快照、1–4 Worker 表格、原始逐请求数据、复现命令、单实例结论和多实例 Go/No-Go。现有 report 已覆盖主要文本交接物；但 provenance 与答案内容校验缺口会影响后续把基准作为 policy 激活证据使用。

Task03 可见产品行为必须继续遵守：观测不可阻塞 Research Task；资源不可用时显示/记录降级状态；路由不可为延迟选择违反 JSON Schema、上下文或证据任务要求的模型；多实例 blocked 不应伪装成能力已启用。

## 放行条件与后续动作

1. **Task03：放行**，范围限定为单 Ollama 服务、ResourceProbe cap、动态决策记录与 shadow policy；保留 `RESOURCE_PROBE_FAILED` 和单 Worker fallback。
2. **多实例：不放行**，直到第二实例在保持 11434 入口不变的条件下有同口径质量、TTFT、吞吐、峰值内存、失败率和局域网访问证据。
3. **Task06 前补齐 P1**：harness 必须校验固定 JSON；raw 必须保存 ResourceProbe snapshot/available memory、listener/备用端口探针和运行环境 provenance。
4. **Task06 前补齐 P2**：限制 Worker/warm 参数并增强合同测试，核对 summary 与 samples 及 provenance。

## 评审边界

本需求评审只核对 Spec031 与 Task02 交接物，不代表 Task03–05 实现、Task06 全量回归、部署或最终运行时验收已完成；未修改业务代码、Spec 状态或 Task 状态。
