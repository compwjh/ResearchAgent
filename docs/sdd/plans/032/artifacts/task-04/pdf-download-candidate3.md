# spec-032 候选 3：无人值守 PDF 下载（常驻登录态 + 持久化浏览器上下文）

- 交付物：`backend/app/paper_discovery/infrastructure/conference_pdf_downloader.py`（新增，464 行）
- 测试：`tests/test_spec032_conference_pdf_download.py`（新增，551 行，36 个用例）
- 适配器改动：`ccs_publication_source.py`（+21 行）、`ieee_sp_publication_source.py`（+20 行）、
  `ndss_publication_source.py`（+6 行，仅 docstring）
- 复用的既有实现（**没有第二套**）：`paper_download.download_candidate`（HTTP/SSRF 全链）、
  `paper_browser_manager.PaperBrowserManager` / `BrowserSession.authenticated_pdf_request`
  （持久化上下文）、`SITE_ORIGINS` / `SUPPORTED_SITES` / `_origin`（站点白名单与 origin 规范化）、
  `paper_discovery_normalization.normalize_doi` / `normalize_title`（身份键）、
  `paper_download._candidate_value`（记录字段读取）、`url_security.validate_*`（URL 校验）。

---

## 1. 分层策略

```
record
  │
  ├─ 第 1 层 open_access  →  paper_download.download_candidate（纯 HTTP，无浏览器）
  │                         需要调用方提供 allowed_hosts（空则 fail-closed 跳过并给出可行动原因）
  │
  └─ 第 2 层 browser       →  PaperBrowserManager.open_session(site)（**不传 url，不导航**）
                             → BrowserSession.authenticated_pdf_request(url)
                             → finally 无条件 session.close()（释放站点锁与 profile 锁）
```

- 层顺序固定：**先公开直下，失败才动浏览器**。浏览器层是稀缺资源（单 profile 文件锁 +
  站点互斥锁），能不用就不用。
- 每层的结果写进 `outcome.attempts: ((层, 错误码), ...)`，成功层错误码为空串；
  最终 `error_code` 取**最后一次尝试**的错误码；无任何可用层时取 `PDF_UNAVAILABLE`。
- `ConferencePdfBatchResult` 提供 `layer_counts`（各层命中数）、`access_counts`（各层级记录数）、
  `error_counts`（失败码分布）、`login_required_count`，供上层做命中率统计与进度展示。
- 单条失败绝不中断整批（`download_batch` 逐条 `try/except`），与批任务既有「失败降级」一致。

## 2. 各层如何判定（`classify_pdf_access`）

取值固定为 `open_access` / `browser_required` / `unavailable` / `unknown`：

| 条件 | 层级 |
|---|---|
| `pdf_url` 存在 且 `pdf_access ∈ {public, open_access}` | `open_access` |
| `pdf_url` 存在 且 其 origin 命中 `SITE_ORIGINS`（`dl.acm.org` / `ieeexplore.ieee.org`） | `browser_required` |
| `pdf_url` 存在 且 记录显式声明了 `pdf_site`（acm/ieee） | `browser_required` |
| `pdf_url` 存在 但既非公开、也不在白名单（如 `arxiv.org`、`www.ndss-symposium.org`） | `unavailable` |
| 无 `pdf_url` 但有 DOI | `unavailable` |
| 既无 `pdf_url` 也无 DOI | `unknown` |

- **URL 主机是站点的唯一权威来源**（`site_for_url()` 复用 `SITE_ORIGINS`，不新建白名单）。
- `open_access` 但主机恰在浏览器白名单时（**CCS 就是这种情形**：OpenAlex 给的 "OA" 地址本身是
  `https://dl.acm.org/doi/pdf/...`），两层都会排进计划：公开层 403 → 自动落到浏览器层。这正是分层
  设计的价值所在。
- 出版方候选直链由**适配器记录**（`build_publisher_pdf_url`）：
  - ACM：`https://dl.acm.org/doi/pdf/{normalize_doi(doi)}`（只需 DOI）
  - IEEE：`https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={n}`（`n` 来自 Crossref
    `resource.primary.URL` 的 `/document/{n}`；**只有 DOI 构造不出来**，Xplore 无 DOI 形式的 PDF 地址）
- 发现阶段**不发起任何 PDF 请求**：适配器只写 `pdf_url`，测试断言 `dl.acm.org` 从未出现在抓取请求里。

## 3. NDSS 为什么不能走浏览器层（与任务描述的差异）

任务描述认为 NDSS「不在 `SUPPORTED_SITES` 内 → 标 `unavailable`」。**实际代码不是这样**：

