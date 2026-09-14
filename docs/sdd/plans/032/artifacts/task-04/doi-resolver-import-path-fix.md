# Task 04 附件：DOI 解析器地址在**入库路径**的复用修复

> 日期：2026-09-15 ｜ 上一轮修复：`doi-resolver-fix-report.md`（只覆盖批量下载器）
> 影响面：`backend/app/paper_discovery/application/paper_import.py`、
> `backend/app/paper_discovery/infrastructure/conference_pdf_downloader.py`、
> 新增 `backend/app/paper_discovery/infrastructure/doi_resolver.py`
> 触发：NDSS 记录 `pdf_url=https://doi.org/10.14722/ndss.2024.24017`，
> `allowed_hosts=("www.ndss-symposium.org",)` 时 `import_candidate` 100% `DOWNLOAD_BLOCKED`（140/140）。

## 1. 结论

| 项 | 结果 |
|---|---|
| 根因 | 上一轮只修了批量下载器；`import_candidate` 在调用下载器**之前**没有做 DOI 解析，`download_candidate` 拿到的仍是 `doi.org` |
| 改法 | 解析逻辑提取为**唯一实现** `infrastructure/doi_resolver.resolve_doi_url()`，批量下载器与入库路径共用同一函数对象；入库路径在 `_download()` 之前解析 |
| `allowed_hosts` 语义 | **不变**（`doi.org` 绝不进入下载白名单，也不新增任何"跳过校验"开关） |
| 新增公开 API | 新增模块 `doi_resolver`（2 个公开函数 + 2 个常量）；`import_candidate` 签名不变 |
| 快照决策 | `candidate_snapshot["pdf_url"]` 记**实际下载**的最终地址，原始解析器地址写入 `pdf_url_original`（见 §5） |
| 幂等 / 补偿 / 临时目录清理 | **不变**（解析在既有 `try` 内，失败仍走同一 `finally`） |
| 定向验收 | 4 个 spec-032 文件：**214 passed**（基线 214，未变少）；新增文件：**28 passed** |
| 相关回归 | 16 个 paper_import / download / browser / kb 相关文件：**231 passed, 12 subtests passed** |
| 真实网络验收 | `acceptance_ingest_loop.py --host www.ndss-symposium.org --limit 5` → **5/5 入库成功**（修复前 0/5） |
| 静态检查 | `ruff check backend/app/paper_discovery` → All checks passed |

## 2. 改了什么

| 文件 | 变化 | 说明 |
|---|---|---|
| `backend/app/paper_discovery/infrastructure/doi_resolver.py` | **新增 180 行** | 解析能力的唯一实现（原 `ConferencePdfDownloader` 私有方法整体搬入） |
| `backend/app/paper_discovery/infrastructure/conference_pdf_downloader.py` | 591 → 513 行（净 −78） | 删掉 `_resolve_open_access_url` / `_probe_client` / `_probe` 与模块级 `_doi_resolver_host` / `_REDIRECT_STATUSES`，改为调用 `resolve_doi_url()`；清理 12 个失效导入；保留一行兼容别名 `_DOI_RESOLVER_HOSTS = DOI_RESOLVER_HOSTS` |
| `backend/app/paper_discovery/application/paper_import.py` | **+47 / −1** | 新增 `_candidate_with_pdf_url()`；`import_candidate` 物化 `allowed_hosts`，并在 `_download()` 之前解析 DOI 地址、同步快照 |
| `tests/test_spec032_doi_resolver_import.py` | **新增 619 行 / 28 用例** | 唯一实现 / 入库成功 / 安全负例 / 回归保护四组 |

**没有**改动：`frontend/**`、其他 spec 的代码、`paper_download.py`、`url_security.py`、`knowledge_base/**`。

## 3. 解析逻辑放在哪

新模块 `backend/app/paper_discovery/infrastructure/doi_resolver.py`：

```python
DOI_RESOLVER_HOSTS = frozenset({"doi.org", "www.doi.org", "dx.doi.org", "www.dx.doi.org"})  # 封闭集合
REDIRECT_STATUSES  = frozenset({301, 302, 303, 307, 308})                                   # 与 download_candidate 一致

def doi_resolver_host(url) -> str | None: ...            # 只认封闭集合里的主机，其余返回 None

def resolve_doi_url(
    url, *, allowed_hosts, settings=None, dns_resolver=None,
    transport=None, client=None, peer_ip_resolver=None,
    max_redirects=DEFAULT_MAX_REDIRECTS,
) -> str: ...                                            # 非解析器地址原样返回；失败抛 PaperDownloadError
```

