# Spec030 Task02：Evidence Report Contract v1

## 结果状态

```text
result=GO_FOR_TASK03
schema=evidence-report-v1
claim_evidence_contract=FROZEN
citation_manifest=FROZEN
format_semantic_parity=FROZEN
degradation_rules=FROZEN
business_code_changed=false
network_or_real_data=false
```

Task02 冻结后续证据矩阵（Task03）和报告生成/导出（Task04）共同使用的最小结构合同。合同只描述可追溯事实与状态，不授权新建检索、chunker、下载器、导入状态机或第二套报告存储。

## 1. 版本与不变量

- 顶层 `schema_version` 固定为 `evidence-report-v1`；同一 `report_id` 的 `report_version` 单调递增，旧版本只读、不可覆盖。
- `task_id`、`plan_version`、`report_id` 和 `report_version` 必填；报告状态为 `draft | generating | completed | partial | failed`。
- Markdown 是权威可移植正文；HTML 和 JSON 必须从同一结构化报告模型渲染。JSON 至少包含结构化报告和完整 `citation_manifest`，不能把 HTML/Markdown 再解析为事实来源。
- 论文事实只能来自 `Evidence`；模型生成的未定位摘录不是证据，不能写入 `fulltext`。

## 2. Claim / Evidence 模型

### ResearchClaim

| 字段 | 约束 |
|---|---|
| `claim_id` | 报告版本内唯一、稳定字符串；引用该 Claim 的 Evidence 必须反向指向它 |
| `task_id` | 必须等于报告 `task_id` |
| `topic` / `statement` | 非空；`statement` 是可审计结论，不隐含未提供的论文事实 |
| `confidence` | `low | medium | high`；是结论置信度，不代替证据等级 |
| `status` | `supported | contested | unresolved`；`contested` 表示存在冲突，不能压平为支持 |
| `evidence_ids` | 只能引用同一报告版本已登记的 Evidence；可为空，但此时 Claim 必须是 `unresolved` 并进入 limitations |

### ClaimEvidence

| 字段 | 约束 |
|---|---|
| `evidence_id` / `claim_id` / `paper_id` | 三者必填且唯一关系可回查；`paper_id` 是目录论文 ID，不是 KB `document_id` |
| `evidence_level` | `catalog | abstract | fulltext`；只能由已有来源与定位能力证明 |
| `stance` | 仅 `supports | contradicts | contextual`。支持、冲突和上下文都是有证据的关系 |
| `status` | `available | unavailable | revalidation_required`；只有 `available` 可以作为当前有效证据 |
| `locator` | 按证据等级满足下述定位合同；不可定位或引用不存在的 locator 必须拒绝整个 payload |

证据等级定位规则：

- `catalog`：只能带服务端 `catalog_snapshot_id`/论文目录引用，不得进入方法或结果比较。
- `abstract`：必须带服务端目录/摘要引用和 `abstract_digest`；摘要可支持范围内结论，但不能伪称全文细节。
- `fulltext`：必须复用 Spec029 的 canonical `document_id`、非空确定性 `chunk_ids`、正整数 `page`/`page_end`（`page_end >= page`）、`source_sha256`、`manifest_generation`、`manifest_fingerprint` 和 `chunker`。`quote_digest` 必须是已定位原文的 SHA-256，不保存模型改写文本作为出处。

## 3. 支持、冲突、上下文和缺失

矩阵 `PaperComparisonCell.relation` 固定为 `supports | contradicts | contextual | missing`：

- `supports`：至少一个 `ClaimEvidence.stance=supports`，同一 Claim 和论文 ID 一致。
- `contradicts`：至少一个 `stance=contradicts`；保留冲突，不以投票或置信度静默消解。
- `contextual`：证据提供背景、边界或适用条件，不直接证明 Claim 成立/不成立。
- `missing`：`evidence_ids=[]`，必须提供 `missing_reason`；它是覆盖缺口，不是 Evidence，也不能出现在 citation manifest 中。

Claim 的 `evidence_ids` 为空或存在当前不可用 Evidence 时，当前矩阵单元格降为 `missing`/缺口状态，报告至少为 `partial`，并把原因写入 `limitations`。历史报告正文保留原样，但当前引用不得继续声称 `fulltext`。

## 4. CitationManifest

```json
{
  "manifest_version": 1,
  "report_id": "report-030-1",
  "citations": [
    {"citation_no": 1, "paper_id": "paper-a", "evidence_ids": ["evidence-1"]}
  ]
}
```

