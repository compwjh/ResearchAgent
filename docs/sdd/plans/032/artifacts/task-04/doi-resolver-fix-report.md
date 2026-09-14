# Task 04 附件：DOI 解析器地址（doi.org）下载失败修复

> 日期：2026-09-15 ｜ 影响面：`backend/app/paper_discovery/infrastructure/conference_pdf_downloader.py`
> 触发：NDSS 记录 `pdf_url=https://doi.org/10.14722/ndss.2024.24017`，`allowed_hosts=("www.ndss-symposium.org",)`
> 时 100% `DOWNLOAD_BLOCKED`。

## 1. 结论

| 项 | 结果 |
|---|---|
| 根因 | `download_candidate` 在**跟随重定向之前**用 `allowed_hosts` 校验初始 URL |
| 改法 | 公开层下载前先解析 DOI 解析器地址，用**最终 host** 过 `allowed_hosts` |
| `allowed_hosts` 语义 | **不变**（`doi.org` 绝不进入下载白名单，也不新增任何"跳过校验"开关） |
| 新增/删除公开 API | 无（只新增模块内私有常量/函数与 3 个私有方法） |
| 定向回归 | `tests/test_spec032_conference_pdf_download.py`：**55 passed**（基线 38 → 新增 17） |
| 相关回归 | 16 个相关测试文件：**404 passed, 12 subtests passed** |
| 全量后端套件 | **2051 passed, 9 failed**（9 条全部来自其他 agent 的在改文件，见 §5 末尾） |
| 静态检查 | `ruff check`（改动文件）All checks passed |

## 2. 根因

`paper_download.download_candidate()` 的校验顺序是：

```
validate_url(pdf_url, allowed_hosts=...)   # ← 初始 URL，重定向之前
  → 循环: client.stream(GET, current_url)  # follow_redirects=False
          → 30x: validate_redirect_target(current_url, location, allowed_hosts=...)
```

`pdf_url` 是 `https://doi.org/<doi>` 时，被校验的主机是 **`doi.org`**（跳转入口），
而真正落地的 `www.ndss-symposium.org` 只在**第二跳**才参与校验——但第一跳就已经被
allowlist 拒绝了（`doi.org` 不在 `allowed_hosts` 里），循环根本进不去。

用 MockTransport 复现（与线上同一调用形态，`handler` 对 doi.org 返回 302 → NDSS 官方 PDF）：

```
allowed_hosts=('www.ndss-symposium.org',)                  -> DOWNLOAD_BLOCKED / 下载地址被安全策略拒绝
allowed_hosts=('doi.org', 'www.ndss-symposium.org')        -> OK url=https://www.ndss-symposium.org/wp-content/uploads/2024-17-paper.pdf
```

第二行就是"把 `doi.org` 加进白名单"的方案 B：能跑通，但 `doi.org` 可以 302 到**任意域名**，
把它放进下载白名单等于把主机白名单架空（`evil.example.test` 也会被放行）。**因此不可接受**。

## 3. 改法

改动全部落在 `ConferencePdfDownloader` 内部，调用方合同（构造参数、返回结构、错误码）不变。

### 3.1 新增模块级设施

```python
_DOI_RESOLVER_HOSTS = frozenset({"doi.org", "www.doi.org", "dx.doi.org", "www.dx.doi.org"})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})   # 与 download_candidate 一致

def _doi_resolver_host(url) -> str | None: ...              # 只认封闭集合里的主机，其余返回 None
```

`_DOI_RESOLVER_HOSTS` 是**封闭集合**（不接受调用方输入），且**只**用于校验解析入口那一跳，
从不参与下载目标的 allowlist 判定。

### 3.2 `_download_open_access()`：先解析，再交给既有下载链

```python
resolved = self._resolve_open_access_url(url)
result = self._download({"pdf_url": resolved}, self.settings, self.allowed_hosts, **self._download_kwargs())
```

- 非 DOI 解析器地址 → `_resolve_open_access_url` 原样返回（行为完全不变，有回归用例锁定）。
- `allowed_hosts` 传给下载链时**原样不动**，因此 `download_candidate` 会用它校验最终 host，
  并复核实际连接的对端 IP（`validate_peer_ip`）。

