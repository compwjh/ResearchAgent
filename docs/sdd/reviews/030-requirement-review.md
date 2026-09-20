# Spec030 需求评审：跨论文证据矩阵与深度研究报告

- 评审对象：[`docs/sdd/specs/030-research-evidence-reporting.md`](../specs/030-research-evidence-reporting.md)
- 评审范围：Task02 Evidence Report Contract v1 与固定样本
- 评审时间：2026-09-17（Asia/Shanghai）
- 评审角色：开发主管视角
- 评审模型：Luna high（临时分派）

## 结论：通过（Task02 合同门）

Spec030 的目标、证据边界、失败语义和三种只读输出已足够拆分为矩阵、报告生成和工作台任务。Task02 已把需求转为可验收的 Claim → Evidence → Paper/locator → CitationManifest 回查合同；未发现需求级 P0 阻塞。

## 逐项核对

| 维度 | 判定 | 依据 |
|---|---|---|
| 目标与用户旅程 | 通过 | Spec 明确查看矩阵、展开证据、生成不可覆盖版本和查看 Markdown/HTML/JSON；缺失证据显式展示。 |
| 证据范围 | 通过 | `catalog`、`abstract`、`fulltext` 分级；仅标题级候选不得进入方法/结果比较。 |
| 支持/冲突/上下文/缺失 | 通过 | 矩阵单元格固定四种关系；缺失单元格没有 Evidence ID，必须带缺口原因。 |
| 引用可追溯 | 通过 | 主要 Claim 通过 citation manifest 回查到论文和定位；失效引用 fail closed。 |
| 降级与历史 | 通过 | 证据不足发布 `partial`（若流程允许）；删除/重建不覆盖历史正文，当前证据降为 unavailable/revalidation_required。 |
| 明确不做 | 通过 | 不新增检索、下载、导入、chunker、embedding、reranker 或富文本编辑器。 |

## Task02 验收映射

固定样本覆盖 Paper A 支持、Paper B 冲突、Paper C 上下文、Paper D 缺失、跨页全文定位、错误 citation/chunk/page 拒绝，以及三格式引用编号与 limitations 一致。业务 API、持久化、网络、PDF/Qdrant 和浏览器验收保留给后续 Task，不在本结论中冒充完成。

## 评审依据

- `docs/sdd/plans/030/artifacts/task-02/evidence-report-contract.md`
- Spec029 Task02/Task04：canonical `document_id`、chunk/page、source hash、manifest generation/fingerprint 与删除/重建重验证
- Spec027：只读报告、引用和 limitations 约束
- `tests/test_spec030_contract.py`：4 passed
