# Spec032 Task14：四会议逐年来源覆盖审计

> 角色：`backend-tester`  
> 审计时间：2026-10-08（Asia/Shanghai）  
> 分支：`codex/spec032-final-acceptance`，HEAD `5b1b1d9`  
> 范围：只读核对 Spec032、Task07、Task14 现有证据；未同步外站、未下载 PDF、未启停服务、未读取或输出 `.env` 秘密。

## 最终裁决

**BLOCKED / NO-GO：当前 `GET /api/papers/sources` 的 `verified_years` 不能作为 Spec032 年度覆盖证明。**

Spec032 要求每个来源×年度同时有固定样本、受控真实目录抓取、字段质量统计和导入结果；`MIN_YEAR`/`MAX_YEAR` 或参数可接受范围不构成覆盖证明（`docs/sdd/specs/032-research-source-expansion.md:45-50,137-145`）。当前 `verified_years` 是 `SourceRegistry` 的静态配置值，由 API 原样投影，不读取真实 fetch unit、字段 provenance 或可信全文导入结果：

- `backend/app/paper_discovery/infrastructure/source_registry.py:46,102-123` 静态声明 USENIX `2022..2026`、IEEE S&P `2024`、NDSS `2024`，CCS 为空。
- `backend/app/api/routes_paper.py:1488-1501,1516-1537` 直接调用 `entry.to_dict()` 返回 `verified_years`；`health.network_probe` 明确为 `not_performed`。
- 全仓代码引用中没有将 `verified_years` 与 `source_fetch_units`、`field_provenance`、`paper_import_items` 或 Task14 证据产物绑定的实现；现有测试只锁定字段形状/静态值，没有“证据不足不得进入 verified_years”的门禁。

因此，USENIX 的 `2022–2026` 是把适配器支持范围/历史资产声明成了已验证年度；IEEE S&P/NDSS 的 `2024` 至多是官方目录固定样本和目录同步年度，尚未证明可信全文导入。该语义冲突是 Task14 收口阻塞项，也是用户可见的覆盖过度宣称风险。

## 证据矩阵

状态含义：

- `已证明`：有可复核的固定样本或脱敏运行记录；不自动推导完整年度覆盖。
- `部分`：官方目录链路或字段链路有证据，但缺完整字段/可信全文导入门禁。
- `未验证`：只有代码能力、聚合 fallback、缓存行或测试片段，没有本年度可签收的 Task14 真实证据。
- `NO-GO`：Task07 明确拒绝把官方身份不完整或动态页面当成官网年度覆盖。

| 来源 / 年度 | 固定样本 | 受控真实官方目录 | 摘要/字段质量 | 可信全文导入 | 当前结论 |
|---|---|---|---|---|---|
| USENIX 2022 | 有 parser 测试片段，但无 Task07 年度 fixture/hash 交接 | 无 Task14 真实请求/响应记录；本地缓存有 176 行，但 fetch unit 的 `year` 全为 NULL | 本地缓存显示 176/176 有摘要；不是可复核年度交接物 | 本地仅有 cancelled/failed 项，无成功交接物 | 未验证 |
| USENIX 2023 | 同上，无年度验收交接 | 无 Task14 真实请求/响应记录；本地缓存有 246 行，fetch unit 年份未持久化 | 本地缓存显示 246/246 有摘要 | 本地有 1 个 completed 项，但没有对应 Task14 请求/产物证据，不能代替签收 | 未验证 |
| USENIX 2024 | `tests/fixtures/usenix/usenixsecurity24-{summer,fall}-accepted-papers.html`；配套 parser/source 测试 | `runtime-smoke-20260922.md`：两个官方页面单元，`completed`，227 篇；重启后缓存仍可读 | 同一真实 smoke 记录 227 篇候选摘要可用；目录/详情两阶段可读 | `real-usenix-import-smoke-20260921.md` 记录 1 篇公开候选经安全链 `indexed`；本地缓存另有 completed 项，但不扩展历史产物结论 | 受控单年度闭环；不代表 2022–2026 全覆盖 |
| USENIX 2025 | 有 `usenixsecurity25-cycle1` 测试 fixture，但无年度 Task07/Task14 真实交接 | 无 Task14 真实请求/响应记录；本地缓存有 245 行 | 本地缓存显示 245/245 有摘要，不能替代年度来源统计 | 无可复核成功导入记录 | 未验证 |
| USENIX 2026 | 有 `cycle1-accepted-papers.html` 测试 fixture/解析片段，但不是年度真实验收 | 本地缓存没有 2026 目录行或真实同步记录 | 无 | 无 | 未验证；当前静态 `verified_years` 明确过度 |
| IEEE S&P 2021/2022/2023/2025 | 无固定官方 fixture；官方路由表只注册 2024 | 无 | 无 | 无 | 未验证 |
| IEEE S&P 2024 | `artifacts/task-07/ieee_sp-coverage.md` 与 `tests/fixtures/ieee_sp/official-program-papers-2024.html`，3 条，hash 已记录 | `real-usenix-import-smoke-20260921.md` 追记官方同步 43 篇；本地 `sp:2024:official` completed 43 | 官方样本 3/3 明确摘要/关键词缺失；本地官方记录 43 条同样无摘要/关键词 | 候选导入因 `ieeexplore.ieee.org` DNS 失败返回 `DOWNLOAD_BLOCKED`，无成功导入 | 部分目录证据，不能进严格 `verified_years` |
| ACM CCS 2021/2022/2023/2024/2025 | `artifacts/task-07/ccs-coverage.md` 明确不生成官网 fixture/hash；Crossref/OpenAlex fixture 不是官网样本 | 2021/2022/2024 身份键不足，2023 动态数据库故障，2025 JavaScript/空列表；没有官方年度目录合同 | 只有聚合 fallback 字段；本地 2024 的 328 行、摘要/关键词/PDF 不能写成官网字段 | 无可信成功导入；本地 2024 有 1 项 `waiting_login`、无 document | `NO-GO`，当前空 `verified_years` 正确但缺显式状态解释 |
| NDSS 2021/2022/2023/2025 | 无固定官方 fixture；官方路由只注册 2024 | 无 | 无 | 无 | 未验证 |
| NDSS 2024 | `artifacts/task-07/ndss-coverage.md` 与 `tests/fixtures/ndss/official-accepted-papers-2024.html`，3 条，hash 已记录；仅 bounded subset | `runtime-smoke-20260922.md`：official 单元 142 篇，`completed`；本地 official/fallback 两单元均 completed | 官方固定样本 3/3 摘要/关键词缺失；本地丰富摘要/关键词/PDF 来自 DOI/聚合回退，不能倒写成官网字段 | 没有 Task14 成功导入记录 | 部分目录证据，不能进严格 `verified_years` |