内部流程与上一轮**逐字一致**（只是从方法变成函数）：

```
validate_url(url, allowed_hosts=DOI_RESOLVER_HOSTS)        # 入口那一跳：协议/端口/认证参数/DNS 公共地址
loop:
    _probe(probe_client, target)                            # 只读 status + Location，不读响应体
    非 30x 且 redirects == 0 -> PDF_NOT_FOUND（doi.org 不是下载目标，fail-closed）
    非 30x 且 redirects > 0  -> 返回 target.url（已过 allowlist 的最终地址）
    无 Location 或 redirects >= max_redirects -> DOWNLOAD_BLOCKED「重定向次数超过限制」
    validate_redirect_target(target, location, allowed_hosts=<调用方 allowlist>)   # 每一跳都校验
```

**为什么新建模块而不是塞进 `paper_download.py`**：职责单一（解析 ≠ 下载），且两个调用点
（`infrastructure/conference_pdf_downloader.py` 与 `application/paper_import.py`）都能 import 它
而不产生环（`doi_resolver` → `paper_download` → 无回边）。

**为什么不是把 DOI 解析塞进 `download_candidate`**：那会让**所有**下载路径都隐式多一跳网络探测，
且把"指路牌解析"与"下载校验"混在一个函数里；本任务明确要求"在 `import_candidate` 里，调用
`_download()` 之前解析"。

## 4. 两处调用如何保持一致

| 维度 | 批量下载器 | 入库路径 |
|---|---|---|
| 调用的函数 | `resolve_doi_url` | `resolve_doi_url`（**同一个函数对象**） |
| `allowed_hosts` | `self.allowed_hosts`（调用方构造参数） | `allowed_hosts`（`import_candidate` 参数，先 `tuple()` 物化） |
| `settings`（超时） | `self.settings` | `settings` |
| 网络出口 | `self.transport` / `self.client` | `transport` / `client` |
| DNS 注入 | `self.dns_resolver` | `dns_resolver` |
| 对端 IP 复核 | `self.peer_ip_resolver` | `peer_ip_resolver` |
| 重定向上限 | `self.max_redirects`（默认 `DEFAULT_MAX_REDIRECTS`） | 默认 `DEFAULT_MAX_REDIRECTS` |
| 空 allowlist | 直接 `PDF_OPEN_ACCESS_SKIPPED`，**不发请求** | 跳过解析，交给 `download_candidate` 产生 `DOWNLOAD_BLOCKED`，**不发请求** |
| 解析后 URL 的用途 | `self._download({"pdf_url": resolved}, ...)` | `_candidate_with_pdf_url(candidate, resolved)` 后交给 `_download(...)` |

一致性由测试护栏钉死（不是靠约定）：

- `test_the_downloader_and_the_import_path_share_one_resolver_implementation`：断言两个模块里的
  `resolve_doi_url` / `DOI_RESOLVER_HOSTS` **是 `doi_resolver` 里的同一个对象**（复制粘贴会立刻红）。
- `test_both_call_sites_hand_the_same_resolved_url_to_the_download_chain`：同一份数据 + 同一份
  allowlist，两条路径交给下载链的候选 `pdf_url` 完全相同，且 allowlist 未被污染。
- `test_both_call_sites_reject_the_same_unauthorized_doi`：失败路径也一致（同一个稳定错误码）。

## 5. `candidate_snapshot` 里存什么：决定与理由

**决定**：解析成功且最终地址与原始地址不同时，写入两个键——

```python
snapshot["pdf_url"] = <最终落地地址>            # 例如 https://www.ndss-symposium.org/.../2024-17-paper.pdf
snapshot["pdf_url_original"] = <原始解析器地址>  # 例如 https://doi.org/10.14722/ndss.2024.24017
```

**理由**：

1. **快照是"服务端候选快照"这一载荷，不是只读历史记录**。`import_candidate` 本来就往里写
   `_stored_name`（`paper_import.py` 既有行为），说明它允许被编排层加工。
2. **`pdf_url` 的语义是"PDF 从哪来"**。若保留 `doi.org` 而实际下载的是 `www.ndss-symposium.org`，
   知识库侧/排障者看到的就是一个"没被用过"的地址——正是任务要求避免的自相矛盾。
   改为最终地址后，快照与 `DownloadResult.url`（下载链返回的**最终** URL）语义对齐。