- `citation_no` 为报告版本内从 1 开始的唯一正整数；正文中的 `[n]`、HTML 的 `data-citation-no="n"`、JSON manifest 必须一一对应。
- 每条 citation 必须至少有一个 Evidence；所有 Evidence 必须存在、属于同一报告版本、属于该 `paper_id`，且状态为 `available`。
- 主要 Claim 至少关联一个 citation；无法由 manifest 回查到 Claim → Evidence → Paper/locator 的报告 payload 必须 fail closed。
- 论文删除、manifest tombstone、source hash/generation/fingerprint/chunk 定位变化后，不删除历史 manifest；当前视图把 Evidence 标为 `unavailable` 或 `revalidation_required`，并降级 Claim/矩阵，不伪造新 locator。

## 5. 三格式语义一致

三种只读视图的 canonical 语义投影必须相同：

```text
(report_id, status, claims[id/statement/evidence_ids],
 evidences[id/paper_id/level/stance/status],
 cells[claim_id/paper_id/relation/evidence_ids],
 citation_manifest[citation_no/paper_id/evidence_ids], limitations)
```

允许格式差异：Markdown 的标题和 `[n]`、HTML 的安全 DOM 标记/转义、JSON 的字段类型。禁止格式差异：Claim 文本、Evidence ID、关系、证据等级/状态、citation 编号、limitations 或 Paper ID。语义投影不一致时导出拒绝并返回稳定错误 `FORMAT_SEMANTIC_MISMATCH`；不发布半份报告。

## 6. 拒绝与降级规则

| 条件 | 处理 |
|---|---|
| Schema、枚举、ID 关系、页码/chunk、source hash 或 manifest 定位不合法 | 拒绝写入，`REPORT_SCHEMA_INVALID` 或 `EVIDENCE_LOCATOR_INVALID` |
| Citation 缺失、重复、指向删除/不存在 Evidence，或 Paper ID 不一致 | 拒绝写入/导出，`CITATION_MANIFEST_INVALID` |
| 只有标题级 catalog 候选，缺少摘要/全文定位 | 保留候选但单元格 `missing`，加入 limitations；不进入方法/结果比较 |
| 全文文档删除或 provenance 变化 | `unavailable` / `revalidation_required`；历史正文不可覆盖，当前报告降为 partial |
| 模型输出结构校验失败、生成中断 | 不发布报告版本，保留失败状态；不得把半份 Markdown/HTML/JSON 当作完成品 |
| 可用证据不足但结构仍完整 | 发布 `partial`（若产品流程允许），明确缺口；绝不使用常识补齐论文事实 |

## 7. 固定样本与验证

固定样本位于 `tests/test_spec030_contract.py`，覆盖：Paper A 支持、Paper B 冲突、Paper C 上下文、Paper D 缺失；全文 locator 的跨页范围；错误 citation、错误页码/chunk 的 fail-closed；删除/失效降级；Markdown/HTML/JSON 引用编号和 limitations 语义一致。

验证命令：

```text
.venv/bin/python -m pytest -q tests/test_spec030_contract.py
git diff --check
```

## Go / No-Go

- **GO**：Task03 可按本合同实现矩阵关系、缺失单元格和 limitations；Task04 可按同一结构实现不可覆盖报告版本及三格式导出。
- **NO-GO**：业务实现若创建第二套 Evidence/检索/导入模型，或无法完成 Claim → Evidence → Paper/locator → CitationManifest 回查，必须停工并退回本 Task 修订合同。

## 交接信息

- 决策依据：Spec030 数据模型/失败场景/验收条款；Spec029 Task02/Task04 的 canonical document、inspection manifest、chunk/page provenance 与删除/重建 revalidation；Spec027 的只读报告和 citation/limitations 约束；既有 `citation_payloads()` 的 document/chunk/page 定位。
- 风险：Task03/04 仍需把合同接入真实 ResearchStore/报告 API；本 Task 未验证业务持久化、网络、PDF/Qdrant 或浏览器。
- 阻塞：无 Task02 合同级阻塞；若既有报告持久化不能保存 `report_version`/manifest，需要在 Task04 进入前扩展 spec 并重新评审。
- 主 Agent 后续动作：读取本报告；将 Task02 标记完成并把 Task03 依赖锁定为 `evidence-report-v1`；分派 Task03 结构化矩阵实现；Task04 复用同一 canonical model 做版本和导出。
- 时间：开始 `2026-09-17T01:56+08:00`（约）；结束 `2026-09-17T02:00+08:00`；耗时约 4 分钟。
- 模型：Luna high（临时分派）；工具：文件读取/编辑、定向 pytest、`git diff --check`；未使用网络或真实数据。
