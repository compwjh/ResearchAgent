---
name: semantic-scholar-download-orchestration
description: 受控使用 Semantic Scholar Academic Graph API 查找开放获取论文 PDF，并复用现有安全下载与知识库导入链；不抓取搜索页、Reader HTML 或绕过登录/付费墙。
tools: [paper_discovery, download_and_import_paper]
---

# Semantic Scholar 开放 PDF 回退编排

本技能只负责回退决策。Semantic Scholar API 负责返回论文元数据和
`openAccessPdf.url` 候选；实际 URL 校验、PDF 校验、去重、索引和补偿必须继续由
现有 `paper_discovery` / `download_and_import_paper` Tool 执行。

## 固定顺序

1. 先使用候选自身的官方 PDF 或 prepublication PDF。
2. 再使用已有的严格匹配 arXiv 回退。
3. 前两层失败时，用候选已有 DOI 或 ArXiv ID 查询 Semantic Scholar。
4. 只有 API 返回的 `openAccessPdf.url` 主机已经在服务端固定 allowlist 中时，才交给导入 Tool。
5. 没有 OA URL、匹配不确定、主机未登记、API 失败或下载校验失败时，保留稳定错误码并转人工下载/上传。

## 输入与匹配

- 优先使用 `DOI:<normalized-doi>`，其次使用 `ARXIV:<id>`。
- 不把搜索页、Reader hash、用户任意 URL、Cookie、Token 或 Authorization 作为后端输入。
- 返回记录必须与原候选的标题、作者和年份核对；不一致时返回
  `SEMANTIC_SCHOLAR_MATCH_UNCERTAIN`，不得导入。
- Semantic Scholar 只补缺失的摘要/作者等字段，不覆盖官方会议字段，也不改变论文主身份。

## 安全边界

- API 固定请求 `api.semanticscholar.org`，API key（若有）只从服务端
  `SEMANTIC_SCHOLAR_API_KEY` 读取，不写入日志、候选、事件或前端。
- 不根据 API 返回 URL 动态扩大 allowlist；未登记 PDF 主机返回
  `SEMANTIC_SCHOLAR_UNSUPPORTED_PDF_HOST`。
- 不抓取 Semantic Scholar 搜索页或 Reader 页面，不绕过验证码、登录、订阅或付费墙。
- 所有可下载地址仍须经过现有 DNS/peer IP、逐跳重定向、大小、PDF 魔数、页数和临时文件清理。

## 稳定失败语义

`SEMANTIC_SCHOLAR_UNAVAILABLE`、`SEMANTIC_SCHOLAR_RATE_LIMITED` 可有限退避重试；
`SEMANTIC_SCHOLAR_AUTH_FAILED`、`SEMANTIC_SCHOLAR_NOT_FOUND`、
`SEMANTIC_SCHOLAR_NO_OPEN_PDF`、`SEMANTIC_SCHOLAR_MATCH_UNCERTAIN` 和
`SEMANTIC_SCHOLAR_UNSUPPORTED_PDF_HOST` 不得无限重试，转人工处理。