3. **不丢溯源**：原始解析器地址没有丢弃，而是放在**显式命名**的 `pdf_url_original` 里，
   "哪个 DOI 入口解析到哪个落地地址"这一事实仍然可查。
4. **不改判重与元数据**：`knowledge_base` 侧 `import_paper()` 只把 `article_url` 写成 `source_url`，
   **不读** `pdf_url`；`_same_identity()` 用 doi/dblp/title/year 判重，也**不读** `pdf_url`。
   全仓 grep 也确认没有任何测试断言快照的键集合。因此这次改写对下游是**零行为影响**。
5. **不改调用方对象**：解析结果写进快照的**副本**（`_candidate_snapshot` 对 Mapping 会 `dict(...)`
   拷贝），调用方传入的 `record` 不被就地修改（有断言）。

## 6. 安全约束对照（逐条，与上一轮一致，未削弱）

| 约束 | 实现 | 测试 |
|---|---|---|
| `doi.org` 一族是封闭集合，只校验**入口**那一跳 | `DOI_RESOLVER_HOSTS` 为 `frozenset`，不接受调用方输入；`validate_url(url, allowed_hosts=DOI_RESOLVER_HOSTS)` | `test_the_resolver_host_set_stays_closed` |
| **每一跳**（含中间跳）都过调用方 `allowed_hosts` | 循环内每次 `validate_redirect_target(..., allowed_hosts=<调用方>)` | `test_import_rejects_a_doi_that_resolves_to_an_unauthorized_host`、`test_import_rejects_an_unauthorized_intermediate_hop` |
| `doi.org` 绝不进入下载 allowlist | 解析只读 `Location`；`allowed_hosts` 原样透传；无任何 `+=` | `test_both_call_sites_hand_the_same_resolved_url_to_the_download_chain`（断言交集为空） |
| 禁止解析到内网/回环/链路本地 | 每一跳都走 `url_security._public_addresses` / `_unsafe_ip` | `test_import_rejects_a_doi_that_resolves_to_a_private_address`（`127.0.0.1`） |
| 限制重定向次数 | `max_redirects`（默认 `DEFAULT_MAX_REDIRECTS`=5） | `test_import_bounds_doi_redirect_chains` |
| 保留 `_check_peer` 对端 IP 复核 | 探针每次响应都调用 `_check_peer(..., transport, client is not None)` | 复用既有 `tests/test_paper_download_security.py` + `test_spec032_conference_pdf_download.py` |
| 入口同样过 `validate_url` 全量检查（协议/端口/认证参数/fragment/用户信息） | `validate_url` 未放宽 | `test_import_applies_url_security_to_the_resolver_entry_hop`（4 个参数化负例） |
| 解析器本身不是下载目标 | 入口 200/非 30x → `PDF_NOT_FOUND` | `test_import_never_downloads_the_resolver_itself` |
| 不新增"跳过校验"开关 | 无新参数、无环境变量 | 代码审查 + `resolve_doi_url` 签名 |
| 失败转稳定错误码 | `PaperDownloadError`（`DOWNLOAD_BLOCKED` / `DOWNLOAD_TIMEOUT` / `PDF_NOT_FOUND`） | `test_import_returns_a_stable_code_when_doi_resolution_fails`、`test_import_maps_a_doi_resolution_timeout_to_the_existing_code` |
| 空 allowlist fail-closed | 跳过解析 → `download_candidate` 拒绝 | `test_import_skips_doi_resolution_without_an_allowlist`（且断言零请求） |

**唯一的行为变化**：`pdf_url` 是 DOI 解析器地址且 allowlist 非空时，入库路径**多一次只读重定向探测**，
并用最终 host 参与白名单判定。

## 7. 既有语义保留（幂等 / 补偿 / 临时目录）

- **幂等**：解析发生在下载前的重复检查**之后**（`_find_existing` 命中即 return），
  所以"已导入"的记录不会被解析探针打扰，也不下载 → `test_import_still_short_circuits_on_an_existing_paper_before_any_network`。
- **补偿**：`port.import_paper()` 返回的错误码 → `PaperImportError` 的映射路径未改（解析失败在
  `port.import_paper` 之前，因此不涉及补偿；解析失败时 port 零调用，有断言）。
- **临时目录清理**：解析放在既有 `try:` 内，`finally` 里的 `_cleanup_download` /
  `_cleanup_attempt_root` 语义与调用顺序未改 → `test_import_removes_its_own_temp_root_after_a_rejected_doi`。
