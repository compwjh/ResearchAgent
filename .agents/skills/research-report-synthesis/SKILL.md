---
name: research-report-synthesis
description: 编排会话式深度研究的证据报告合成、引用校验、不可变 Artifact 与会话写回。仅在研究任务已完成评估并需要生成最终报告时使用。
---

# Research Report Synthesis

## 适用范围

- 只处理已批准研究计划和已验证候选证据。
- Markdown 是规范源；HTML 只能由固定安全渲染器派生。
- 结果写入 ResearchArtifact，并按任务与报告版本幂等写回原会话。

## 编排步骤

1. 接收 Evaluator/Critic 的验证候选、引用白名单和任务范围；拒绝未验证候选、越界引用、Prompt、CoT、凭据、任意 URL 或文件路径。
2. 生成结构化 `ReportSynthesisOutput`：`schema_version`、`report_version`、`output_hash`、`sections`、`citation_manifest`、`artifact_ids`、`safe_summary`、`source_refs`。
3. 通过 `ReportSynthesizer` 生成 Markdown，并用固定转义渲染器派生 HTML；不得解释原始 HTML、Markdown 链接或图片。
4. 通过 `ReportDeliveryService` 保存 Markdown、HTML、citation manifest 三类不可变 Artifact。重复 `(task, report_version, artifact_type)` 必须复用，不覆盖已有内容。
5. 以 `research-report:{task}:{version}` 作为最终助手消息幂等键写回原会话；消息、Artifact 与通知按可重放 Saga 分阶段提交。
6. 发送完成、partial、失败、重试和需要用户操作等通知；通知使用 owner+幂等键和 event cursor，已读采用 owner 校验的 CAS。

## 失败与停止条件

- 引用缺少验证证据、哈希不匹配、版本冲突、Artifact 不可变冲突或 owner/session 不匹配：停止写回，返回稳定错误码并保留可重试事实。
- Synthesizer 失败：保留已有证据与旧报告，可单独重试并生成新版本；不得生成模板假报告。
- 下载只接受已登记的 `artifact_id` 和 owner 校验，不解引用 `storage_ref` 或任意路径。

## 不负责

- 不下载或验证论文 PDF，不实现 Claim/Evidence 矩阵。
- 不展示 Prompt、隐藏思维链、凭据或模型内部完整推理。
- 不发送浏览器系统通知、邮件或移动推送。
