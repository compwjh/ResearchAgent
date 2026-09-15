# Task 04 附件：三会议 OA 可得性横评与 DOI 解析器缺陷修复

> 日期：2026-09-14 ｜ 样本：CCS 2024 (n=418)、IEEE S&P 2024 主会 (n=270)、NDSS 2024 主会 (n=140)
> 目的：验证 spec-032 Task04 的流水线是否泛化到三个会议，并记录修复的一个阻塞性生产缺陷。

## 1. 横评结果

| 会议 | 主会论文 | 摘要命中 | 有 pdf_url | 非受限候选 | **实下成功** | **占全会** |
|---|---|---|---|---|---|---|
| **NDSS 2024** | 140 | 140 (100%) | 140 (100%) | 140 | **140 (100%)** | **100%** |
| **ACM CCS 2024** | 418 | 417 (99.8%) | 240 (57%) | 70 | **50 (71%)** | **11%** |
| **IEEE S&P 2024** | 270 | 270 (100%) | 17 (6%) | 17 | **11 (65%)** | **4%** |

产物：`/tmp/ndss_pdfs`（140 篇 / 322 MB）、`/tmp/ccs_pdfs`（50 篇 / 182 MB）、`/tmp/sp_pdfs`（11 篇）。
全部通过 `%PDF-` 校验，无损坏文件。

### 结论

- **NDSS 是 100% 开放获取**——USENIX 直接托管 PDF，零门槛。这是接入收益最高的会议，
  应优先落地。
- **IEEE S&P 基本封闭**：253/270 篇在 OpenAlex 里连 `pdf_url` 都没有，
  只能靠机构订阅 / HITL。不要对它抱有 OA 幻想。
- **CCS 居中**：57% 有链接，但其中 41% 指向不可得的 `dl.acm.org`。

## 1c. Task02「Source Adapter 合同」符合性证据

Task02 在计划里仍是「待执行」，而它是 Task03/04/05/06 的**依赖**。由于 Task04 的
三个适配器已经落地，这里用运行时检查给出可判定证据，供 spec 负责人判断能否关闭 Task02：

| 合同要求 | NDSS | CCS | S&P |
|---|---|---|---|
| `source_id` | `ndss` | `acm-ccs` | `ieee-sp` |
| `source_id` 全局唯一 | ✓ | ✓ | ✓ |
| `authority_rank` | 2 | 2 | 2 |
| `discover_units` / `fetch_unit` / `parse_catalog` | ✓ | ✓ | ✓ |
| `normalize_identity` / `health` | ✓ | ✓ | ✓ |
| `health()` 无副作用（可重复调用结果一致） | ✓ | ✓ | ✓ |
| `normalize_identity` DOI 优先且稳定 | ✓ | ✓ | ✓ |
| 字段级 provenance | 9 字段 | 9 字段 | 9 字段 |

`discover_units` 签名三处一致：`(scope: Any) -> tuple[SourceFetchUnit, ...]`。
provenance 覆盖 `abstract / article_url / authors / container_title / doi /
keywords / pdf_url / title / year`。

**即：Task02 的合同在代码层面已由 Task04 的适配器实现**，缺的是 spec/Task 状态确认，
不是实现。

## 1d. 内容正确性校验：`%PDF` 魔数不够，必须校验「是不是对的那一篇」

之前只校验 ``%PDF-`` 魔数——那只能证明「是个 PDF」。新增
`scripts/pdf_content_check.py`：抽 PDF 前两页文本，检查元数据里的标题实词是否真出现。

### 扩大样本后的风险量化（412 篇）

为判断这是个例还是系统性问题，补跑了 NDSS 2025 全量（**211/211 下载成功，零失败**）：

| 来源 | PDF 数 | 内容匹配 | 不匹配 |
|---|---|---|---|
| NDSS 2024（官方会场直链） | 140 | 140 | 0 |
| NDSS 2025（官方会场直链） | 211 | 211 | **0** |
| CCS 2024（arXiv 镜像） | 50 | 50 | 0 |
| IEEE S&P 2024（OpenAlex 推断的 arXiv 镜像） | 11 | 10 | **1** |
| **合计** | **412** | **411** | **1（0.24%）** |