- **注入 downloader 的形态**：只换 `pdf_url`，Mapping → dict、dataclass → `replace`（保形），
  其余形态退化为快照字典（`download_candidate` 与浏览器会话都接受 Mapping）
  → `test_import_preserves_the_candidate_shape_for_injected_downloaders`。

## 8. 测试结果（真实输出）

```bash
cd /Users/wjh/work/ResearchAgent-2/ResearchAgent

# 1) 任务验收命令（基线 214，未变少）
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_spec032_conference_pdf_download.py \
  tests/test_spec032_ccs_source.py tests/test_spec032_ieee_sp_source.py \
  tests/test_spec032_ndss_source.py -q
# 214 passed in 1.16s

# 2) 新增用例
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_spec032_doi_resolver_import.py -q
# 28 passed, 5 warnings in 0.82s

# 3) 相关回归（paper_import / batch / download / security / browser / kb 边界）
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_paper_import.py \
  tests/test_paper_import_batch_service.py tests/test_paper_import_batch_integration.py \
  tests/test_paper_import_batch_api.py tests/test_paper_import_batch_store.py \
  tests/test_paper_import_identity.py tests/test_paper_import_generation_binding.py \
  tests/test_paper_import_index_failure_code.py tests/test_import_compensation.py \
  tests/test_paper_download.py tests/test_paper_download_security.py \
  tests/test_paper_browser_manager.py tests/test_paper_discovery_api.py \
  tests/test_kb_application_boundary.py tests/test_download_outcomes.py \
  tests/test_article_services.py -q
# 231 passed, 6 warnings, 12 subtests passed in 9.74s

# 4) 静态检查
env -u PYTHONPATH .venv/bin/python -m ruff check backend/app/paper_discovery
# All checks passed!

# 5) 导入冒烟
env -u PYTHONPATH .venv/bin/python -c "import backend.app.paper_discovery.application.paper_import as m; print(m.resolve_doi_url)"
# <function resolve_doi_url at 0x...>
```

### 真实网络验收（修复前 0/5 → 修复后 5/5）

```bash
env -u PYTHONPATH .venv/bin/python \
  .codebuddy/skills/ccs-paper-acquisition/scripts/acceptance_ingest_loop.py \
  /tmp/ndss_2024_enriched.jsonl --host www.ndss-symposium.org --limit 5
```

```
候选 140，取 5 条；allowed_hosts=('www.ndss-symposium.org',)

  OK   10.14722/ndss.2024.24017    paper_id=stub-1     895,373B pdf=True sha=df36563e6e7454d2
  OK   10.14722/ndss.2024.24006    paper_id=stub-2   1,441,521B pdf=True sha=dd7a16e8aa5cad18
  OK   10.14722/ndss.2024.24992    paper_id=stub-3   1,578,255B pdf=True sha=bcb8d893c16f4b69
  OK   10.14722/ndss.2024.23009    paper_id=stub-4   1,198,043B pdf=True sha=70d3df5489d4f84c
  OK   10.14722/ndss.2024.23419    paper_id=stub-5   2,192,716B pdf=True sha=28e46fafef504f2d

入库闭环结果: 5/5
知识库侧记录数: 5
```

脚本**未做任何修改**（参数、断言都保持原样），直接跑通。

### 新增用例清单（`tests/test_spec032_doi_resolver_import.py`，28 个）