### 3.3 `_resolve_open_access_url()`：逐跳解析 + 逐跳校验

```
validate_url(url, allowed_hosts=_DOI_RESOLVER_HOSTS)        # 入口那一跳：DNS 公共地址/协议/端口/认证参数
loop:
    _probe(client, target)                                  # 只读 status + Location，不读响应体
    非 30x 且 redirects == 0 -> PDF_NOT_FOUND（doi.org 不是下载目标，fail-closed）
    非 30x 且 redirects > 0  -> 返回 target.url（已过 allowlist 的最终地址）
    无 Location 或 redirects >= max_redirects -> DOWNLOAD_BLOCKED「重定向次数超过限制」
    validate_redirect_target(target, location, allowed_hosts=self.allowed_hosts)  # 每一跳都过调用方白名单
```

- `max_redirects` 默认 `DEFAULT_MAX_REDIRECTS`（=5，`backend/app/core/url_security.py`）。
- `_probe()` 用 `client.stream(..., follow_redirects=False)` 并**立即离开上下文**，不读 body
  ——避免把整份 PDF 拉两遍（只多发一次头部往返 + 可能被服务端推送的首包字节）。
- 每跳都调用 `_check_peer(response, target, peer_ip_resolver, transport, supplied_client)`，
  与 `download_candidate` **同一套对端 IP 复核**：真实 transport 必须给出可校验的 peer IP，
  注入的 mock transport / client 才允许缺省（与既有实现判断条件完全一致）。

### 3.4 复用的既有符号（无第二套实现）

| 复用 | 来源 |
|---|---|
| `validate_url` / `validate_redirect_target` / `URLSecurityError` / `ValidatedURL` / `DEFAULT_MAX_REDIRECTS` | `backend/app/core/url_security.py` |
| `download_candidate`（真正下载） | `paper_download` |
| `_check_peer`（对端 IP 复核）、`_timeouts`（超时配置解析）、`_candidate_value` | `paper_download`（本模块原本已复用 `_candidate_value`） |
| `PaperDownloadError` + 既有错误码 `DOWNLOAD_BLOCKED` / `DOWNLOAD_TIMEOUT` / `PDF_NOT_FOUND` | `paper_download` |

## 4. 安全考量（对照 regression-guard 后端条目）

- **第 5 条（SQLite 迁移）**：不涉及。
- **第 6 条（并发领用）**：不涉及。
- **第 7 条（SSRF）**：**加强**，未削弱。
  - 内网/回环/链路本地/保留地址：由 `url_security._public_addresses` / `_unsafe_ip` 在**每一跳**拒绝，
    并有专门用例（`allowed_hosts` 含该主机、但 DNS 解析到 `127.0.0.1` → `DOWNLOAD_BLOCKED`）。
  - 重定向次数：`self.max_redirects`（默认 `DEFAULT_MAX_REDIRECTS`）硬上限，有用例。
  - 协议 / 端口 / 认证参数 / fragment / 用户信息：沿用 `validate_url` 既有检查。
  - 对端 IP 复核：`_check_peer`，与下载链一致（防 DNS rebinding 到内网）。
  - 未授权主机（含**中间跳**）：逐跳 `validate_redirect_target` → 拒绝，且**绝不进入下载链**（用例断言 `downloader` 零调用）。
  - 新增的网络出口复用调用方注入的 `client`/`transport`（`trust_env=False`），不自建第二套网络栈。
  - **没有**新增任何"跳过校验"的开关或参数；`doi.org` 没有被写进任何下载 allowlist。
- **第 9 条（禁止重复实现）**：下载 / 安全校验 / 超时 / 对端复核 / 浏览器会话 / 身份规范化全部复用既有实现。
- 凭据与日志：不记录 URL 中的认证参数（此类 URL 在 `validate_url` 阶段就被拒），不记录 cookie。

## 5. 测试结果（真实输出）

