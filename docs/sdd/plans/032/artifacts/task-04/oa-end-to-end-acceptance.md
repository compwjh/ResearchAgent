# Task 04 附件：OA 层端到端验收（发现 → 富化 → 生产下载）

> 日期：2026-09-14 ｜ 样本：ACM CCS 2024，n=418
> 目的：在不动 Cloudflare 的前提下，验证 spec-032 的真实链路可用性，为 Task05/06 提供可复现基线。

## 1. 结论

| 指标 | 结果 |
|---|---|
| Crossref 枚举（ACM member 320 + container-title 过滤） | 418 条 |
| OpenAlex 摘要命中 | **417 / 418 = 99.8%** |
| 有 `pdf_url` | 240 / 418 = 57% |
| 其中指向 `dl.acm.org`（403，不可得） | 170 / 418 = 41% |
| 非受限域名候选 | 70 / 418 = 17% |
| **独立脚本实下** | **50 篇 / 182 MB，100% 通过 `%PDF-`** |
| **生产 `ConferencePdfDownloader` 实下** | **arXiv 44/44 = 100%，36 s** |
| spec-032 定向回归 | 38 passed |

## 2. 关键认知修正：OpenAlex 的 `open_access` 对 ACM 不可信

OpenAlex 把 `dl.acm.org` 链接也标为 open access（无付费墙），但 Cloudflare 仍 403。
**反爬与权限是两道独立的门，过了一道没有意义。**

因此 `oa_enrich.py` 改为扫描 `locations[]` 挑选非受限域名（`best_oa_location`
偏袒出版商，即使存在 arXiv 镜像也返回 `dl.acm.org`），此项多救回 26 篇。
受限行标记 `pdf_access="blocked"` + `pdf_gated=true`。

## 3. 生产代码路径验收（`acceptance_prod_path.py`）

```bash
python3 scripts/acceptance_prod_path.py 50
```

- **44/44 OK**，字节数与独立脚本逐字节一致（532,181 / 967,782 / 1,664,119 …）。
- 降级行为正确，未注入 `browser_manager` 时：
  - `dl.acm.org` → `access=browser_required` → `PDF_BROWSER_UNAVAILABLE`
  - 无 `pdf_url` → `access=unavailable` → `PDF_UNAVAILABLE`
  - 均不抛异常，批量循环继续。
- 生产下载器**无需**额外礼貌延迟即 44/44（其 SSRF/DNS/校验本身已拉开间隔），
  不应为了"提速"而移除这些安全检查。

## 4. 按域名成败（独立脚本，候选 70）

| 域名 | 候选 | 已下 |
|---|---|---|
| arxiv.org | 44 | **44 (100%)** |
| vtechworks.lib.vt.edu | 3 | 3 |
| eprints.gla.ac.uk / discovery.ucl.ac.uk / ir.cwi.nl | 各 1 | 各 1 |
| hal.science | 7 | **0** |
| dspace.mit.edu | 7 | **0** |
| digitalcommons / ubn.ru.nl / lirias / worktribe | 6 | **0** |

**arXiv 是 100% 可靠源；全部失败来自机构知识库。**
HAL（HTML 落地页）、MIT DSpace（405）、Worktribe（403）换浏览器 UA 与
`Accept: application/pdf` 均无效，判定为不可脚本化，不再投入。

## 5. 本轮修复的三个缺陷

1. **`httpx.get(url带query, params={})` 静默丢弃整个 query string**。
   传 `params=`（即使空 dict）会重建 query 并丢弃 URL 中已有参数。
   症状：OpenAlex 返回 200 + 25 条随机论文，DOI 命中 0 且无任何报错。
   修法：query 一律用 `params=` dict 构造。
2. **`ccs_fetch.py` 带富化 = 每条 DOI 一次 HTTP**，13 分钟写出 0 字节。
   改为 `--no-enrich` + `oa_enrich.py` 批量（50/次），约快 50 倍。
3. **按主机熔断把 4xx 计入失败**（本轮自己引入）。arXiv 因 0.3 s 间隔被限速返回
   403 → 熔断触发 → 剩余 24 篇被跳过（首轮仅 25 篇）。
   修法：熔断只统计传输错误与 5xx；403/429 视为"慢一点"并做指数退避；
   arXiv 默认 3 s 礼貌间隔。修复后 25 → 50 篇。

## 6. 产出物

- `/tmp/ccs_2024_raw.jsonl`（418 条原始）、`/tmp/ccs_2024_enriched.jsonl`（富化后）
- `/tmp/ccs_pdfs/`（50 篇真实 PDF，182 MB）
- 脚本：`ccs_fetch.py`（`--no-enrich`）、`oa_enrich.py`、`oa_pdf_fetch.py`、`acceptance_prod_path.py`
- Skill 文档已同步实测数据与 5 条新增 dead-end。

## 7. 仍未闭环

- **付费层（41%）**：需 HITL。`acm_login_cdp.py` 已就绪，等待人工点击 Cloudflare
  验证 + 机构登录；`cf_clearance` 有有效期，需可重复执行。
- 生产 `ConferencePdfDownloader` 的浏览器层仍用 Playwright 启动的上下文，
  无法自清 Cloudflare——CDP-attach + 同源 `fetch()` 的洞察尚未移植进生产代码。