| 组 | 用例 | 锁定的行为 |
|---|---|---|
| 唯一实现 | `test_the_downloader_and_the_import_path_share_one_resolver_implementation` | 两处引用同一函数/常量对象（禁止第二套实现） |
| | `test_the_resolver_host_set_stays_closed` | 解析器主机是封闭集合；非解析器主机返回 `None` |
| | `test_both_call_sites_hand_the_same_resolved_url_to_the_download_chain` | 两条路径交给下载链的最终地址一致；白名单无 `doi.org` |
| | `test_both_call_sites_reject_the_same_unauthorized_doi` | 失败路径错误码一致 |
| (a) 入库成功 | `test_import_resolves_a_doi_resolver_url_through_the_final_allowlisted_host` | 真实 `download_candidate`：`allowed_hosts` 只含最终主机 → 入库成功、SHA256 对账、探针次数 |
| | `test_import_snapshot_records_the_address_that_was_actually_downloaded` | 快照 `pdf_url` = 实际下载地址 + `pdf_url_original` 留痕 |
| | `test_every_doi_resolver_host_is_resolved_in_the_import_path[4]` | 4 个解析器主机都识别 |
| | `test_import_resolves_the_doi_address_before_the_download_chain_runs` | 下载链收到的是解析后地址 |
| | `test_import_preserves_the_candidate_shape_for_injected_downloaders` | dataclass 候选保形，只换 `pdf_url` |
| (b)(c) 安全负例 | `test_import_rejects_a_doi_that_resolves_to_an_unauthorized_host` | 未授权最终主机 → `DOWNLOAD_BLOCKED`，port 零调用 |
| | `test_import_rejects_an_unauthorized_intermediate_hop` | **中间跳**未授权同样拒绝 |
| | `test_import_rejects_a_doi_that_resolves_to_a_private_address` | 解析到 `127.0.0.1` → 拒绝（走到 DNS 校验） |
| | `test_import_bounds_doi_redirect_chains` | 重定向环有上限 |
| | `test_import_applies_url_security_to_the_resolver_entry_hop[4]` | http / 认证参数 / fragment / 用户信息 → 拒绝且零请求 |
| | `test_import_never_downloads_the_resolver_itself` | 解析器 200 → `PDF_NOT_FOUND`，不下 `doi.org` |
| | `test_import_skips_doi_resolution_without_an_allowlist` | 空 allowlist fail-closed 且零探针 |
| | `test_import_returns_a_stable_code_when_doi_resolution_fails` | 网络失败 → 稳定码 |
| | `test_import_maps_a_doi_resolution_timeout_to_the_existing_code` | 超时 → `DOWNLOAD_TIMEOUT` |
| (d) 回归保护 | `test_import_keeps_direct_pdf_urls_unchanged` | 直连 URL 零探针、快照无解析留痕 |
| | `test_import_skips_resolution_for_a_candidate_without_a_pdf_url` | 无 `pdf_url` 零探针 |
| | `test_import_still_short_circuits_on_an_existing_paper_before_any_network` | 幂等：已存在 → 零探针零下载 |
| | `test_import_removes_its_own_temp_root_after_a_rejected_doi` | 解析被拒仍清理自建临时根 |

全部用例用 `httpx.MockTransport` + in-memory port 桩，**不依赖真实网络与 chromium**；
入库成功用例走**真实** `download_candidate`，页码校验用一页真实 PDF（`pymupdf` 生成）。

## 9. 残留风险

1. **多一次只读往返**（继承上一轮）：`pdf_url` 是 DOI 解析器地址时，入库/下载各多一次 GET 探针
   （只读 header 即离开，但服务端可能已推送少量字节）。140 条约多 140 次往返。改用 HEAD 需处理
   405/501 回退，未做。
2. **探针无 connect 级 IP 固定**（继承上一轮）：DNS 在校验时解析一次、httpx 连接时再解析一次，
   理论上有 rebinding 窗口；缓解措施是 `_check_peer` 对**探针响应**同样复核 peer IP（真实
   transport 必须给出可校验地址），与下载链同等级。属既有架构共性问题，非本次引入。
3. **`pdf_url_original` 键名是本轮新引入的约定**：目前无人读取（纯留痕）。若上游 candidate 自身
   带了同名键，解析成功时会被覆盖；实际不可能冲突——只有当 `pdf_url` 还是解析器地址时才会写，
   而"上一轮产物"的 `pdf_url` 已是最终地址，不会再触发解析。
4. **`allowed_hosts` 现在被 `tuple()` 物化**：语义等价（`download_candidate` 只遍历它），
   且修掉了"生成器被解析用掉、下载拿到空集合"的隐患；但如果某处依赖传入对象的**身份**（目前没有），
   会受影响。
5. **部署配置才是真正的闸门**：本修复只解决"解析器地址被误拒"。若某部署的
   `paper_discovery_allowed_hosts` 里没有 `www.ndss-symposium.org`，解析仍会在第一跳被拒
   （fail-closed，符合预期）。生产启用 NDSS 需确认该配置。
6. **NDSS 适配器当前产出的是 Crossref primary resource 直链**（见 `ndss-adapter-report.md`），
   所以本次修复真正覆盖的是 OpenAlex 富化 / Task05 合并路径产出的 DOI 解析器形态，
   属**防御性修复**；建议 Task05 合并后再跑一次真实批量验收确认端到端命中率。
