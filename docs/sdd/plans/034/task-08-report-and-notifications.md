# Task08 — 报告 Artifact、会话写回与通知

> 关联：[Spec034](../../specs/034-conversational-deep-research-agent-runtime.md) ｜ 索引：[README](./README.md)
> 依赖：Task06、Task07；当前状态：`实施中（后端实现中）`

## 一句话目标

由真实 Synthesizer 基于验证证据生成不可变 Markdown/HTML 报告，并幂等写回原会话、通过应用内通知可靠送达。

## 背景与前置条件

- 必读 Spec034 的 Artifact、最终消息、通知、失败重试与引用边界。
- 只做引用 manifest，不扩展为 Spec030 完整 Claim/Evidence 矩阵。

## 数据、配置与接口

- 新增 `research-report-synthesis` Skill 和 ReportSynthesisOutput Schema。
- Markdown 是规范源；HTML 固定渲染并净化；版本、哈希、生成 Run 和 manifest 必填。
- ResearchArtifact 与 ResearchNotification 使用独立表；Artifact 版本/类型唯一且不可变，Notification 以 owner+幂等键去重并以 owner 级 event_seq 补发。
- Notification 明确保存 `status=unread/read`，已读只允许由 owner 校验的 CAS 完成；通知事实与 Artifact 生命周期分离。
- 实现 artifacts 列表/下载、owner 通知 SSE 与 read 接口。

## 实施步骤与文件边界

1. 后端实现 Synthesizer 输入白名单、引用校验、不可变 Artifact 和安全 HTML。
2. 以 `research-report:{task}:{version}` 幂等插入最终助手消息。
3. 实现五种重要通知、游标补发、去重和已读定位。
4. 前端实现报告渲染、Markdown 下载、HTML 打开和通知跳转。

## 子代理分派

- `backend-dev`、`frontend-dev` 分端；每次一个 Artifact/通知/展示关注点。
- `backend-reviewer` 检查引用、不可变版本、路径/响应头和重复写回。
- `frontend-reviewer` 检查 Markdown/HTML XSS、下载和通知定位。

## 边界与明确不做

- 不生成强制 PDF，不覆盖旧报告，不通知每个 Tool 进度。
- Synthesizer 不得引用未验证证据或杜撰论文。
- 浏览器系统通知、邮件和移动推送不在范围。

## 验收、风险与回滚

- 同版本重试只产生一条最终消息；新版本产生新消息并标明版本。
- synthesis 失败保留证据和旧报告，可单独重试并生成新版本。
- 同一 `(task, report_version, artifact_type)` 不能覆盖；下载按 artifact_id 和 owner 校验，不接受任意路径或 storage_ref。
- SSE 断开后补发未读，不重复；点击定位准确。

## 产出物、执行结果与变更日志

- 产出：Synthesizer Skill、Artifact/通知 API、报告与通知 UI、双端测试和评审。
- 执行结果：后端阶段实施中，待双端实现与评审/验收后填写。
- 变更日志：2026-09-13 启动报告 Synthesizer、不可变 Artifact、会话幂等写回与通知游标实现；复用 Task05/06/07 运行与投影接缝，不扩展 Claim/Evidence 矩阵。