```bash
cd /Users/wjh/work/ResearchAgent-2/ResearchAgent

# 1) 定向（任务验收命令）
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_spec032_conference_pdf_download.py -q
# 55 passed in 0.56s

# 2) 相关回归（spec-032 四个文件 + 下载/安全/浏览器/导入/文章链共 16 个文件）
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_spec032_conference_pdf_download.py \
  tests/test_spec032_ccs_source.py tests/test_spec032_ieee_sp_source.py tests/test_spec032_ndss_source.py \
  tests/test_paper_download.py tests/test_paper_download_security.py tests/test_paper_browser_manager.py \
  tests/test_paper_import.py tests/test_paper_import_batch_integration.py tests/test_paper_import_batch_service.py \
  tests/test_paper_import_batch_api.py tests/test_paper_discovery_api.py tests/test_import_compensation.py \
  tests/test_article_services.py tests/test_article_download_probe.py tests/test_article_html_probe.py -q
# 404 passed, 6 warnings, 12 subtests passed in 9.97s

# 3) 静态检查与导入冒烟
env -u PYTHONPATH .venv/bin/python -m ruff check \
  backend/app/paper_discovery/infrastructure/conference_pdf_downloader.py \
  tests/test_spec032_conference_pdf_download.py
# All checks passed!
env -u PYTHONPATH .venv/bin/python -c "import backend.app.paper_discovery.infrastructure.conference_pdf_downloader"
# 导入冒烟通过

# 4) 全量后端套件（用于确认无跨模块回归）
env -u PYTHONPATH .venv/bin/python -m pytest tests -q -p no:randomly
# 9 failed, 2051 passed, 6 warnings, 62 subtests passed in 414.91s (0:06:54)
```

### 关于全量套件的 9 个失败（与本次改动无关）

失败清单：`test_chat_route.py`(2)、`test_conversation_compaction_summary.py`(3)、
`test_conversations_api.py`(1)、`test_frontend_model_library_contract.py`(1)、
`test_kb_upload_closure_matrix.py`(1)、`test_memory_repositories.py`(1)。

逐条核对失败原因，全部落在**其他 agent 正在进行的工作区改动**上：

| 失败 | 直接证据 | 关联的在改文件 |
|---|---|---|
| chat / compaction / conversations / memory 共 7 条 | 断言 `['system','user'] != ['system','system','user']`、`EvolutionCheckpoint ... 'running' == 'completed'`、`assert 'done' == 'failed'` | `routes_conversations.py`、`memory/repository.py`、`chat_graph.py`（均 `M`） |
| `test_frontend_model_library_contract.py` | 期望 `/assets/app.js?v=46`，实际 `?v=49` | `frontend/index.html`（spec-035，`M`） |
| `test_kb_upload_closure_matrix.py` | 冻结清单哈希不符：`backend/app/main.py` 期望 `4d6b6aab…` 实际 `79be3cb7…` | `backend/app/main.py`（`M`） |

补充证据：上述 6 个测试文件**均不引用** `conference_pdf_downloader` / `paper_discovery` 运行时逻辑
（`test_kb_upload_closure_matrix.py` 只对 `paper_discovery/application/paper_import.py` 做 AST 解析，
该文件本次未改）；且本次改动文件 `conference_pdf_downloader.py` **不在**该冻结清单的
`inventory_files`（8 项）内，清单失配项只有 `main.py` 与 `routes_kb.py`。

新增 17 个用例（`tests/test_spec032_conference_pdf_download.py` 第 4 节），全部用 fake transport，
不依赖真实网络与 chromium：

