# Spec018 单文档重建后的来源区间诊断

- 日期：2026-10-26
- 范围：只读核对单文档 `d4dfd2a620384ad5bece27320661f8f0` 的本次 `chunker=all` 重建产物；未触发重建、模型/网络访问、下载或主数据写入。
- 对应请求：[`reindex-request-response.json`](artifacts/20261026-reindex-entry/reindex-request-response.json)
- 对应状态：[`reindex-status.json`](artifacts/20261026-reindex-entry/reindex-status.json)

## 结论

本次结果不能标记为“全量成功”。v1 仍为 `ready`（107/107），v2 是 `partial`/`indexed_partial`：当前 manifest 有 297 个 v2 chunk，其中 277 个已映射、20 个以 `SOURCE_RANGE_UNRESOLVED` 留在未映射集合中。20 个未映射项均落在 PDF 的图表/坐标轴/表格碎片上；按 Spec018 的 source-anchor-v2 契约，它们属于无法唯一、精确定位的合法不支持/歧义情况，不应通过模糊匹配伪造来源区间。

另有独立且更严重的索引一致性问题：当前 v2 manifest 只覆盖 chunk index `0..296`，而本地 Qdrant 对同一文档仍有 v2 points `0..307`（308 个），其中 `297..307` 的 11 个 page-18 points 不在当前 manifest，也不在当前 20 项未映射统计中。当前状态因此是“manifest/状态与实际 point snapshot 不一致”，属于发布/一致性缺陷；不能把顶层文档 `status=indexed`、`error=null` 解读为 v2 已完整可验收。

## 证据与对象身份

| 项目 | 只读观察 |
|---|---|
| 文档 | `How to Peel a Million- Validating and Expanding Bitcoin Clusters.pdf`，18 页 |
| document_id | `d4dfd2a620384ad5bece27320661f8f0` |
| source size / SHA-256 | `762149` bytes / `71f8829f2e1d36ab2695ebcf1c1697e301e429eb1aea5225981f526be98a14a1` |
| 请求 | 2026-10-25T17:35:00.930349+00:00，`chunker=all`，HTTP 202，task `c4ab10b585f24a0689be67bdce0b4d6c` |
| 最终状态记录 | v1 `indexed` 107/100、error null；v2 `indexed_partial` 297/100、error `SOURCE_RANGE_UNRESOLVED` |
| `papers.json` | 顶层 `status=indexed`、`error=null`；legacy chunk_count 107；v1 indexed 107，v2 indexed_partial 297 |
| 源文件 | `data/kb/manifests/d4dfd2a620384ad5bece27320661f8f0/v1.json` 与 `v2.json`，source hash 均为 verified |

顶层状态与 v1 兼容投影相符，但不能覆盖 v2 的 partial 状态。

## 当前 manifest 的区间统计

| chunker | manifest 状态 | chunks | mapped | unmapped | 原因 |
|---|---:|---:|---:|---:|---|
| v1 | ready | 107 | 107 | 0 | — |
| v2 | partial | 297 | 277 | 20 | `SOURCE_RANGE_UNRESOLVED` |

v1 manifest 为 504 blocks、566 anchors；v2 为 504 blocks、465 anchors。两者均使用 `source-anchor-v2` 与 `pymupdf-display-dict-insertion-v2`。v2 的 20 个 unresolved chunk index 为：

```text
56,
150, 153,
166, 169, 170,
180, 181, 182, 183, 186, 187, 188, 189, 190, 191, 193, 195, 198, 202
```

按页归组：p7 为 `56`；p11 为 `150,153`；p12 为 `166,169,170`；p13 为 `180,181,182,183,186,187,188,189,190,191,193,195,198,202`。代表文本是图表坐标轴或孤立标签，例如 `101 102 103 104 105 106 107`、`1.00`、`Truth Class error`、`# of transactions`、`Clusters`、`Transactions`、`1`、`3`、`41`、`9`、`11` 等；均为 `is_citation=false` 的图表/表格碎片，而非正文段落。

`source-anchor-v2` 只接受规范化源文本中唯一、精确的完整区间；不能唯一定位时返回 unresolved，禁止 fuzzy fallback。因此上述 20 项是当前契约下的合法 partial 结果，而不是应被强行补齐的算法错误。若产品以后要求每个图表标签都可定位，应另行定义图表级 provenance 扩展，不能改变本次验收结论。

## manifest 与 Qdrant snapshot 不一致

对本地 Qdrant 的只读 payload 核对显示：目标文档共有 415 points，即 v1=107、v2=308。v1 索引为 `0..106`；v2 索引为 `0..307`。当前 v2 manifest 为 `0..296`，没有 manifest-only index；因此多出的完整 11 个 points 是：

```text
v2 chunk index 297..307（全部为 page 18 的引用/正文/页脚尾部）
```

对共同的 `0..296`，manifest 与 Qdrant payload 的 `text`、`page`、`page_end`、`section` 均未发现不一致；所有 415 points 的 document id 与 source SHA 也一致。这说明当前 manifest 是 297-chunk 新快照，而 Qdrant 仍保留了旧 308-chunk 快照的尾部，且这 11 个旧 points 没有进入当前 `unmapped_count`。`data/kb/index-generation.json` 与 rebuild run `38efa91a33154fd097c61d1c745d408f` 仍记录旧的 v2=308/total=415 生成快照，也进一步证明生成标记、manifest、point 集合没有形成同一原子快照。

这不是 20 个图表区间的 source-anchor 算法问题，而是索引发布/清理一致性问题。实现路径中旧 points 删除失败被吞掉、写入后没有对目标文档+chunker 的实际 point 集合做精确校验，能够解释这一现象；当前证据未包含删除异常日志，因此这里标记为“与该路径一致的可能机制”，不声称已直接证明具体异常。

## 前端必须诚实呈现

前端应以 chunker 级 manifest 为准，而不是仅依据顶层 `status=indexed`：

1. v1 可独立显示 ready/107 mapped。
2. v2 必须显示 `partial`（277/297 mapped、20 unresolved、原因 `SOURCE_RANGE_UNRESOLVED`），并保留“部分来源区间不可定位”的可见告警。
3. 由于 v2 manifest 与实际 Qdrant point 集合不一致，在一致性校验修复前不得将 v2 显示为完整 ready，也不得把 308 个 points 当成当前 manifest 的完整可检视结果；应显示需要重建/一致性修复的诊断，或禁用会误导用户的 v2 精确定位入口。

## 最小下一步（本次未执行）

在批准的修复范围内增加并置于发布前的只读一致性门禁：枚举目标文档+chunker 的实际 Qdrant point index 与 payload fingerprint，与即将发布的 manifest 做精确集合和内容比对；不一致时 fail closed，不发布 ready/partial 元数据快照，并将删除失败显式暴露而非吞掉。确认快照一致后，再从受保护源与已知 snapshot 做一次受控修复/重建。20 个图表 unresolved 项应保留为 partial；是否增加图表级定位另立范围，不应采用模糊匹配。

## 范围声明

本报告只诊断本次单文档重建结果；监视任务以 exit 130 停止是观察终止，不等于产品任务失败。未进行新的 reindex、网络/模型调用、下载、全量回归或主数据修复，也未将该结果标记为 Spec018 的完整成功。
