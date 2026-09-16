# Spec029 验收评审：Research Task 全文获取与知识库联动

- 评审对象：[`docs/sdd/specs/029-research-fulltext-acquisition.md`](../specs/029-research-fulltext-acquisition.md)
- 评审时间：2026-09-16（Asia/Shanghai）
- 评审者：Spec029 最终评审文档子 Agent
- 评审角色：验收评审（基于 Task02–05 交接证据与全量回归摘要）
- 评审模型：Luna high（本次分派）
- 分派方式：主 Agent 分派的 Task06 文档评审子任务；初审未执行真实网络下载或浏览器操作，收口复核已补齐运行时证据

## 结论：通过（GO）

代码合同、定向测试、最终全量回归和真实公开 PDF 导入/索引/证据升级均已完成。用户已完成人工验收并明确通过，Spec029 满足收口条件。

## 逐项验收

| Spec 验收项 | 判定 | 证据与缺口 |
|---|---|---|
| 候选增删与预览 | 合同通过 | `tests/test_spec029_frontend_acquisition_progress.py` 4 项静态合同；前端新增候选 checkbox 和 preview 调用（`frontend/research-tasks.js:1150-1361`），预览文案明确不会下载。未在真实浏览器点击验证。 |
| 显式确认前不下载 | 合同通过，运行时未验 | 前端确认按钮才调用 `POST .../acquisitions`；后端 preview 是只读分类，`ResearchAcquisitionService.confirm()` 要求当前版本、服务端 `search_id` 后才调用既有 batch。未抓取真实 downloader/KB/Qdrant 计数证明。 |
| 审批幂等与过期版本 | 通过（单测） | `tests/test_spec029_acquisition_bridge.py` 覆盖重复 approval 和 stale selection；ResearchStore 唯一约束及 `acquisition.py:56-115` 提供代码依据。 |
| 已有文档复用与批量导入映射 | 通过（合同/定向测试） | Task02 证明 duplicate 在下载前命中既有文档；Task03 证明 `candidate_id → import_item_id/paper_id/status/error_code` link/event 投影和部分失败语义。未以真实 PDF 走完整链路。 |
| 登录等待、单篇失败和重试 | 合同通过，未制造失败样本 | 前端展示 waiting_login 并要求用户在既有浏览器会话登录，失败项复用既有 import-item retry；Task03/05 报告与静态合同覆盖。本次成功样本不人为制造登录或失败状态。 |
| 全文 RAG allowlist | 通过 | `tests/test_spec029_fulltext_evidence.py` 断言 `document_ids` allowlist、`fulltext` 升级和 provenance；真实文档 `bfaf307d22a145b88fbf9e200df869b5` 已完成 evidence upgrade。 |
| 可定位全文切片 | 通过（fake manifest），真实结果未验 | 服务验证确定性 chunk、manifest 中的精确文本、页码和 `page_end`；测试断言 document/chunk/page/provenance。没有真实公开 PDF 产生的 manifest/chunk/page 证据。 |
| 删除/重建后的降级 | 通过（合同单测），真实结果未验 | `revalidate()` 合同测试覆盖 manifest fingerprint/generation 变化与删除后的 `revalidation_required`/`unavailable`；未对真实 KB 文档删除、manifest tombstone 和报告投影执行运行时验证。 |
| 前端证据入口与 DOM 安全 | 通过（静态） | 前端专项测试断言 evidence locator、chunk IDs、`jumpToKnowledgeBase`、无 `.innerHTML`；`node --check frontend/research-tasks.js` 通过；未在浏览器确认原文切片自动聚焦。 |
| 全量回归 | 通过 | 收口复验命令退出码 0：**2486 passed / 1 skipped / 5 warnings / 67 subtests**。 |
| 真实公开 PDF + 浏览器 smoke | **通过** | 任务 `3eee288b8e5a512dad3dad524d787c63` 通过服务端快照确认导入 USENIX 公开论文；批次 `67eec23f-d5e3-49ef-b380-acf8313fe8db` 完成，文档 `bfaf307d22a145b88fbf9e200df869b5` 生成 138 chunks 的 verified manifest，证据升级为 fulltext。用户已人工验收页面行为。 |

## 收口复验清单（已完成）

以下项目已在 2026-09-17 收口复验中完成：

1. 服务端任务详情返回稳定 `search_id`，句柄与确认请求一致性校验通过。
2. preview HTTP 200 且未创建导入批次；显式确认后才创建既有 batch。
3. 批次逐篇返回 `completed` 并写回 `document_id/import_item_id` link。
4. 真实 v1 manifest 为 `ready/verified`、138 chunks、0 unmapped，包含 page/chunk/source hash/generation。
5. evidence-upgrade 返回 `fulltext`、5 个真实 chunk locator、page 1–12；删除/重建降级合同仍由定向测试覆盖，未改写历史报告。

## 开发主管签字

> 初审时待真实公开 PDF 与浏览器 smoke；收口复核已完成，以下签字以真实运行时记录和用户人工验收为依据。

- 签字人：主 Agent（基于用户人工验收和运行时证据）
- 签字时间：2026-09-17（Asia/Shanghai）
- 签字结论：GO