### 目录/字段/导入证据的边界

1. IEEE S&P/NDSS 的 2024 产物明确把官方页面缺失摘要/关键词记为 `missing`；这证明了缺失语义和解析样本，不证明全文下载或入库。
2. CCS 的 Crossref/OpenAlex 真实 fixture 可证明 fallback 解析和字段合并，但官方目录审计仍为 bounded NO-GO；聚合字段不得抬升为官网覆盖。
3. USENIX 2024 是当前唯一同时有受控官方目录运行记录、摘要详情链和至少一个安全导入成功样本的年度；其余 USENIX 年度不能因 parser 支持或本地缓存行存在而进入 `verified_years`。
4. 本地只读 SQLite 快照（`data/paper_search/state.sqlite3`）可作为诊断交叉核对：IEEE S&P 2024 official 43、CCS 2024 fallback 328、NDSS 2024 official 142 + fallback 140、USENIX 2022–2025 目录行存在；但 USENIX 234 个 fetch unit 的 `year` 全为 NULL，且该快照没有 Task07 年度固定样本/真实请求 artifact，故不把它升级为年度验收证据。

## 运行与回归核对

### 8000 真实只读探活

本轮未改变服务状态，执行：

```text
GET http://127.0.0.1:8000/api/papers/sources  -> HTTP 000（connection refused）
GET http://127.0.0.1:8000/api/health           -> HTTP 000（connection refused）
```

因此本轮不把旧 8000 响应冒充当前 live 证据；主会话已提供的 `verified_years={usenix:[2022..2026], ieee_sp:[2024], ndss:[2024], ccs:[]}` 与代码静态值一致，但其语义缺陷仍成立。

### 2026-10-08 探活解释补正（保留原失败证据）

上面的 `HTTP 000（connection refused）` 来自本代理的沙箱网络命名空间；它只证明该沙箱当时无法连接 `127.0.0.1:8000`，不能推出宿主机服务未监听。该失败响应与原始记录保留，不再将其表述为“8000 未监听”。

本次以只读、升级权限重新请求：

```text
GET http://127.0.0.1:8000/api/ready -> HTTP 200
{"ready":true,"warmup":{"jieba":{"status":"ready"},"ollama_tags":{"status":"ready"},"embedding":{"status":"ready"},"qdrant":{"status":"ready"}}}
```

因此，当前真实服务的 `/api/ready` 已有 2026-10-08 的 `200`/四项 warmup ready 证据；这只修正网络可达性与监听状态的解释，不增加任何来源年度覆盖证据，也不改变 `verified_years` 静态配置的语义缺陷。

### 精确后端回归

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_source_authority_contract.py tests/paper_discovery/test_official_catalog_coverage.py tests/paper_discovery/test_ccs_catalog_coverage.py tests/paper_discovery/test_ndss_official_catalog.py` | 0 | 17 passed |
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_paper_sources_api.py -k 'get_sources'` | 0 | 5 passed，17 deselected |

这些测试证明来源 ID/权威、Task07 固定样本解析、CCS NO-GO 交接和 API 配置级读取均未回归；它们没有证明外站当前可用，也没有约束 `verified_years` 必须由四维证据驱动。

## 下一项最小 backend-dev 工作

