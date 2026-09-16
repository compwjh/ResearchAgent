# Spec029 需求评审：Research Task 全文获取与知识库联动

- 评审对象：[`docs/sdd/specs/029-research-fulltext-acquisition.md`](../specs/029-research-fulltext-acquisition.md)
- 评审时间：2026-09-16（Asia/Shanghai）
- 评审者：Spec029 最终评审文档子 Agent
- 评审角色：开发主管视角的需求门禁审阅
- 评审模型：Luna high（本次分派）
- 分派方式：主 Agent 分派的 Task06 文档评审子任务；基于 Spec029、Task02–05 交接报告、当前 diff 与最终全量回归摘要

## 结论：通过（已完成运行时收口）

需求目标、数据边界、接口行为、失败语义和明确不做均足以指导实现与验收，未发现需求级 P0。真实公开 PDF 导入、全文索引、可定位切片和用户人工验收均已完成。

## 逐项评审

| 维度 | 判定 | 依据与说明 |
|---|---|---|
| 一句话目标 | 通过 | Spec 明确要求用户确认论文清单后复用既有安全下载、批量导入和 KB 索引，并把证据升级为可定位全文切片；成功标准可被拆成确认、导入、索引、引用四段链路。 |
| 数据模型 | 通过 | `AcquisitionApproval`、`ResearchDocumentLink`、`EvidenceUpgrade`、`AcquisitionEvent` 分别承载确认快照、引用映射、证据升级和既有批次状态投影；没有复制 KB 文档或建立第二套导入状态机。实现字段见 `backend/app/research/domain/models.py:382-585`。 |
| 接口与用户行为 | 通过 | `acquisition-preview` 为只读预览；`acquisitions` 只在显式确认后创建既有 batch；状态 GET 返回逐项映射；`evidence-upgrade` 只接受文档白名单和问题。路由和请求模型见 `backend/app/api/routes_research.py:111-152,1095-1204`。 |
| 边界可测试性 | 通过 | Spec 已列重复确认、过期选集、已有文档、部分失败、等待登录、下载/索引失败、取消、删除与重建等边界；Task02–05 交接报告逐项给出 fake/临时 SQLite 合同测试。 |
| 明确不做 | 通过 | 不自动下载未确认论文、不绕过登录/付费墙/验证码、不复制 downloader/parser/chunker/embedding/reranker/Qdrant collection、不做报告编辑器；当前实现未显示越界。 |
| 验收映射 | 通过 | “候选确认→批量导入→单篇失败重试→全文索引→页码/切片定位”已映射到 Spec 验收方式；初审时真实公开 PDF 和浏览器 smoke 尚未执行，已在 Task06 补齐。 |

## 需求级强制约束

1. 确认前只允许读取服务端候选快照；预览不得下载、创建 KB 文档或写入 Qdrant。
2. 确认请求必须带当前 `selection_version`、唯一 `paper_ids`、`idempotency_key` 和服务端 `search_id`；过期版本、候选越界或无快照必须 fail closed。
3. 论文导入只能复用现有 `PaperImportBatchService` 及其安全下载、去重、登录等待、部分成功和重试语义；Research 侧只保存 link/event 投影。
4. 全文证据必须来自已批准的 canonical `document_id`，通过既有 `hybrid_search` 的 allowlist 和 inspection manifest 校验确定性 `chunk_id`、文本、页码及页码范围；无法定位时保持摘要级或 `unavailable`，不可保存模型摘录冒充证据。
5. 删除、来源 hash/manifest 变化或索引代次变化后，全文引用必须降为 `unavailable` 或 `revalidation_required`，但不得改写历史报告正文。
6. 真实环境验收必须补齐：至少一篇公开 PDF 的下载、导入、全文索引、证据升级及浏览器主链路；这些动作在本评审中没有执行，也不能从单测结果推断成功。

## 评审范围与限制

- 评审读取了 Spec029、`plans/029/artifacts/task-02` 至 `task-05` 报告、Task06 计划、Spec029 相关当前 diff 和新增合同测试。
- 初审全量回归摘要为 2450；收口复验重新执行并通过：**2486 passed / 1 skipped / 5 warnings / 67 subtests**，退出码 0。
- 初审时真实下载、真实 KB/Qdrant 写入、真实登录等待和浏览器 smoke 尚未执行；收口复核已补齐公开 PDF 导入、索引、证据升级和用户人工验收。

## 收口复核（2026-09-17）

运行时已完成服务端快照 → preview → 显式确认 → 既有批量导入 → v1 manifest → fulltext evidence 链路；用户人工验收通过。需求评审结论保持 GO。