| 用例 | 锁定的行为 |
|---|---|
| `test_doi_resolver_url_downloads_through_the_final_allowlisted_host` | 端到端（**真实 `download_candidate`**）：`allowed_hosts=("www.ndss-symposium.org",)` 也能下成功 |
| `test_doi_resolver_url_is_resolved_before_the_allowlist_is_applied` | 下载链收到的是**解析后**地址；`allowed_hosts` 未被污染 |
| `test_every_doi_resolver_host_is_recognized[4 个主机]` | `doi.org` / `www.doi.org` / `dx.doi.org` / `www.dx.doi.org` 都被识别 |
| `test_doi_redirect_to_an_unauthorized_host_is_blocked` | 最终主机未授权 → `DOWNLOAD_BLOCKED`，下载链零调用 |
| `test_doi_redirect_to_a_private_address_is_blocked` | 主机在 allowlist 内但解析到 `127.0.0.1` → 拒绝（证明走到 DNS 检查） |
| `test_every_hop_of_a_doi_redirect_chain_must_be_authorized` | **中间跳**未授权同样拒绝 |
| `test_doi_redirect_chain_is_bounded_by_max_redirects` | 重定向环有上限（`<= DEFAULT_MAX_REDIRECTS + 1` 次探测） |
| `test_doi_resolver_without_a_redirect_is_never_downloaded` | 解析器直接 200 时 `doi.org` 不被当下载目标 |
| `test_doi_resolution_network_failure_returns_a_stable_code` | 网络失败 → 稳定错误码，不抛异常 |
| `test_doi_resolution_timeout_reuses_the_existing_timeout_code` | 超时 → `DOWNLOAD_TIMEOUT` |
| `test_non_doi_urls_never_trigger_a_resolution_probe` | 非 DOI 地址行为完全不变（探针零调用） |
| `test_doi_resolver_urls_still_skip_the_open_access_layer_without_an_allowlist` | 空 allowlist 仍是 `PDF_OPEN_ACCESS_SKIPPED`（fail-closed，不发请求） |
| `test_download_batch_degrades_when_doi_resolution_is_rejected` | 单条解析被拒不影响整批（`download_batch` 失败降级语义保留） |
| `test_classify_pdf_access_still_routes_doi_resolver_urls_to_the_open_access_layer` | `classify_pdf_access` 判定不变（仍是 `open_access`） |

## 6. `allowed_hosts` 语义是否变化

**不变，且是本次修复的核心约束。**

| | 修复前 | 修复后 |
|---|---|---|
| `allowed_hosts` 的含义 | 下载目标主机白名单（在**初始 URL** 上判定） | 下载目标主机白名单（在**每一跳的 URL** 上判定，含最终落地主机） |
| `doi.org` 是否可作下载目标 | 否 | **否**（解析探针只读 `Location`，从不下载其内容） |
| `doi.org` 是否进入白名单 | 否 | **否**（`_DOI_RESOLVER_HOSTS` 仅用于校验解析入口那一跳） |
| 未授权主机 | 拒绝 | 拒绝（最终主机与中间跳都拒绝） |
| 新增放行开关 | — | **无** |

唯一的行为变化：`pdf_url` 是 DOI 解析器地址时，**多一次只读重定向探测**，并用最终 host 参与白名单判定。

## 7. 残留风险与后续建议

1. **多一次往返 + 首包字节**：解析探针是一次 GET（只读 header 即离开），服务端可能已推送少量
   PDF 字节。140 条记录约多 140 次往返；如需进一步省流量可改用 HEAD 并在 405/501 时回退 GET，
   但会引入分支复杂度（未做）。
2. **探针本身无 connect 级 IP 固定**：DNS 在校验时解析一次、httpx 连接时再解析一次，
   理论上有 rebinding 窗口；缓解措施是 `_check_peer` 对**探针响应**同样复核 peer IP
   （真实 transport 必须给出可校验地址），与下载链同等级。若要彻底消除，需要把
   `dns_resolver` 结果固定到连接层（httpx 不支持），属既有架构的共性问题，非本次引入。
3. **解析器 200/4xx 的语义**：`doi.org` 未重定向时返回 `PDF_NOT_FOUND`（"DOI 未解析到可下载的地址"）。
   这是稳定错误码且 fail-closed（不会去下 `doi.org`），但如果上游希望区分"DOI 无效"与
   "DOI 解析到落地页"，可另加错误码——当前沿用既有码表，未新增。
4. **NDSS 适配器当前产出的 `pdf_url` 是 Crossref primary resource**
   （`https://www.ndss-symposium.org/.../*.pdf`，见 `ndss-adapter-report.md`），
   这类记录本次修复前后都能下。修复真正覆盖的是 `pdf_url` 为 DOI 解析器地址的形态
   （OpenAlex 富化路径 / Task05 合并路径 / 其他会议来源），属**防御性修复**，
   需要在 Task05 合并后再跑一次真实批量验收确认端到端命中率。
5. **未做真实网络验收**：本任务环境不联网，全部用例基于 fake transport；
   建议在有网环境用真实 NDSS 记录跑一次 `ConferencePdfDownloader(allowed_hosts=("www.ndss-symposium.org",))` 的
   5–10 条抽样，确认 `302` 链路与 peer IP 复核在真实 CDN 下同样通过。
