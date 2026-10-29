# 真实报告生成记录

- 部署提交：`a955e2ee`，服务 `http://127.0.0.1:8000/`。
- 原始自然语言请求与审批：`../20261030-real-report-r2/01-intake.sse`、`02-approve.json`。原任务失败记录保留，不回退其终态。
- 公开重生成请求：`POST /api/research-tasks/bdcd7fc185425e0f8443599e9cdbe8ec/reports`，plan_version=1，HTTP 202，原始响应 `01-submit.json`。
- report_id：`4e71c52b-ff5e-4c15-8ffe-347af2dd6376`；report_version=2；published=true。
- Session：`50585f56b1b641fd9a5bd00a6379ff81`；Conversation：`cd5d8b1c3648462d9d5a59a903b832b4`。
- 真实质量响应：`03-report.json`，正文 CJK=2428，5篇、2项比较、4项多论文支持发现、0无效Evidence、0次质量改写。
- 已下载 Markdown、HTML、citation manifest；SHA-256 与 `04-artifacts.json` 三项完全一致。
- Markdown：`32810bc5cac2ba7530420db4db6f5e448fc12b5ba989a1dc19f7626e8e43ca5e`。
- HTML：`db6ad4fe783e6ac6cf4b7ffc5ef6e871762ca96661a9997a7eb7b927e088aade`。
- Citations：`88b2b86f363b69e9b61749b942fe5c0d152e6337c57104cd2363df72367bc9cc`。

这是基于摘要证据的真实内容报告，并非全文综述。选集中 PAL 的内核 CFI 研究与口令认证主题关联较弱，正文已明确其适用性仍需验证；不能据此宣称选集相关性完全通过。独立内容评审另记 `content-review.md`。

此记录只证明用户要求的超过1500字报告实际生成、发布和下载成功；不代表 Spec030 全部前端反馈、人工验收、最终全量回归和收尾已完成。
