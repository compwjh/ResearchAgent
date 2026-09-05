# Spec 015 Task 02 基线与数据源子批次评审

## 执行信息

- 执行角色：tester（子批次：数据源与本地基线；不含 Playwright 登录）
- 执行目录：`/Users/wjh/ResearchAgent`
- 开始时间：2026-09-04 15:42:12 CST
- 结束时间：2026-09-04 15:49:42 CST
- 约束：只读核对与验证；不修改业务代码、Spec015 计划/Spec、`.env` 或用户当前未提交改动；不执行 `reset`、`clean`、`stash`、`push`

## 结论

本轮结论：**No-Go（限缩范围下的阶段性 No-Go）**。

- `OpenAlex`：**Go with caveats**。DOI 精确补全、摘要/OA 字段和“0 命中不报错”的降级路径都成立，可以作为 DBLP 之后的补全层。
- `DBLP Search`：**部分 Go**。`CCS 2023/2024`、`SP 2024`、`NDSS 2024` 的 live 查询能返回结构化 JSON，但已实测出现 `429`、`500`、`503` 和 `curl exit 28` 超时，且 `conf/uss` 流会把 `SOUPS @ USENIX Security Symposium` 混进结果，不能把 stream 命中当作主会论文。
- `DBLP Venue Search`：**未放行**。本轮多次 live 请求只拿到 `429`/`503`，没有成功样本，无法证明“搜索并新增非内置会议”这一前提已被真实验证。

因此，若现在直接进入 Task 03 编码，会把“今天的 DBLP 行为不稳定”和“USENIX 主会过滤规则未冻结”一起带入实现。建议先把 DBLP 的查询/重试/缓存/过滤契约写死，再继续实现；否则至少把 Venue Search 和 USENIX 主会识别保留为阻塞项。

## 本地代码现状

- [backend/app/services/article_search.py](/Users/wjh/ResearchAgent/backend/app/services/article_search.py:44) 统一用 `httpx.get(..., timeout=settings.article_request_timeout_seconds, trust_env=False)` 发请求，有重试，但没有显式 `User-Agent`，也没有 DBLP 专用客户端。
- [backend/app/services/article_search.py](/Users/wjh/ResearchAgent/backend/app/services/article_search.py:79) 当前 OpenAlex 查询只用 `search=`，适合宽召回，不足以替代 DBLP 的会议/年份约束。
- [backend/app/core/article_settings.py](/Users/wjh/ResearchAgent/backend/app/core/article_settings.py:14) 默认元数据源仍只有 `crossref`、`openalex`；[backend/app/core/article_settings.py](/Users/wjh/ResearchAgent/backend/app/core/article_settings.py:25) 请求超时默认为 `30s`。

## 数据源判定

### 1. DBLP Publication Search

| 会议 | 年份 | live 结果 | 样本/观察 | 判定 |
|---|---:|---|---|---|
| CCS (`conf/ccs`) | 2024 | `HTTP 200` | 主会样本：`FuzzCache...`（pages `511-524`）；Workshop 样本：`AACD '24: 11th ACM Workshop...`；poster-like 样本：`Catch Me if You Can...`（pages `5098-5100`） | 可用，但必须过滤 |
| CCS (`conf/ccs`) | 2023 | `HTTP 200` | 主会样本：`HE3DB...`（pages `2930-2944`）；Workshop 样本：`CCSW '23: Cloud Computing Security Workshop.` | 可用，但必须过滤 |
| USENIX Security (`conf/uss`) | 2024 | `HTTP 200` | 前 5 条全部为 `SOUPS @ USENIX Security Symposium`，无主会论文样本 | **不满足主会过滤前提** |
| USENIX Security (`conf/uss`) | 2023 | `HTTP 500` | DBLP 返回 error page | 未验证 |
| IEEE S&P (`conf/sp`) | 2024 | `HTTP 200` | 混有 `10.1109/SPW63631...`（workshop）与 `10.1109/SP54263...`（主会）两类 DOI 前缀 | 可用，但必须过滤 |
| IEEE S&P (`conf/sp`) | 2023 | `curl exit 28 / HTTP 000` | 20s 超时无响应 | 未验证 |
| NDSS (`conf/ndss`) | 2024 | `HTTP 200` | 前 5 条均为 `venue=NDSS` 的主会论文样本，未见 workshop 混入 | 当前样本可用 |
| NDSS (`conf/ndss`) | 2023 | `curl exit 28 / HTTP 000` | 20s 超时无响应 | 未验证 |

过滤依据（基于 live 返回与 DBLP 页面事实）：

- `CCS`：仅靠 `stream:conf/ccs` 不够。至少要排除标题含 `Workshop`、会议简称后缀如 `CCSW` 的记录；对 `pages` 很短的记录要单独标记人工复核，因为 DBLP 字段里没有稳定的 `poster=true`。
- `USENIX Security`：`conf/uss` stream 命中会混入 `SOUPS @ USENIX Security Symposium`。必须再加 `venue_aliases` 白名单，只接受 `USENIX Security` 主会别名；不能只认 stream。
- `IEEE S&P`：live 结果已显示 workshop/main 可通过 DOI/venue 细分。`SPW...` 对应 workshop，`SP...` 主会与 `IEEE Symposium on Security and Privacy` 主会别名需要单独白名单。
- `NDSS`：2024 样本较干净，但 2023 没拿到 live 第二年样本，本轮不能把“总是干净”当成已验证事实。

