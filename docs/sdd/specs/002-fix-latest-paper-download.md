# 002 修复最新论文无法下载

**状态：已完成**

**实际实现**：已完成 Crossref/OpenAlex 多来源检索、候选标题评分与 DOI 去重、`content-type: unspecified` 链接保留、PDF/文章页探测、HTML 页面 PDF 链接发现、429/超时有限重试、SoK 真实下载验收及相关单元/API 测试。

**当前范围调整**：无法获得合法可访问 PDF 时视为可解释结果，不要求 Agent 伪造下载成功；必须明确告知用户文章是否找到、选中的版本、来源、不可下载原因，并提供文章页面或人工处理入口。

**完成记录**：已实现 Crossref/OpenAlex 多来源检索、标题评分和 DOI 去重、PDF/文章页探测、HTML PDF 链接发现、结构化不可下载提示和有限重试；SoK 真实下载成功；Planning 已找到 SSRN 和期刊版本，在没有可公开 PDF 时返回明确来源状态和文章页面，不绕过访问限制。

**最终验证**：16 个单元/API 测试全部通过；后端全量编译通过；前端 JavaScript 语法检查通过；SoK 文件已完成 PDF 文件头和 SHA-256 校验；最新服务启动后首页和健康接口验证通过。

**验证结果**：13 个单元/API 测试全部通过；SoK 真实下载成功，文件大小 5,450,171 bytes，并完成 SHA-256 校验；Planning 已找到两个高匹配版本，但 PDF 探测结果分别为 `not_found` 和 `invalid`。

## 复现记录

复现文章：`Planning as Graphs: Adaptive Agentic Planning for LLM Agents`

复现接口：`POST /api/agent/run`

复现结果：

- 意图识别为 `download_paper`，置信度 `0.85`。
- Crossref 返回了两条标题高度匹配的候选，标题分别为 `Planning as graphs: Adaptive agentic planning for LLM agents` 和 `Planning as Graphs: Adaptive Agentic Planning for LLM Agents`。
- 两条候选的 `confidence` 都为 `1.0`，但 `pdf_url` 都为 `null`。
- 候选 DOI 分别为 `10.1016/j.eswa.2026.133777` 和 `10.2139/ssrn.6502119`。
- 当前下载服务遇到 `pdf_url` 为空时会抛出“候选文章没有可下载的 PDF 地址”，不会继续解析 DOI、文章页或其他公开来源。

结论：问题可稳定复现，属于本 spec 已定义的“元数据候选存在但公开 PDF 地址发现失败”问题，不创建新的 Bug Spec。

## Bug 描述

输入文章名称 `Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers` 后，Agent 无法稳定找到并下载论文。

## 根因分析

当前默认检索链路只有 Crossref：

1. Crossref 查询结果宽泛，当前实现只取返回结果前 5 条，没有分页、精确标题过滤或候选重排，目标文章可能不在候选列表中。
2. Crossref 的 `link` 链接经常使用 `content-type: unspecified`，当前实现只接受 `content-type` 包含 `pdf` 的链接，导致存在公开下载链接时仍然生成空的 `pdf_url`。
3. 当前没有 OpenAlex、Semantic Scholar、arXiv 等针对最新科研文章的多来源检索和公开 PDF 兜底。
4. 下载服务在候选没有 `pdf_url` 时只回退到全局下载地址的第一个地址，不会基于 DOI、文章页或来源继续解析 PDF 地址。
5. Semantic Scholar 等外部服务可能返回 429，检索 Agent 需要有超时、限流、重试和来源降级策略，不能依赖单一服务。
6. 本次复现还显示同一标题可能同时对应正式期刊记录和 SSRN 预印本，当前系统没有按版本、年份、作者和 DOI 做候选合并与来源优先级提示。

## 一句话目标

让 Agent 能够针对最新科研文章进行多来源检索、精确候选排序和公开 PDF 地址发现；当没有公开下载地址或需要登录时，清晰进入人工确认或 Human-in-the-loop 分支，而不是直接报告笼统下载失败。

## 本次验收标准

