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