### 2. DBLP Venue Search

| 请求 | 结果 | 说明 |
|---|---|---|
| `https://dblp.org/search/venue/api?q=network and distributed system security...` | `HTTP 429` | 真实限流 |
| `https://dblp.uni-trier.de/search/venue/api?q=usenix security...` | `HTTP 503` | mirror 不可用 |

结论：本轮没有成功的 live `venue/api` 样本，无法证明“用户搜索会议并保存受控 `dblp_stream`”已经被真实验证。只能确认该接口今天存在明显限流/可用性风险，必须设计退避、缓存和前端稳定错误提示。

### 3. OpenAlex 补全与降级

| 用例 | 结果 | 说明 |
|---|---|---|
| DOI：`10.1145/3658644.3690240` | `HTTP 200`, `count=1` | 命中 `Functional Adaptor Signatures...`，返回 `doi`、`publication_year=2024`、`open_access`、`abstract_inverted_index` |
| 标题：`A Practical and Secure Byzantine Robust Aggregator` | `HTTP 200`, `count=5912` | 首条是无关的 AAAI 2019 论文 `RSA: Byzantine-Robust...`，说明标题搜索宽召回且 relevance 不足以替代会议/年份约束 |
| 伪 DOI：`10.9999/not-a-real-doi` | `HTTP 200`, `count=0` | miss 行为稳定，适合做“DBLP-only 结果 + warning”而非异常 |

结论：OpenAlex 适合作为 DOI 优先、标题兜底的补全器；标题兜底必须绑定 DBLP 已确定的标题/年份/会议，不能单独拿 OpenAlex 排序结果直接上屏。

## 实际请求与返回摘要

> User-Agent（显式验证用）：`ResearchAgent-Spec015-Task02/1.0 (tester)`
> 现有代码 User-Agent：未显式设置，继承 `httpx` 默认行为。

| 命令摘要 | 退出码 | HTTP | 耗时 | 结果 |
|---|---:|---:|---:|---|
| `curl ... dblp/search/publ ... stream:conf/ccs year:2024` | 0 | 200 | 约 6.93s | 成功，JSON 命中 419，总前 5 条含主会、Workshop、poster-like |
| `curl ... dblp/search/publ ... stream:conf/ccs year:2023` | 0 | 200 | 约 9.56s | 成功，JSON 命中 293，含主会与 CCSW workshop |
| `curl ... dblp/search/publ ... stream:conf/uss year:2024` | 0 | 200 | 约 7.50s | 成功，但前 5 条全是 `SOUPS @ USENIX Security Symposium` |
| `curl ... dblp/search/publ ... stream:conf/uss year:2023` | 0 | 500 | 约 7.70s | DBLP internal error |
| `curl ... dblp/search/venue ... NDSS` | 0 | 429 | 约 1.32s | 限流 |
| `curl ... dblp.uni-trier.de/search/publ ... stream:conf/sp year:2024` | 0 | 200 | 约 5.14s | 成功，混有 `SPW...` 与主会 DOI |
| `curl ... dblp.uni-trier.de/search/publ ... stream:conf/ndss year:2024` | 0 | 200 | 约 5.23s | 成功，当前样本较干净 |
| `curl ... dblp.uni-trier.de/search/publ ... stream:conf/sp year:2023` | 28 | 000 | 20.00s | 超时无响应 |
| `curl ... dblp.uni-trier.de/search/publ ... stream:conf/ndss year:2023` | 28 | 000 | 20.00s | 超时无响应 |
| `curl ... dblp.uni-trier.de/search/venue ... usenix security` | 0 | 503 | 约 1.50s | mirror 不可用 |
| `curl ... api.openalex.org/works?filter=doi:10.1145...` | 0 | 200 | 约 1.36s | 成功，返回 1 条完整补全样本 |
| `curl ... api.openalex.org/works?search=A Practical...` | 0 | 200 | 约 1.42s | 成功，但首条非目标论文 |
| `curl ... api.openalex.org/works?filter=doi:10.9999...` | 0 | 200 | 约 1.21s | 成功，0 结果 |

## 风险与阻塞

1. **DBLP Venue Search 未完成正向验证**：本轮没有成功的 `venue/api` 响应，不能证明自定义会议配置流可稳定落地。
2. **USENIX 主会过滤规则仍未冻结**：`conf/uss` live 返回已混入 `SOUPS`，如果直接编码只认 stream，会把非主会论文带进默认结果。
3. **DBLP 实时稳定性不足**：同一轮内同时出现 `200/429/500/503/timeout`，说明客户端必须内建重试、退避、缓存与稳定 warning code。
4. **当前代码缺显式 User-Agent**：对 DBLP/OpenAlex 都不理想，也不利于后续排查被动限流。

## 建议的 Go/No-Go 裁决

- `OpenAlex`：可以放行到 Task 03，前提是按 spec 只做补全层，不承担主召回与最终排序。
- `DBLP publication search`：可以带着“必须过滤 + 必须退避/缓存”的前提进入实现。
- `DBLP venue search`：本轮保持 **No-Go / unverified**。
- `Task 02` 总体：保持 **No-Go**，直到补到至少 1 个成功的 `venue/api` 样本，并冻结 USENIX/CCS/SP 的主会过滤契约。

## 过程日志

- `.codebuddy/agent-logs/tester-spec015-task02-sources-v2-20260904.md`