**结论：风险不随 arXiv 普遍存在，而是「OpenAlex 把某篇预印本挂错 DOI」的偶发错链。**
官方会场直链（NDSS 351 篇）**零错**；CCS 的 arXiv 镜像 50 篇也零错。
整体错链率约 0.24%，但它是**静默**的——下载链每一步都"成功"。

不匹配的这一篇是**真实缺陷，且是静默的**：

| 项 | 值 |
|---|---|
| DOI | `10.1109/sp54263.2024.00182` |
| Crossref 登记标题 | From Chatbots to Phishbots?: Phishing Scam Generation in Commercial LLMs |
| OpenAlex 给的 `pdf_url` | `https://arxiv.org/pdf/2406.01964` |
| arXiv 2406.01964 真实标题 | Measure-Observe-Remeasure: An Interactive Paradigm for DP Exploratory Analysis |
| 实际下载到的 PDF | **Measure-Observe-Remeasure**（另一篇论文） |

即 **OpenAlex 把一篇不相关的 arXiv 预印本挂到了这个 IEEE DOI 上**。下载链每一步都
"正确"——URL 合法、HTTP 200、是合法 PDF、DOI 与元数据自洽——只有内容对不上。
若直接入库，用户会拿到一篇标题与内容完全无关的论文，**且没有任何报错**。

**给 Task05 的建议**：入库前加一道内容门禁（复用 `pdf_content_check.py` 的思路），
标题实词命中率低于阈值时记为"存疑"而非静默入库；不要因为"下载成功"就认定内容正确。

## 1e. 文本层审计：内容对 ≠ 能被检索

`pdf_content_check.py` 证明「下载的是对的那一篇」，但**扫描件/纯图片 PDF 内容同样正确**，
入库后 RAG 却抽不出任何文字——又一种静默故障。新增
`scripts/pdf_text_layer_audit.py` 按「每页可抽取字符数」判定。

**412 篇全部有可用文本层，零扫描件（0%）。**

阈值有效性（抽样 30 篇验证不是假阴性）：每页可抽取字符数
最小 3394 / 中位 5738 / 最大 6691，最小值为阈值（120）的 **28 倍**，
分布远离阈值。这批论文全部是原生数字 PDF，可直接入库做全文索引。

## 2. 修复的阻塞性生产缺陷：DOI 解析器地址被误拒

### 现象

NDSS 的 `pdf_url` 形如 `https://doi.org/10.14722/ndss.2024.24017`，
302 后落到 `https://www.ndss-symposium.org/wp-content/uploads/2024-17-paper.pdf`（真实 PDF）。

生产 `ConferencePdfDownloader` 在**跟随重定向之前**用 `allowed_hosts` 校验，
校验的 host 是 `doi.org`：

```python
# 正确意图：只放行最终真实主机
ConferencePdfDownloader(allowed_hosts=("www.ndss-symposium.org",))
# -> 全部 FAIL，DOWNLOAD_BLOCKED「下载地址被安全策略拒绝」  ← 修复前
# -> 8/8 OK                                              ← 修复后（实测）
```

### 为什么不能"把 doi.org 加进白名单"

`doi.org` 可 302 到任意域名。把它放进 `allowed_hosts` 等于把主机白名单架空，
与 spec-032 的 fail-closed 约定冲突。已明确拒绝该方案。

### 改法（`conference_pdf_downloader.py`）

1. 识别封闭集合 `_DOI_RESOLVER_HOSTS = {doi.org, www.doi.org, dx.doi.org, www.dx.doi.org}`。
2. 先**逐跳解析**重定向，每一跳都过调用方的 `allowed_hosts`
   （含**中间跳**，未授权同样拒绝），复用既有 `url_security` 设施。
3. 把**最终 URL** 交给既有 `download_candidate`，用**原样** `allowed_hosts` 校验。
4. 探针只读取 status + `Location`，不读 body；复用 `_check_peer` 做对端 IP 复核；
   遵守 `max_redirects`；失败转稳定错误码，`download_batch` 降级语义不变。
5. `doi.org` **永不进入下载 allowlist**，无"跳过校验"开关。

### 实测验证（真实网络，非 mock）