### 建议 Task：修正年度字段语义并加严格门禁（不重写来源适配器）

1. **`backend/app/paper_discovery/infrastructure/source_registry.py`**
   - 将 `verified_years` 改为严格验收字段：在现有证据下仅保留 USENIX `2024`（受控单年度闭环）；IEEE S&P、CCS、NDSS 暂为空。
   - 若 UI/Planner 仍需知道“有官方样本/路由可尝试的年度”，新增明确命名的 `official_sample_years` 或 `catalog_capability_years`，不得复用 `verified_years`；其说明必须写明“不是 Spec032 覆盖证明”。
   - 不把 `MIN_YEAR/MAX_YEAR`、适配器 URL 表或本地缓存行写入 `verified_years`。

2. **`backend/app/api/routes_paper.py`**
   - 维持现有无副作用 `/api/papers/sources`，但返回可区分的 `verified_years` 与 sample/capability 字段；前端显示时不能把 sample/capability 标签渲染成“已覆盖”。
   - 不在 GET 端点触发外站探测或 PDF 请求；当前 `health.network_probe=not_performed` 约束继续保留。

3. **USENIX 年份持久化的最小配套修复（若后续要动态计算）**
   - `backend/app/paper_discovery/infrastructure/usenix_publication_source.py:555-617,866-902` 创建 listing/detail `SourceFetchUnit` 时传入对应 `year`；当前 234 个 USENIX fetch unit 的 `year` 全为 NULL，不能直接按 fetch unit 做年度证据聚合。
   - 在 `tests/paper_discovery/test_usenix_publication_source.py` 增加 listing/detail unit 年份持久化断言；该配套不应被本次静态字段修复偷偷扩大成批量重抓。

### 精确测试建议

- 更新 `tests/paper_discovery/test_source_authority_contract.py::test_registry_exposes_canonical_entries_and_protects_required_sources`，断言严格 `verified_years`；新增断言 sample/capability 年度不会被误命名为 verified。
- 更新 `tests/paper_discovery/test_paper_sources_api.py::test_get_sources_returns_registered_sources`，逐来源断言 API 返回的 verified/sample 字段和标签；保留 `health.network_probe == "not_performed"`。
- 在 `tests/paper_discovery/test_usenix_publication_source.py` 增加 listing/detail `SourceFetchUnit.year` 回归；不要用 `MIN_YEAR/MAX_YEAR` 断言年度覆盖。
- 保持现有 `tests/paper_discovery/test_official_catalog_coverage.py`、`test_ndss_official_catalog.py`、`test_ccs_catalog_coverage.py`：它们应继续分别证明 2024 bounded sample、字段 missing、CCS 五年 NO-GO，而不是把 fixture 计数改成年度全覆盖。

### 修复完成条件

修复后 API 仍只能报告严格通过的年度；真实目录/字段/导入证据仍由 Task14 逐年补充。只有新增年度 artifact 同时列出固定样本、真实请求/响应、字段统计、可信导入实体 ID/最终状态和产物路径后，才允许把该年度加入 `verified_years`。本审计不建议为解除阻塞批量同步、下载或猜测 CCS 官方 API。

## 风险、阻塞与耗时

- **收口阻塞**：四会议首轮年度矩阵未闭环；IEEE/NDSS 只有 2024 官方目录样本/同步，CCS 全部官方年度 NO-GO，USENIX 仅 2024 有完整受控样本链。
- **用户可见风险**：若 UI/Planner 直接把 `verified_years` 当作“已覆盖”，USENIX 2022/2023/2025/2026 会被错误宣称成功；`MIN_YEAR/MAX_YEAR` 也可能被误认为覆盖范围。
- **证据路径风险**：Task07 计划引用 `docs/sdd/plans/032/artifacts/task-07/`，实际交接物位于仓库根 `artifacts/task-07/`；当前 CCS 测试读取的是根 `artifacts/task-07/ccs-coverage.md`。本轮未修改路径，后续收口应统一引用以便复核。
- **服务证据风险**：原始沙箱请求对 8000 不可达，但不能据此判断服务未监听；2026-10-08 升级权限只读 `/api/ready` 已返回 200 且四项 warmup ready。本轮未启动/停止服务，也未将旧 18080 记录当作当前 live 证据。
- **耗时**：约 20 分钟（恢复后，含只读代码/证据核对、SQLite 只读聚合、精确回归与报告落盘）。

## 产物与日志

- 本报告：`docs/sdd/plans/032/artifacts/task-14/current-source-coverage-audit.md`
- 进展日志：`.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261006-224051.md`
- 关键既有证据：`artifacts/task-07/coverage-matrix.md`、`artifacts/task-07/ieee_sp-coverage.md`、`artifacts/task-07/ndss-coverage.md`、`artifacts/task-07/ccs-coverage.md`、`docs/sdd/plans/032/artifacts/task-14/runtime-smoke-20260922.md`、`artifacts/task-14/real-usenix-import-smoke-20260921.md`。

**本角色未修改业务代码、测试代码、环境变量或服务进程。**