- 输入 `Planning as Graphs: Adaptive Agentic Planning for LLM Agents`，Agent 能找到正确文章版本；在存在合法公开 PDF 时完成下载、文件头校验和 SHA-256 记录，在没有合法 PDF 时明确提示原因并提供文章页面。
- 输入 `SoK: Agentic Skills -- Beyond Tool Use in LLM Agents`，Agent 能找到正确文章候选并完成下载；如果公开来源需要登录，则必须进入 Human-in-the-loop，用户完成登录后能继续下载并完成校验。
- 两篇文章都不能因为 Crossref 前 5 条结果、`content-type: unspecified`、缺少直接 `pdf_url` 或单一来源限流而直接返回笼统失败；找不到 PDF 时必须给出结构化来源状态和下一步建议。

## 修复工作流

1. 规范化标题并提取 DOI、作者、年份等线索。
2. 并行或按优先级查询多个元数据源：Crossref、OpenAlex、Semantic Scholar，必要时支持 arXiv。
3. 对结果做去重和精确标题匹配，使用标题相似度、作者、年份、DOI 组合评分；不再无条件使用前 5 条。
4. 为候选建立公开全文发现步骤：优先使用来源明确的 PDF 链接，其次解析 DOI/文章页的公开链接；不能把 `content-type: unspecified` 直接视为不可下载。
5. 对每个候选分别探测 PDF 地址，识别 200 PDF、登录页、401/403、HTML 错误页和 429，并记录来源状态。
6. 有高置信度公开 PDF 时展示候选并允许下载；没有公开 PDF 但文章页需要登录时进入 Human-in-the-loop；没有任何合法来源时给出可解释结果。
7. 对外部 API 增加超时、指数退避、有限重试和来源降级；一个来源 429 或不可用不应阻塞其他来源。

## 数据模型

| 字段 | 类型 | 约束（必填？范围？默认？）|
|---|---|---|
| `query` | string | 必填；长度 1-500 |
| `normalized_title` | string | 必填；用于跨来源检索 |
| `source_name` | string | 必填；`crossref` / `openalex` / `semantic_scholar` / `arxiv` / `configured` |
| `source_rank` | integer | 必填；来源优先级和结果顺序 |
| `title_score` | number | 0-1；精确标题匹配分数 |
| `metadata_score` | number | 0-1；作者、年份、DOI 等综合分数 |
| `doi` | string | 可选；跨来源去重主键，若存在必须标准化 |
| `article_url` | string | 可选；必须是 HTTP(S) |
| `pdf_url` | string | 可选；必须是 HTTP(S)，需要探测确认 |
| `pdf_url_status` | enum | `unknown` / `public_pdf` / `login_required` / `not_found` / `invalid` |
| `requires_login` | boolean | `true` 时不得自动下载，进入 Human-in-the-loop |
| `source_error` | string | 可选；不得包含凭据，记录限流或服务错误 |
| `download_outcome` | enum | `downloaded` / `login_required` / `not_found` / `invalid_source` / `rate_limited` / `source_unavailable` |
| `user_message` | string | 必填；面向用户的明确结果说明，不得只显示内部异常 |
| `confidence` | number | 0-1；低于阈值不得自动选择 |

## 系统设置

| 设置 | 说明 | 默认行为 |
|---|---|---|
| `article_metadata_sources` | 元数据源启用顺序和地址 | Crossref、OpenAlex、Semantic Scholar（可用时） |
| `article_max_candidates_per_source` | 每个来源最大候选数 | `20` |
| `article_retry_count` | 单来源失败重试次数 | `2` |
| `article_retry_backoff_seconds` | 重试退避基数 | `1` |
| `article_pdf_probe_timeout_seconds` | PDF 地址探测超时 | `10` |
| `article_match_threshold` | 自动选择最低匹配分数 | `0.90` |