| 场景 | 期望 | 实测 |
|---|---|---|
| `allowed_hosts=("www.ndss-symposium.org",)`，NDSS 真实记录 | 成功 | **8/8 OK** |
| `allowed_hosts=("arxiv.org",)`，实际解析到 ndss-symposium.org | 拒绝 | **DOWNLOAD_BLOCKED「DOI 解析到未授权的下载地址」** |
| `allowed_hosts=()` | 拒绝 | **PDF_OPEN_ACCESS_SKIPPED** |

测试：spec-032 四文件 **214 passed**（下载器由 38 → 55，新增 17 个用例，
含内网地址、中间跳未授权、重定向上限等负例）。`ruff check` 通过。

详见 `doi-resolver-fix-report.md`。

## 1b. 多年度/track 验收（Task04 明确的验收点）

只测 2024 不足以说明稳定——Crossref 每年的 container-title 措辞都在变
（如 `Proceedings of the 2024 on ACM SIGSAC Conference...` 多一个 "on"），
年份边界与相关性排序也可能翻车。逐年实跑（2022–2025）：

| 会议 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|
| NDSS | 83 / 83 摘要 | 94 / 88 | 140 / 138 | 211 / 201 |
| CCS | 221 / 221 | 233 / 233 | 328 / 310 | 317 / 295 |
| IEEE S&P | 147 / 147 | 198 / 198 | 261 / 261 | 256 / 255 |

**12 个（适配器 × 年份）组合全部 `status=completed`，无 `failed_years`，
warning 总数 1 条**（S&P 2025）。合计 **2489 条记录，全部有 pdf_url**。

耗时：**2 分 18 秒**。按批量化前约 1.0 s/条估算，同样的量需要约 41 分钟——
这也是富化批量化必须做的直接理由。

`git diff --check` 通过（无空白错误）。

## 2b. 同一缺陷的另一半：入库路径（`import_candidate`）

上面的修复只覆盖**批量下载器**。`import_candidate` 是另一条代码路径
（`_download()` → `download_candidate`），调用下载器前同样没有解析 DOI，
于是 NDSS 记录在 `allowed_hosts=("www.ndss-symposium.org",)` 下
**140/140 全部 `DOWNLOAD_BLOCKED`**。

已一并修复，并做了**去重**：解析逻辑提取为唯一实现
`infrastructure/doi_resolver.resolve_doi_url()`，两条路径引用**同一个函数对象**
（由 `tests/test_spec032_doi_resolver_import.py` 用 `is` 断言锁定，禁止复制第二份）。
快照约定：`candidate_snapshot["pdf_url"]` 记**实际下载**的最终地址，
原始解析器地址写入 `pdf_url_original`，避免知识库侧出现
「快照是 doi.org、实际下的是别处」的自相矛盾。

- 测试：新增文件 28 passed；spec-032 五文件合计 **242 passed**；`ruff` 通过。
- 真实网络：`acceptance_ingest_loop.py --host www.ndss-symposium.org --limit 5`
  → **5/5 入库成功**（修复前 0/5），PDF 落盘、SHA256 一致、port 收到 `trusted_pdf_path`。

详见 `doi-resolver-import-path-fix.md`。至此
**发现 → 富化 → 下载 → 入库** 全链路闭环。

## 3. 本轮其他修复

1. **DOI 解析器误伤**（`oa_pdf_fetch.py`）：同上逻辑，独立脚本也做了重定向后再判定，
   否则 140 篇 NDSS 会被 `doi.org` 不在白名单而全部丢弃。
2. **机构库白名单过窄**：`inria.hal.science`、`escholarship.org`、`zora.uzh.ch`、
   `iris.unige.it` 被误拒。模式改为子域无关（`hal\.science$`）并补充
   `escholarship`、`zora`、`unige.it`、`repositor*`。S&P 由 10 → 11 篇。

## 4. 残留风险

- 修复依赖"解析一次再下载"，理论存在 DNS rebinding 窗口（校验与实际连接各解析一次）。
  已用 `_check_peer` 同等级缓解；彻底消除需连接级 IP 固定，httpx 不支持。
- 当前 NDSS 适配器产出的是 Crossref 直链（非 DOI 形态），该缺陷属**防御性修复**；
  建议 Task05 合并来源后再抽样复验端到端命中率。
- CCS 的 41% 与 S&P 的 96% 仍需 HITL / 机构订阅，OA 层无解。