- `ndss_paper_parser._record()` 已经从 Crossref `resource.primary.URL` 记录了
  `https://www.ndss-symposium.org/wp-content/uploads/*.pdf`，并写 `pdf_access="public"`；
  `tests/test_spec032_ndss_source.py:190/207` 已冻结该行为。
- 若强行改标 `unavailable`，会**回退一个本来可用的公开路径**，并挂掉既有断言。

因此实际落地方案是：NDSS **永不**是 `browser_required`（`www.ndss-symposium.org` 不在
`SITE_ORIGINS`，也绝不把它伪造成 acm/ieee 站点），有官方公开 PDF 时判 `open_access`、
否则判 `unavailable`。已在 `ndss_publication_source.py` docstring 里写明该决定。

> 前置条件：公开层要真的能下 NDSS，调用方需把 `www.ndss-symposium.org` 加进
> `allowed_hosts`（默认 `_paper_candidate_hosts` 只有 usenix.org + 服务端配置）。
> 这是**配置**问题，不是分类问题；未配置时公开层 fail-closed，错误码 `DOWNLOAD_BLOCKED`
> （`下载站点不在 allowlist`），不会静默放行。建议 Task05 一并处理。

## 4. 与任务描述的第二处差异：`pdf_access` 词表（重要）

任务要求把 `pdf_access` 固定为 `open_access/browser_required/unavailable/unknown`。**实际代码里这个字段已被冻结**：

- `paper_discovery_store.py:457`、`openalex_enricher.py:121`、`paper_discovery_search.py:359`
  都把取值限定在 `{unknown, public, login_required, unavailable}`，**越界值会被静默降级为 `unknown`**；
- 三个既有 spec-032 测试文件共 6 处断言旧词表（`unknown` / `public`），任务又要求这些文件保持通过。

若按字面改词表：`browser_required` 在写库那一刻就变成 `unknown`，**候选 3 需要的信息恰好被抹掉**，
功能静默失效。因此采用**双轴**：

| 轴 | 字段 | 词表 | 用途 |
|---|---|---|---|
| 可访问性（已冻结，不改） | 记录/store 的 `pdf_access` | `unknown/public/login_required/unavailable` | 既有 UI/搜索/存储 |
| **下载路由（本次新增）** | `classify_pdf_access()` 的返回值 + `outcome.pdf_access` | `open_access/browser_required/unavailable/unknown` | 分层下载决策与命中率统计 |

路由层级是**派生量**（由 `pdf_url` + 白名单确定性算出，单一实现），不写进 store，因此既拿到任务
要求的 4 个取值语义，又不破坏 store 合同与 6 处既有断言。

**Task05 合并时需注意**：适配器记录构造直链时写 `provenance["pdf_url"] = <适配器 source_id>`
（`acm-ccs` / `ieee-sp`）。该 id 不在 `SOURCE_AUTHORITY` 里 → 按「未知来源 = 最高权威」处理，
会挡住后续 OpenAlex 的 OA 地址覆盖。建议 Task05 合并时**优先选 `pdf_access == "public"` 的 OA 地址**，
而不是单纯按 provenance 权威排序（否则 IEEE 会丢掉 arXiv 公开副本这条更省事的路径）。

## 5. 一次性登录如何衔接（无人值守的关键）

1. 人工阶段（一次性）：`PaperBrowserManager(settings=...)` → `open_session("acm")` →
   `goto("https://dl.acm.org")` → 用户在真实窗口里完成机构登录/挑战 →
   cookie 落进 `data/browser-profile/security-papers`（`launch_persistent_context` 的 profile 目录，
   权限 0700，进程文件锁 `.profile.lock`）。
2. 无人值守阶段：`ConferencePdfDownloader` **只调 `open_session(site)`（不传 url、不 goto）**，
   直接 `authenticated_pdf_request(url)` 复用 profile 里的 cookie。
3. 上下文未认证时：既有实现抛 `PaperDownloadError(LOGIN_REQUIRED)` 或
   `BrowserManagerError(BROWSER_SESSION_REQUIRED/EXPIRED)`；下载器统一给出
   `login_required=True` + 稳定错误码 + 中文提示「请先手动登录一次（保持 profile）后重试」。
   **代码里没有任何登录动作**（不填表单、不点按钮、不解析挑战页）。
4. 会话生命周期：`open_session` 有 TTL（默认 300s）与站点互斥锁；下载器在 `finally` 里无条件
   `session.close()`，避免锁泄漏把后续批次挡在 `BROWSER_PROFILE_LOCKED` 上（已有测试覆盖）。

## 6. 已知限制

