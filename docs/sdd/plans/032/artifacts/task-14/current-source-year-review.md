# Spec032 Task14 来源年度修复后端独立复审

- 复审时间：2026-10-08（Asia/Shanghai）
- 分支：`codex/spec032-final-acceptance`
- 角色：`backend-reviewer`
- 复审依据：`current-source-year-fix.md` 及其声明的 source registry / USENIX source / source-contract 测试 diff
- 范围：`backend/app/paper_discovery/infrastructure/source_registry.py`、`backend/app/paper_discovery/infrastructure/usenix_publication_source.py`，以及对应来源 API、权威契约和 USENIX source 测试
- 明确排除：`paper_import_batch_service.py`、其测试、Intake/plan 预算修复及其他 agent 未完成 diff
- 业务代码：本轮未修改；仅新增本复审报告和进展日志

## 结论

**PASS（仅来源年度修复切片）：P0=0，P1=0，P2=0。**

当前 source registry 的年度 allowlist 与验收证据一致：

```text
usenix  -> [2024]
ieee_sp -> []
ccs     -> []
ndss    -> []
```

新增 USENIX listing/detail fetch unit 的 `year` 会随现有 URL 或已有 `CatalogPaper.year` 写入，成功、失败和详情补抓路径均保留该值；现有 unit 则继续保留已持久化值（包括 `NULL`）。本报告不把该行为表述为旧 `NULL` 回填，也不把测试/探活表述为真实目录覆盖或可信全文导入证据。

这只是本来源年度切片的结论，不代表整条 Task14 可部署：预算修复独立复审已发现 P1 并阻塞，batchservice 也不在本报告范围内。

## 核对结果

### 1. 严格 `verified_years`

- `source_registry.py:102-120` 仅将 USENIX 配置为 `(2024,)`，IEEE S&P、CCS、NDSS 使用既有默认空元组。
- `test_source_authority_contract.py` 锁定 registry 返回 `(2024,)` / `()`；`test_paper_sources_api.py` 锁定公开映射为 `[2024]` / `[]`。
- `SourceEntry.to_dict()` 和既有 API 字段未变；本次只是收紧配置值，没有新增 schema、公开字段或第二套覆盖字段。

### 2. 新建与现有 fetch unit 的年份持久化

- `usenix_publication_source.py:433-440` 从受控的既有 `usenixsecurity24`/`25` URL 路径解析年份。
- listing 的 pending、failed、completed unit 均携带 `unit_year`（约 `568-632`）；新 unit 因而进入既有 `source_fetch_units.year` 列。
- detail unit 优先使用已有 `CatalogPaper.year`，缺失时从同源 presentation URL 推导（约 `811-814`、`862-865`、`879-929`）；失败路径也携带同一年份（约 `971-983`）。
- 现有 row 明确取 `existing.year`，包括 `NULL`（约 `552-556`、`879-884`）；没有迁移、批量重抓或隐式回填逻辑。数据库 DDL、domain dataclass 和 store 映射不在本次 diff 中。
- 定向测试覆盖：2024 新 listing 成功、2025 listing 失败、2024 detail 成功，以及混合 listing/detail 失败的持久值；其中 SQLite 失败路径通过 `get_fetch_unit()` 检查写回值，成功详情路径检查新 unit 值。

### 3. 边界与安全

- 年度解析沿用既有 USENIX host/path 验证、缓存、租约、失败重试和请求年份过滤；本 diff 未扩大外部 URL 输入，也未引入动态 host、SQL、命令或凭据处理。
- `verified_years` 仅是当前验收证据 allowlist，不等价于 parser 支持范围、请求参数范围、全量目录覆盖、PDF 下载成功或可信导入完成。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_usenix_publication_source.py` | 0 | **42 passed**，5 个既有依赖弃用 warnings |
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_source_authority_contract.py tests/paper_discovery/test_paper_sources_api.py` | 0 | **26 passed** |
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_official_catalog_coverage.py tests/paper_discovery/test_ccs_catalog_coverage.py tests/paper_discovery/test_ndss_official_catalog.py` | 0 | **13 passed** |
| `.venv/bin/python -m py_compile backend/app/paper_discovery/infrastructure/source_registry.py backend/app/paper_discovery/infrastructure/usenix_publication_source.py tests/paper_discovery/test_paper_sources_api.py tests/paper_discovery/test_source_authority_contract.py tests/paper_discovery/test_usenix_publication_source.py` | 0 | 编译通过 |
| `git diff --check` | 0 | 无空白/冲突标记问题 |

## 未覆盖项与交接

- 未执行真实外部目录请求、批量同步、PDF 下载或可信全文导入；因此不提供真实 coverage 结论。
- 未对既有 `NULL` year 做回填验证；静态路径与代码注释确认本修复会保留它，任何旧数据迁移应另开有界任务。
- 未审阅 batchservice 或预算修复；请以各自独立报告为准。

进展日志：`.codebuddy/agent-logs/spec-032/task-14/backend-reviewer/20261008-004621.md`

