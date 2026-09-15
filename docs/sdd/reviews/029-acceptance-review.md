# Spec029 验收评审：Research Task 全文获取与知识库联动

- 评审对象：[`docs/sdd/specs/029-research-fulltext-acquisition.md`](../specs/029-research-fulltext-acquisition.md)
- 评审时间：2026-09-16（Asia/Shanghai）
- 评审者：Spec029 最终评审文档子 Agent
- 评审角色：验收评审（基于 Task02–05 交接证据与全量回归摘要）
- 评审模型：Luna high（本次分派）
- 分派方式：主 Agent 分派的 Task06 文档评审子任务；未执行真实网络下载或浏览器操作

## 结论：不通过（待完成真实环境验收）

代码合同、定向测试、前端静态检查和最终全量回归摘要支持“实现候选可进入运行时验收”，但尚未满足 Spec029 明确要求的真实公开 PDF 全文导入/索引/切片定位，也未完成真实浏览器 smoke。开发主管签字因此暂留空，Spec029 不应据此标记为已完成。

## 逐项验收

| Spec 验收项 | 判定 | 证据与缺口 |
|---|---|---|
| 候选增删与预览 | 合同通过 | `tests/test_spec029_frontend_acquisition_progress.py` 4 项静态合同；前端新增候选 checkbox 和 preview 调用（`frontend/research-tasks.js:1150-1361`），预览文案明确不会下载。未在真实浏览器点击验证。 |
| 显式确认前不下载 | 合同通过，运行时未验 | 前端确认按钮才调用 `POST .../acquisitions`；后端 preview 是只读分类，`ResearchAcquisitionService.confirm()` 要求当前版本、服务端 `search_id` 后才调用既有 batch。未抓取真实 downloader/KB/Qdrant 计数证明。 |
| 审批幂等与过期版本 | 通过（单测） | `tests/test_spec029_acquisition_bridge.py` 覆盖重复 approval 和 stale selection；ResearchStore 唯一约束及 `acquisition.py:56-115` 提供代码依据。 |
| 已有文档复用与批量导入映射 | 通过（合同/定向测试） | Task02 证明 duplicate 在下载前命中既有文档；Task03 证明 `candidate_id → import_item_id/paper_id/status/error_code` link/event 投影和部分失败语义。未以真实 PDF 走完整链路。 |
| 登录等待、单篇失败和重试 | 合同通过，运行时未验 | 前端展示 waiting_login 并要求用户在既有浏览器会话登录，失败项复用既有 import-item retry；Task03/05 报告与静态合同覆盖。未执行真实登录等待或失败恢复。 |
| 全文 RAG allowlist | 通过（单测） | `tests/test_spec029_fulltext_evidence.py` 断言 `document_ids` allowlist、`fulltext` 升级和 provenance；服务在 `evidence_upgrade.py:86-100,196-205` 拒绝未批准文档。真实 KB 检索未执行。 |
| 可定位全文切片 | 通过（fake manifest），真实结果未验 | 服务验证确定性 chunk、manifest 中的精确文本、页码和 `page_end`；测试断言 document/chunk/page/provenance。没有真实公开 PDF 产生的 manifest/chunk/page 证据。 |
| 删除/重建后的降级 | 通过（合同单测），真实结果未验 | `revalidate()` 合同测试覆盖 manifest fingerprint/generation 变化与删除后的 `revalidation_required`/`unavailable`；未对真实 KB 文档删除、manifest tombstone 和报告投影执行运行时验证。 |
| 前端证据入口与 DOM 安全 | 通过（静态） | 前端专项测试断言 evidence locator、chunk IDs、`jumpToKnowledgeBase`、无 `.innerHTML`；`node --check frontend/research-tasks.js` 通过；未在浏览器确认原文切片自动聚焦。 |
| 全量回归 | 通过（交接摘要） | 最终摘要为 **2450 passed / 1 skipped / 5 warnings / 67 subtests**；退出码未在交接信息中提供，本评审未重新运行。 |
| 真实公开 PDF + 浏览器 smoke | **未完成** | Task02–05 均明确 `network_or_real_download=false`、`real_kb_or_qdrant_write=false`；Task05 明确 `runtime_smoke=NOT_RUN_BY_SUBAGENT`。这是当前不通过的唯一收口门禁缺口。 |

## 必须补做的运行时证据

以下项目完成并落盘真实输出后，才能重新进行验收签字：

1. 启动当前服务，确认 Research 任务详情能提供稳定的服务端 `search_id`；若缺失，先修订契约并重新评审。
2. 对固定公开 PDF 执行候选预览，证明 preview 不产生下载、导入 item、KB document 或 Qdrant 写入。
3. 在 UI 增删候选并点击一次确认，证明只在确认后创建既有 batch；读取逐篇状态，覆盖已有、completed、waiting_login、failed、partial 和 retry。
4. 至少完成一篇公开 PDF 的真实导入和全文索引；通过 inspection manifest 读取真实 `document_id`、`chunk_id`、页码/跨页范围、source hash 和 generation。
5. 调用 evidence-upgrade，证明报告/投影从 abstract 升级到 `fulltext`，并能从 UI 打开既有 KB 原文入口；随后执行删除或重建验证 `unavailable`/`revalidation_required`，历史报告正文保持不变。

## 开发主管签字

> 待真实公开 PDF 与浏览器 smoke 完成后，由开发主管（tech-lead）复核并签字。当前不签署“通过”，不把未执行的运行时步骤写成成功。

- 签字人：待补
- 签字时间：待补
- 签字结论：待补