1. **IEEE Xplore 直链形态未实测**：`stampPDF/getPDF.jsp?tp=&arnumber=N` 是按 Xplore 的
   "PDF 下载" 端点构造的（`stamp/stamp.jsp` 返回的是包裹 PDF 的 HTML frameset，会被
   `INVALID_PDF` 拒掉）。spec-032 禁止在发现阶段探测，本机也**没有真实 chromium**，
   因此该形态未经验证；若浏览器层报 `INVALID_PDF`，改 `build_publisher_pdf_url()` 里的模板即可
   （单点修改）。
2. **`pdf_site` 不是记录字段**：三个 `*CatalogRecord` 定义在 parser 模块里（不在本次允许改的文件内），
   加字段要改 3 个 parser。因此站点改由 `site_for_url(pdf_url)` 从 URL 反查（复用 `SITE_ORIGINS`），
   并同时支持调用方显式传 `pdf_site`（为 Task05 的合并记录预留）。
3. **没有真实浏览器端到端验证**：本机 chromium 后台安装未完成；全部测试用 fake
   `playwright_factory` / fake session，验证的是**编排与错误码**，不是「Cloudflare 真的放行」。
   上线前必须做一次真机冒烟（人工登录 → 批量下 3–5 篇 ACM 论文）。
4. **并发**：单 profile 只有一个进程锁 + 每站点一把锁，因此浏览器层实际是**串行**的。
   批量下载应视为「慢而稳」；如需并行，只能多 profile 目录（本任务未做）。
5. **覆盖率工具缺失**：本 venv 未安装 `pytest-cov`，无法出覆盖率数字（TDD 技能要求的 80% 门槛
   本次以 36 个定向用例 + 分层/失败/边界分支覆盖替代）。
6. **不做**：不伪造 UA/header、不解析/绕过 Cloudflare 挑战、不碰付费墙、不自动登录、不在发现阶段探测 PDF。

## 7. ToS / 合规风险（必须让用户知情）

- ACM DL / IEEE Xplore 的**授权访问**通常允许个人研究用途下载；但**自动化批量下载**可能违反其
  Terms of Use（尤其 "systematic downloading" / "scraping" 条款），即使已登录且机构有订阅。
- 本实现刻意保持：**串行、低频、只下载用户明确选中的候选**（无自动全量抓取），并且**不绕过任何
  技术保护措施**——Cloudflare 挑战通过用户自己的浏览器会话（真实登录态）通过，等同于人工点击。
- 建议：默认对批量规模设上限（如每批 ≤ N 篇）、保留可审计的逐条结果、并在 UI/文档提示
  「请遵守出版方条款，仅下载你有权访问的论文」。风险由使用者承担，工具不提供绕过手段。

## 8. 验证命令与真实输出

```bash
# 1) 定向 spec-032（4 个文件）
cd /Users/wjh/work/ResearchAgent-2/ResearchAgent && env -u PYTHONPATH .venv/bin/python -m pytest \
  tests/test_spec032_conference_pdf_download.py tests/test_spec032_ccs_source.py \
  tests/test_spec032_ieee_sp_source.py tests/test_spec032_ndss_source.py -q --basetemp=/tmp/pt_pdf_$RANDOM
# → 195 passed in 1.75s（新增 36 + 既有 159，无回归）

# 2) 相邻回归（浏览器/下载/导入/批任务/富化）
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_paper_browser_manager.py tests/test_paper_browser.py \
  tests/test_paper_download.py tests/test_paper_import.py tests/test_paper_import_batch_service.py \
  tests/test_paper_import_batch_integration.py tests/test_paper_import_identity.py \
  tests/test_paper_discovery_search.py tests/test_openalex_enricher.py tests/test_usenix_publication_source.py \
  tests/test_usenix_paper_parser.py tests/test_ieee_paper_parser.py tests/test_acm_paper_parser.py -q
# → 252 passed in 81.09s

# 3) lint + 导入冒烟
cd backend && ../.venv/bin/python -m ruff check app/paper_discovery/infrastructure/conference_pdf_downloader.py \
  app/paper_discovery/infrastructure/ccs_publication_source.py \
  app/paper_discovery/infrastructure/ieee_sp_publication_source.py \
  app/paper_discovery/infrastructure/ndss_publication_source.py
# → All checks passed!
cd backend && ../.venv/bin/python -c "import app"     # → import app OK
```

## 9. 未装配到 API 层（有意为之）

`ConferencePdfDownloader` 目前**没有**接进 `common.py` / 路由 / 批任务（那些文件在本次硬约束的
禁改清单里）。它已经按既有装配风格写好（可注入 `settings` / `allowed_hosts` / `browser_manager`），
Task05 只需在组合根里 `ConferencePdfDownloader(settings=article_settings,
allowed_hosts=_paper_candidate_hosts(candidate), browser_manager=_paper_browser_manager())` 即可，
无需改动本模块。
