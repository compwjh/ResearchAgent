# Spec030 技术评审：Evidence Report Contract v1

- 评审对象：`docs/sdd/plans/030/artifacts/task-02/evidence-report-contract.md`
- 关联 Spec：[`docs/sdd/specs/030-research-evidence-reporting.md`](../specs/030-research-evidence-reporting.md)
- 评审时间：2026-09-17（Asia/Shanghai）
- 评审角色：开发主管视角
- 评审模型：Luna high（临时分派）

## 结论：通过（允许进入 Task03）

Task02 已冻结 `evidence-report-v1` 的数据边界、定位要求、引用 manifest、三格式语义投影和 fail-closed/降级规则。合同与 Spec027/029 既有 citation、canonical document 和 inspection manifest 接缝一致，没有要求复制检索或导入基础设施；未发现技术 P0/P1 阻塞。

## 技术核对矩阵

| 技术点 | 判定 | 依据 |
|---|---|---|
| Claim/Evidence 关系 | 通过 | Claim 状态区分 supported/contested/unresolved；Evidence stance 保留 supports/contradicts/contextual，不静默消解冲突。 |
| 全文 provenance | 通过 | `document_id + chunk_ids + page/page_end + source_sha256 + manifest_generation + manifest_fingerprint + chunker` 与 Spec029 Task04 一致；quote_digest 只允许已定位原文摘要。 |
| 缺失与失效 | 通过 | `missing` 不携带 Evidence；删除、tombstone、hash/generation/fingerprint/chunk 变化降为 unavailable 或 revalidation_required。 |
| CitationManifest | 通过 | citation 编号正整数且连续、每条至少一个 available Evidence，Paper ID 与 Evidence 一致；无法回查即拒绝。 |
| 三格式一致性 | 通过 | Markdown 为权威正文，HTML/JSON 来自同一 canonical model；语义投影不一致返回 `FORMAT_SEMANTIC_MISMATCH`。 |
| 防越界/复用 | 通过 | 合同不引入 downloader、parser、chunker、embedding、reranker、Qdrant collection 或第二套状态机。 |
| 版本与只读 | 通过 | `schema_version` 固定，`report_version` 单调递增，旧版本不可覆盖；生成失败不发布半份视图。 |

## 定向验证

```text
.venv/bin/python -m pytest -q tests/test_spec030_contract.py
4 passed in 0.26s，退出码 0
git diff --check
退出码 0
```

## 门禁边界

本评审只签 Task02 合同，不代表 Task03–05 的业务实现或 Task06 的全量回归、浏览器验收、部署已完成。Task03 必须使用本报告指定的 `evidence-report-v1`；若需改变公开数据模型、关系枚举、失效语义或导出语义，应先退回更新 Spec/合同并重新评审。
