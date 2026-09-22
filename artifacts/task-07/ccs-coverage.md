# Spec032 Task07：ACM CCS 官网目录覆盖证据

## 结论

- 状态：**NO-GO / 未验证（全年度覆盖）**
- 审计时间：2026-09-20（官方页面只读审计；未下载 PDF、未探测 PDF、未调用导入链）
- 结论边界：2021、2022、2024 确实存在可读的官方 accepted/proceedings 页面，但其可稳定取得的字段主要是标题/作者；页面没有统一 DOI、摘要、关键词或逐篇 PDF 身份键。2023 的官方程序页返回动态数据库故障提示，2025 accepted 页面要求 JavaScript 且 accepted sections 为空。故不能把三年的静态页面拼成 CCS 2021–2025 官网年度覆盖，也不能在现有 SourceRegistry/WorkerTool 上安全接入一个“看似官方”的半套 parser。
- 现有实现：`backend/app/paper_discovery/infrastructure/ccs_publication_source.py` 仍是 Crossref 年度 work-list + OpenAlex 富化；`ccs_paper_parser.py` 只解析 JSON；未新增官方路由、parser 或 fixture。
- 已验证为官网覆盖：**无**（Crossref/OpenAlex 固定样本不计入官网覆盖）
- 可保留的降级链：Crossref 目录枚举 + OpenAlex 缺失字段补齐，字段 provenance 继续标注真实来源。
- 下载/入库：未执行；目录阶段不得探测 PDF。

## 官方入口逐年审计

| 年份 | 官方页面 | 受控只读观察 | 稳定字段/身份结论 | 状态 |
|---:|---|---|---|---|
| 2021 | <https://sigsac.org/ccs/CCS2021/accepted-papers.html> | 静态 HTML；页面标题为 `ACCEPTED PAPERS`，正文连续列出标题和作者 | 标题、作者、页面年份可读；未发现统一 DOI/摘要/关键词/逐篇 PDF 身份字段，不能可靠与 Crossref 候选一一绑定 | `blocked_identity` |
| 2022 | <https://sigsac.org/ccs/CCS2022/program/accepted-papers.html>；补充 proceedings 页 <https://www.sigsac.org/ccs/CCS2022/proceedings/ccs-proceedings.html> | accepted 页可读；proceedings 页含 `Keynote Talks`、`Full Papers` 等混合 session | accepted 页仍主要只有标题/作者；proceedings 页有摘要但需按 session 排除 keynote/workshop，且身份链接指向 ACM DOI，未形成可复用的 accepted-list HTML 合同 | `blocked_identity` |
| 2023 | <https://www.sigsac.org/ccs/CCS2023/program.html> | 页面正文出现 `Something doesn't seem right?`、`Reload the Database`、搜索输入框；程序数据未稳定呈现 | 依赖动态数据库/JavaScript；不能从受控 HTML 固定出 accepted 主会条目或稳定字段。官方 `program.pdf` 不纳入本任务（禁止下载/解析 PDF） | `blocked_js_or_data` |
| 2024 | <https://www.sigsac.org/ccs/CCS2024/program/accepted-papers.html> | 静态 HTML；`ACCEPTED PAPERS` 下分 `First Cycle`/`Second Cycle`，提供 Title/Author 列表 | 标题、作者和页面年份可读；页面未提供统一 DOI、摘要、关键词或逐篇 PDF。仅凭标题不能满足现有候选身份绑定和年度覆盖证明 | `blocked_identity` |
| 2025 | <https://www.sigsac.org/ccs/CCS2025/accepted-papers/> | 非浏览器抓取正文为 `This website requires JavaScript to function properly`；`First Cycle`/`Second Cycle` 标题下无论文字段 | JS/API 依赖和空正文使 accepted 列表、字段、身份均不可验证；不能猜测 API、请求参数或绕过站点运行时 | `blocked_js_or_data` |

## 为什么不实施最小 parser/source

1. 现有统一 Tool 只能接收已注册来源的确定性 adapter；给 CCS 增加一个只覆盖 2021/2022/2024 的官方 parser，会使 `verified_years`、authority 和年度 coverage 语义看起来完整，却无法覆盖 2023/2025。
2. 静态页面虽有标题/作者，但缺少稳定 DOI/详情链接；用标题+年份回连 Crossref 会遇到同名、cycle、workshop/主会边界和版本漂移，不能把聚合候选身份伪装成官网身份。
3. 2023/2025 的页面内容由 JavaScript/数据库运行时提供；本任务禁止猜 API、提交任意 URL、绕过身份/反爬，也禁止以官方 PDF 下载替代 HTML 目录合同。

因此不新增 `official` route、parser、fixture 或 SourceRegistry/WorkerTool 接线。待后续任务取得可复现的官方 HTML/JSON endpoint、稳定身份字段（至少 title/year + DOI 或受控详情键）和逐字段 missing/provenance 规则后，再重新审计；现有 Crossref/OpenAlex fallback 保持不变。

## 可重现性与证据边界

- 页面证据为官方 URL 的受控只读检查，来源正文/字段观察记录在上表；没有把搜索结果、聚合元数据或 PDF 作为官网 fixture。
- 因 2023/2025 无稳定正文且 2021/2022/2024 缺少可绑定身份键，本轮**不生成 HTML fixture、不计算 fixture hash、不宣称论文数/摘要缺失比例/PDF 或入库比例**。
- 统一 `paper_discovery` Tool 在本任务环境不可调用；未以自定义 HTTP/URL 代替它，也未对任何 PDF 发出请求。
- 该产物是 bounded NO-GO 交接，不代表官方页面永久不存在；页面可用性、身份字段或官方 endpoint 变化后必须重新取证。

## 风险与后续入口

- **P1：身份错配**：标题+作者+年份无法保证与 DOI 记录一一对应，不能自动合并或导入。
- **P1：年度不完整**：2023/2025 不能稳定解析；不得将 2021/2022/2024 的页面存在性写成 CCS 2021–2025 覆盖。
- **P2：字段缺失**：官方 accepted 页面没有摘要/关键词/逐篇 PDF；若后续实现，必须将这些字段显式标为 `missing`，由 Crossref/OpenAlex 按字段补缺。
- **解除条件**：提供受控、无需凭据、可复现的 2023/2025 HTML/JSON 目录单元；为五年统一确认主会边界、稳定身份键、允许主机、hash/ETag 和错误码；再补官方 fixture 与 parser/source contract 测试。
