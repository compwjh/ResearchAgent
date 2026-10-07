# Task 14 来源年度与 USENIX fetch unit 修复报告

- 日期：2026-10-08（Asia/Shanghai）
- 分支：`codex/spec032-final-acceptance`
- 角色：backend-dev（Luna max 临时档）
- 范围：只修来源年度门禁和 USENIX `SourceFetchUnit.year` 新建持久化；不新增公开字段、表、模型、迁移、下载器或同步范围。
- 进展日志：`.codebuddy/agent-logs/spec-032/task-14/backend-dev/20261008-004315.md`

## 结论

修复已完成并通过后端定向回归。

`SourceRegistry.verified_years` 现在严格为：

```text
usenix  -> [2024]
ieee_sp -> []
ccs     -> []
ndss    -> []
```

这表示当前验收证据 allowlist，不表示 parser 支持范围、请求参数范围、真实目录全面覆盖、PDF 下载成功或可信全文导入全面完成。当前仍不能向用户宣称四会议 2021–2026 逐年覆盖。

## 探活证据修正

先前 `current-source-coverage-audit.md` 中的沙箱记录保留如下事实：沙箱命名空间对 `GET /api/papers/sources` 与 `/api/health` 返回 HTTP 000/connection refused。该记录只能证明沙箱网络不可达，不能证明宿主机 8000 未监听。

2026-10-08 以升级权限执行只读探活：

```text
GET http://127.0.0.1:8000/api/ready
HTTP 200
{"ready":true,"warmup":{"jieba":{"status":"ready"},"ollama_tags":{"status":"ready"},"embedding":{"status":"ready"},"qdrant":{"status":"ready"}}}
```

本轮没有启动、停止或重启服务；`/api/ready` 的 200 只证明当前服务 ready，不构成来源年度覆盖证据。

## 修改依据与实现

### SourceRegistry

文件：`backend/app/paper_discovery/infrastructure/source_registry.py:102-120`

- 移除 USENIX 的 `tuple(range(2022, 2027))`，只保留有当前闭环证据的 2024。
- 清空 IEEE S&P、CCS、NDSS 的 `verified_years`；它们的 2024 固定样本/同步或字段结果仍在 Task07/Task14 证据中，但不足以通过本字段的真实目录、字段、可信全文导入门禁。
- 增加代码注释，明确 `verified_years` 不是 parser 支持范围或下载/导入全面覆盖。
- 没有新增 `sample_years`、`capability_years` 或任何公开/API 字段，避免形成第二套覆盖存储。

### USENIX fetch unit 年份

文件：`backend/app/paper_discovery/infrastructure/usenix_publication_source.py:433-440,552-632,788-979`

- 新增受控 URL 年份解析：从既有 `usenixsecurity24`/`usenixsecurity25` 路径解析 2024/2025；不扩大允许的 URL 或年份范围。
- listing 的 pending/failed/completed `SourceFetchUnit` 创建均写入该 listing 的 year。
- detail 的 pending/failed/completed `SourceFetchUnit` 创建优先使用已有 `CatalogPaper.year`，缺失时从同源 presentation URL 解析 year。
- 既有 unit 保留已持久化的 `year`，包括旧的 NULL；不会因为本修复批量回填、重抓或迁移旧数据。旧 NULL 行若未来需要修复，必须另开有界迁移/证据任务。
- 保留原有缓存、租约、失败重试、详情去重和按请求年份过滤逻辑。

## 测试与验证

### 修改前基线

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_source_authority_contract.py tests/paper_discovery/test_paper_sources_api.py -k 'get_sources or registry_exposes_canonical_entries'` | 0 | 6 passed，20 deselected |
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_usenix_publication_source.py` | 0 | 42 passed，5 warnings |

### 测试先行红灯

新增年度和 unit-year 断言先于生产改动执行：SourceRegistry/API 2 failed，USENIX 年份 4 failed；失败分别复现硬编码年度和 `SourceFetchUnit.year is None` 根因。

### 修改后定向回归

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_usenix_publication_source.py` | 0 | 42 passed，5 个既有依赖弃用 warnings |
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_source_authority_contract.py tests/paper_discovery/test_paper_sources_api.py` | 0 | 26 passed |
| `.venv/bin/python -m pytest -q tests/paper_discovery/test_official_catalog_coverage.py tests/paper_discovery/test_ccs_catalog_coverage.py tests/paper_discovery/test_ndss_official_catalog.py` | 0 | 13 passed |
| `.venv/bin/python -m py_compile backend/app/paper_discovery/infrastructure/source_registry.py backend/app/paper_discovery/infrastructure/usenix_publication_source.py tests/paper_discovery/test_source_authority_contract.py tests/paper_discovery/test_paper_sources_api.py tests/paper_discovery/test_usenix_publication_source.py` | 0 | 编译通过 |
| `git diff --check` | 0 | 无空白/冲突标记问题 |

新增/调整的测试只位于 `tests/paper_discovery/`，覆盖：严格年度 allowlist、`/api/papers/sources` 映射、listing 成功/失败 unit 年份、detail 成功/失败 unit 年份。

## 风险、剩余缺口与下一项最小工作

- 当前数据库中历史 USENIX fetch unit 的 NULL year 不会被本次代码回填；这符合“不重抓/不回填旧数据”，但旧快照不能直接用于逐年聚合。
- `sync` 请求允许的年份参数仍是能力/输入范围，不是覆盖证明；任何 UI、Planner 或报告不得把它当 `verified_years`。
- IEEE S&P、CCS、NDSS 当前仍没有年度验收 allowlist；要加入某年，下一项最小 backend-dev 工作是先落盘该年度固定样本、真实官方目录响应、摘要/关键词/身份字段统计、可信全文导入实体 ID/最终状态及产物路径，再只改 `source_registry.py` 的对应元组并补契约测试。
- 本轮未修改 intake/plan、前端、环境变量、API schema、下载器，未做批量同步或下载，也未提交 commit。

## 交接路径

- 本报告：`docs/sdd/plans/032/artifacts/task-14/current-source-year-fix.md`
- 前置覆盖审计（含探活解释补正）：`docs/sdd/plans/032/artifacts/task-14/current-source-coverage-audit.md`
- 进展日志：`.codebuddy/agent-logs/spec-032/task-14/backend-dev/20261008-004315.md`

