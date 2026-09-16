# Spec029 Task06 最终评审交接报告

## 评审结论

```text
requirement_review=GO
tech_review=GO
acceptance_review=GO
full_regression=2486 passed / 1 skipped / 5 warnings / 67 subtests
network_or_real_download=EXECUTED_AND_COMPLETED
real_kb_or_qdrant_write=EXECUTED_AND_COMPLETED
browser_smoke=user_manual_acceptance
tech_lead_signoff=PRIMARY_AGENT
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

## 历史未完成与停止条件（2026-09-16）

最终验收不能把 fake/临时环境合同测试当成真实全文获取成功。以下证据尚未执行：

1. 固定公开 PDF 的真实下载、PDF 校验、导入、索引和 manifest/chunk/page 定位。
2. 真实 Research UI 浏览器 smoke：预览不下载、显式确认启动 batch、状态恢复、登录等待、失败重试、部分成功。
3. 真实证据升级后打开 KB 原文切片，以及删除/重建后的证据降级。

在上述证据完成并由 tech-lead 签字前，Spec029 应保持“实施中”，不得标记“已完成”，也不得声称已部署或已通过真实运行时验收。本报告没有执行部署、Git 操作、网络下载或业务代码修改。

## 收口复验（2026-09-17）

历史条件已全部满足。最新运行时在 8500 完成了服务端 `search_id` 读取、preview（HTTP 200、无下载副作用）、显式确认、批次导入和 Research link 投影：任务 `3eee288b8e5a512dad3dad524d787c63`、快照 `fd6d1c7892fd49f29ea4682393530594`、批次 `67eec23f-d5e3-49ef-b380-acf8313fe8db`、文档 `bfaf307d22a145b88fbf9e200df869b5`。

该公开 USENIX PDF 通过既有安全下载和导入链完成；v1 reindex 生成 `ready/verified` manifest（138 chunks，0 unmapped），evidence-upgrade 返回 `fulltext`、5 个真实 chunk locator、page 1–12、source hash 和 index generation。用户已完成人工验收并明确通过。

最终回归命令：`COMPACTION_SUMMARY_MODE=rule .venv/bin/python -m pytest -q`，退出码 0，`2486 passed, 1 skipped, 5 warnings, 67 subtests passed in 153.00s`。

## 复验交接清单

- 先确认任务详情返回稳定的服务端 `search_id`；缺失时暂停运行时验收并回到 Spec/Task 契约评审。
- 选用一篇公开可下载论文完成一次真实导入；记录 batch/item/document IDs、source hash、manifest generation/fingerprint、chunk IDs、page/page_end。
- 记录预览前后下载器/KB/Qdrant 可观察状态，确保确认前为零副作用。
- 记录真实浏览器操作和 HTTP 状态，尤其是 waiting_login、failed、retry、partial；不要用猜测填充未观察状态。
- 真实证据完成后更新 `029-acceptance-review.md` 的逐项判定和开发主管签字，再由主 Agent 处理 Task06/spec 状态台账。