外部 API 的认证信息必须使用服务器端环境变量或安全配置，不能回显到前端、SSE 或日志。

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况（状态码）|
|---|---|---|---|
| `POST /api/agent/articles/search` | `{ query, authors?, year?, doi? }` | 多来源去重后的候选、标题分数、PDF 状态和任务 ID | `400` 输入无效；`502` 全部来源不可用；`504` 全部超时 |
| `POST /api/agent/articles/probe` | `{ task_id, candidate_id }` | PDF 地址探测结果、来源状态、文章页和明确用户提示 | `400` 候选无效；`401` 需要登录；`404` 无公开文件；`429` 来源限流 |
| `POST /api/agent/articles/download` | `{ task_id, candidate_id }` | 下载进度、文件路径、文件大小和校验结果 | `400` 候选无效；`401` 需要登录；`404` 文件不存在；`413` 超过大小限制；`502` 下载失败 |
| `POST /api/agent/tasks/{task_id}/human-actions/login-completed` | `{ candidate_id }` | 重新探测权限并继续下载 | `400` 状态不允许；`403` 登录后仍无权限；`408` 等待超时 |

## 边界（每条之后会变成一条测试）

- 目标文章不在 Crossref 前 5 条结果中，但在 OpenAlex、Semantic Scholar 或 arXiv 中存在。
- `Planning as Graphs: Adaptive Agentic Planning for LLM Agents` 返回多个高相似候选且 `pdf_url` 为空时，Agent 必须继续做 DOI/文章页/PDF 探测，或明确说明需要用户选择版本。
- 标题大小写、冒号、连字符、Unicode 标点或副标题不同。
- Crossref 返回 `content-type: unspecified`，但链接实际返回 PDF。
- DOI 有文章页但没有公开 PDF，文章页返回登录页面或 401/403。
- 某个来源返回 429、超时、5xx 或非法 JSON，其他来源仍可正常返回候选。
- 多来源返回同一 DOI 时只保留一个候选并合并来源信息。
- 同标题不同年份或不同作者时不能自动选择错误文章。
- 文章页重定向到 HTML、PDF 地址返回登录页、文件头不是 `%PDF-`。
- 所有来源都没有合法公开文件时，Agent 必须明确说明原因、返回 `download_outcome` 和 `user_message`，并提供文章页，不得伪造下载成功。
- 目标文章已有本地文件时应返回已有文件或明确重复下载策略。

## 验证方式

- 使用目标文章标题录制真实元数据响应，验证候选能被找到、去重和正确排序。
- 验收回归：使用 `SoK: Agentic Skills -- Beyond Tool Use in LLM Agents` 作为固定文章样本，验证从检索、候选确认、PDF 地址发现、下载到文件校验的完整链路。
- Mock Crossref 返回宽泛前 5 条，Mock OpenAlex 返回目标文章，验证跨来源补偿。
- Mock `content-type: unspecified` 但响应体以 `%PDF-` 开头，验证能识别为公开 PDF。
- Mock 401/403、登录 HTML、429、超时和 5xx，验证来源降级与 Human-in-the-loop 状态。
- 验证 DOI、标题、作者和年份综合评分，避免下载相似但错误的文章。
- 验证下载文件大小、PDF 文件头、SHA-256、重复下载和危险路径防护。
- API 集成测试覆盖搜索、PDF 探测、下载、登录恢复和任务查询。
- 前端测试覆盖多来源候选、公开 PDF 下载、登录提示、登录完成后继续和失败解释。
- 前端测试覆盖无 PDF、登录要求、来源限流、来源不可用和非 PDF 响应，确保用户看到明确原因和文章页面链接。

## 明确不做（划出范围，防 AI 自由发挥）

- 不绕过付费墙、登录限制、验证码、访问控制或版权保护措施。
- 不把文章页 HTML、登录页或错误响应保存为 PDF。
- 不因为某一外部 API 限流就无限重试或阻塞整个 Agent。
- 不在本 Bug 修复中加入 PDF 全文解析、向量数据库或科研结论生成。
- 不代替用户输入密码，不保存或回显 Cookie、Token 等登录凭据。

---
**三条自检**：①每条规则能不能写成测试？不能就是没说清。②人能在 2 分钟内审完吗？③范围划死了吗？
