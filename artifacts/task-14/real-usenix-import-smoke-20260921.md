# Spec032 Task14：USENIX 检索到导入真实 Smoke

> 时间：2026-09-21（Asia/Shanghai）
> 服务：`http://127.0.0.1:18080`，`RERANKER_ENABLED=false`

## 检索

请求：

```http
POST /api/papers/searches
Content-Type: application/json

{"query":"agent security","conference_ids":["usenix-security"],"years":[2024]}
```

结果：

- `search_id=38bc15ac3a7c4a359bcbf0d5fd73fad0`
- 终态：`partial`；USENIX 单源 `completed`，DBLP 按受控范围 `SOURCE_SKIPPED`
- 总候选：227 篇
- 第一页包含标题、摘要、年份、官方详情页和 `abstract_status=available`
- 搜索阶段未下载 PDF

## 受控导入

从服务端冻结结果中选择第一篇候选：

- 标题：`"What Keeps People Secure is That They Met The Security Team": Deconstructing Drivers And Goals of Organizational Security Awareness`
- `catalog_paper_id=ff93de0782629d6876f5cc97d93f919f`
- 年份：2024
- 官方详情页：`https://www.usenix.org/conference/usenixsecurity24/presentation/hielscher`

请求：

```http
POST /api/papers/imports
Content-Type: application/json

{"search_id":"38bc15ac3a7c4a359bcbf0d5fd73fad0","candidate_id":"ff93de0782629d6876f5cc97d93f919f"}
```

实际响应：

```json
{
  "paper_id": "cacd8936bc074af7a8eb0b2fc9c5df30",
  "stored_name": "2024-USENIX-Security-What-Keeps-People-Secure-is-That-They-Met-The-Security-Team-Deconstructing-Drivers-And-Goals-of-Organizational-Security-Awareness.pdf",
  "status": "indexed",
  "error_code": null,
  "existing": false
}
```

## 判定

PASS：USENIX 官方目录 → 冻结候选快照 → 既有下载/身份校验/知识库索引链已真实贯通；没有接收客户端任意 URL，也没有在搜索阶段下载 PDF。

这只证明一个公开候选的真实成功样本，不代表四会议逐年覆盖、登录恢复或 Spec032 已完成。后续仍需验证失败队列、人工修复、服务重启句柄和独立评审签字。

## 导入后 provenance 复核

`GET /api/papers/ff93de0782629d6876f5cc97d93f919f/provenance` 返回 HTTP `200`，目录记录的 `index_status` 为 `indexed`，官方详情页仍可读，摘要保持可用。该端点的 `paper_id` 是目录候选 ID；导入响应里的 `paper_id=cacd8936bc074af7a8eb0b2fc9c5df30` 是知识库文档句柄，两者按现有领域边界分别使用，不能混用。

## 重启后复核

服务按 `PORT=18080 RERANKER_ENABLED=false ./deploy/start.sh` 重启后复核：

- `GET /api/health`：HTTP `200`，`paper_discovery_enabled=true`。
- `GET /api/ready`：HTTP `200`，jieba、Ollama、embedding、Qdrant 均为 `ready`。
- 再次读取同一目录候选的 provenance：HTTP `200`，`index_status=indexed`，标题、摘要和官方详情页仍在 SQLite 目录记录中。

结论：重启不会丢失该 USENIX 目录记录或其导入状态；本样本可供后续人工验收复现。

## 多来源探针（未宣称通过）

为确认 Spec032 的非 USENIX 运行时边界，发起了仅包含目录元数据的 IEEE S&P 2024 同步：

```http
POST /api/papers/sources/ieee_sp/sync
{"scope":{"years":[2024]}}
```

同步任务 `sync-ieee_sp-5685719bd4884ffb` 被正确入队并可查询，但终态为 `failed`、`error_code=SOURCE_FAILED`、`paper_count=0`。这不是论文 PDF 下载失败，而是来源目录同步尚未形成可供导入的候选，因此本轮没有向你索取替代下载路径。该结果保留为 Task14 的真实阻塞证据：IEEE S&P 不能被标记为已验证，后续需要先定位来源同步失败，再进行候选导入探针。

修复官方目录解析器后重启服务，第二次同步 `sync-ieee_sp-b27e19949f8d4c00` 终态为 `completed`：

- 抓取单元：`ieee_sp|sp|2024|official`
- 目录论文数：43
- `error_code=null`，`degraded=false`
- 未下载或探测任何 PDF

因此 IEEE S&P 2024 的“官方目录 → 结构化元数据”链路已恢复；候选导入仍需单独走统一安全下载链，不能把目录同步成功当作 PDF 导入成功。

随后完成同一服务实例的其他会议元数据探针：

| 来源 | 同步单元 | 论文数 | 终态 | PDF 行为 |
|---|---|---:|---|---|
| NDSS | `ndss|ndss|2024|official` | 142 | `completed` | 未下载/探测 |
| ACM CCS | `ccs|ccs|2024` | 328 | `completed` | 未下载/探测 |

这两项只证明目录同步与 SQLite 持久化成功；四会议搜索入口和具体候选导入仍需 Task14 后续闭环。
