# Spec029 Task06 最终评审交接报告

## 评审结论

```text
requirement_review=GO_WITH_RUNTIME_PREREQUISITE
tech_review=GO_WITH_RUNTIME_PREREQUISITE
acceptance_review=NO-GO_PENDING_REAL_RUNTIME_EVIDENCE
full_regression=2450 passed / 1 skipped / 5 warnings / 67 subtests
network_or_real_download=NOT_EXECUTED
real_kb_or_qdrant_write=NOT_EXECUTED
browser_smoke=NOT_EXECUTED
tech_lead_signoff=PENDING
```

## 已核对的实现事实

- 复用链路保留在既有边界：Research 只接线到 `PaperImportBatchService`，不复制 downloader、PDF parser、导入状态机或 KB 文档。
- 确认快照、文档 link、导入事件和 evidence projection 有独立 Research 持久化；selection version/idempotency key 有约束，旧 evidence 表通过加性列迁移保存 provenance。
- EvidenceUpgrade 只允许已确认且已完成的 `document_id`，将 allowlist 传给既有 `hybrid_search`，并要求 inspection manifest 中的精确 chunk 文本、页码、source hash 与 index generation；无法定位时不升级为 `fulltext`。
- 删除/重建重验证路径能将证据投影标记 `unavailable` 或 `revalidation_required`，不改历史报告正文。
- 前端候选编辑、预览、显式确认、状态轮询、waiting_login/failed/retry 展示、证据定位入口和 DOM 安全均有静态合同；资源版本已更新。

## 测试证据

| 层级 | 结果 |
|---|---|
| Task02 复用/证据门 | 5 passed；临时 SQLite/fake downloader/import/manifest，无网络或真实 KB 写入 |
| Task03 acquisition bridge | `py_compile` 通过；3 passed；与 Spec027 集合 60 passed、5 subtests passed |
| Task04 evidence upgrade | 12 passed；`py_compile`、`git diff --check` 通过 |
| Task05 frontend | 4 passed；相关前端合同 11 passed；`node --check frontend/research-tasks.js` 通过；`git diff --check` 通过 |
| 最终全量回归 | 交接摘要：**2450 passed / 1 skipped / 5 warnings / 67 subtests**；未提供退出码，本报告不推断退出码 |

## 未完成与停止条件

最终验收不能把 fake/临时环境合同测试当成真实全文获取成功。以下证据尚未执行：

1. 固定公开 PDF 的真实下载、PDF 校验、导入、索引和 manifest/chunk/page 定位。
2. 真实 Research UI 浏览器 smoke：预览不下载、显式确认启动 batch、状态恢复、登录等待、失败重试、部分成功。
3. 真实证据升级后打开 KB 原文切片，以及删除/重建后的证据降级。

在上述证据完成并由 tech-lead 签字前，Spec029 应保持“实施中”，不得标记“已完成”，也不得声称已部署或已通过真实运行时验收。本报告没有执行部署、Git 操作、网络下载或业务代码修改。

## 复验交接清单

- 先确认任务详情返回稳定的服务端 `search_id`；缺失时暂停运行时验收并回到 Spec/Task 契约评审。
- 选用一篇公开可下载论文完成一次真实导入；记录 batch/item/document IDs、source hash、manifest generation/fingerprint、chunk IDs、page/page_end。
- 记录预览前后下载器/KB/Qdrant 可观察状态，确保确认前为零副作用。
- 记录真实浏览器操作和 HTTP 状态，尤其是 waiting_login、failed、retry、partial；不要用猜测填充未观察状态。
- 真实证据完成后更新 `029-acceptance-review.md` 的逐项判定和开发主管签字，再由主 Agent 处理 Task06/spec 状态台账。

