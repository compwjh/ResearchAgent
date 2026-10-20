# Spec018 2026-10-21 PDF 安全与状态发布修复：需求评审

- 评审者：`/root/map_analysis_backend_review`
- 角色：独立架构师 / 安全技术评审
- 模型：当前执行 Agent（不固化模型代号）
- 分派方式：上级 Agent 分派，本 Agent 独立只读评审
- 评审日期：2026-10-21（Asia/Shanghai）
- 范围：仅评 Spec018 修复段、原安全/hash/发布合同、诊断报告与相关实现/精准测试；不修改代码、不部署、不调用真实 provider/数据、不改写历史 018 完成报告。

## 结论

**GO（需求评审通过，附强制验收约束）。**

本次修复需求边界清楚且与用户授权一致：只修正真实 GAT PDF 的 Catalog 内部页内 `OpenAction → /GoTo → page reference + /Fit` 误报，并修正同一单文档索引发布中的 manifest、chunker metadata、来源 hash 与 generation 一致性；不把安全误报修复扩展为“放行所有 OpenAction”，不新增任务持久化 API，不做全 KB 重建，不绕过 Spec043 全文 ready gate。

## 需求闭合核对

### 已明确且可验收

1. **安全分类目标**：Spec018 修复段（`docs/sdd/specs/018-knowledge-document-chunk-inspector.md:15-23`）与诊断（`diagnosis.md:76-87`）明确要求只读结构化白名单；危险、远程、脚本、表单、附件/嵌入和未知/不可解析结构继续 fail-closed。
2. **实际误报边界**：诊断（`diagnosis.md:11-18,36-47`）给出 GAT 文档的被动证据：唯一 active 结构是内部 `/GoTo` 页目标，目标为页引用 + `/Fit`，无 JavaScript、表单、附件、远程动作或 `Next` 链。
3. **发布一致性目标**：同次索引必须让 manifest 真实终态、chunker 状态、canonical `indexed_source_sha256/source_hash_state` 与 generation digest 一致；`partial` 不得伪装为 `ready/indexed`（`diagnosis.md:22-29,89-98`）。
4. **可回归性**：需求已明确无害导航、危险动作/对象/间接引用、未知/不可判定拒绝，以及 partial/ready、hash、generation、失败注入测试矩阵（`diagnosis.md:104-124`）。

### 范围与明确不做

- 不新增下载器、PDF action 执行器、网络访问、任务持久化记录或公开任务状态 API。
- 不执行 PDF action，不跟随 destination，不解析外部资源，不调用导航，不联网。
- 不把已有 `partial` manifest 手改为 `ready`，不手改 hash/状态，不降低 Spec043 `status=ready + progress=100 + verified hash + generation` 门禁。
- 不全库重建；仅对目标单文档通过现有 reindex API 做有界恢复。真实文档恢复、API smoke 与全文分析/问答复验留给后续验收门禁。
- 不改写 2026-10-06 已完成报告及其历史证据；本目录只追加本轮诊断、评审和实现交接物。

## 强制验收约束

以下不是建议，而是需求评审通过后必须保留的可观察结果：

1. 白名单只能接受同文档、可验证的内部 page destination；至少验证 page reference 属于当前 PDF、destination 形状合法且无 `/Next`。named destination、无法解析的间接引用和任何额外 action 链不得因“看起来像内部跳转”而放行。
2. 所有 `/AA`、`/AcroForm`、`JavaScript/JS`、`XFA`、`RichMedia`、`EmbeddedFiles`、`Launch`、`SubmitForm`、`ImportData`、`GoToR`、文件/远程目标和未知结构继续产生现有 hostile/unavailable 失败语义；不得只删除 `/OpenAction` 正则命中就结束分类。
3. parser 测试必须用 spy 证明没有 action 执行、导航、资源加载或网络调用；URI annotation 仍可作为被动元数据，不得 fetch。
4. worker 测试必须证明 manifest 先于成功 metadata 发布；manifest 写失败、metadata/hash 写失败和 generation digest 刷新失败均不得暴露 `ready/indexed/verified` 的假成功状态。
5. partial hostile PDF 可以有 `source_hash_state=verified`，但 chunker 必须是 `indexed_partial`，manifest 必须是 `partial`，且 v2 partial 不得覆盖兼容顶层 v1 状态。

## 风险记录

- 本评审只确认需求边界和验收可测性，不确认当前旧实现已经满足需求；当前实现仍存在诊断指出的 `OpenAction` 存在即 hostile 以及 metadata 先于 manifest 发布问题。
- 现有历史验收通过不覆盖本次新增安全/发布修复；Spec018 仍保持 `实施中`，不能据此宣称 Spec043 或 Spec018 全量收口。

## 评审签字

**独立架构师 / 安全技术评审：GO。** 需求范围可以进入技术实现评审，但必须先解决技术评审报告中列出的 P1 发布原子性与结构化 destination 边界问题；在技术评审 BLOCK 消除前不得派发编码。
