# 2026-10-06 整合独立评审

## 评审身份与范围

- 评审角色：Architect（`/root/branch_inventory`，独立只读复核）。
- 评审基线：`main@7bd9602`（`codex/integrate-current-code-to-main`）。
- 重点合并：`8392d14`（父提交 `cb7bf56` + `7cfef4d`）；同时核对其后的 `024c3a7`、`5e9144b` 与 `7bd9602` 是否回退关键行为。
- 重点文件：`routes_conversations.py`、`knowledge_base/application.py`、`platform/config.py`、`research/infrastructure/research_store.py`，以及 `frontend/app.js`、`frontend/index.html`、`frontend/research-tasks.js`、`frontend/styles.css`。
- 本轮没有 Git 写操作、产品/前端业务代码修改，也没有读取 `.env` 内容。

## 结论

**当前候选不具备验收放行条件；不得签署合并/部署 PASS。**

`8392d14` 的冲突解决没有发现 P0，也没有发现 032 功能被 037/041 代码性回退；但发现并由真实 API E2E 复现 1 个 P1 合同阻塞：037 启动自愈把 `auto_requeued_chunkers` 写入 `papers.json`，而 018 的冻结 KnowledgeDocument schema 禁止该顶层字段。结果是已有任一自动恢复标记的库在新 PDF/Markdown 上传时被严格校验拒绝，返回 `400 MIGRATION_INPUT_INVALID`。该问题必须修复并复跑真实上传 E2E 后，才能重新评审。

### P0

| 编号 | 结论 |
|---|---|
| P0 | **0 个**。在本次限定的合并差异与最终树中未观察到数据破坏、越权或会阻断服务启动的 P0。 |

### P1（阻塞）

#### P1-1：037 自愈标记与 018 严格 metadata schema 冲突

证据链：

1. `backend/app/knowledge_base/infrastructure/store.py:30-36` 将 `auto_requeued_chunkers` 定义为 `papers.json` 文档顶层字段；`mark_chunker_auto_requeued()` 在 `:832-849` 实际写入 `item[AUTO_REQUEUED_CHUNKERS]`。
2. `docs/sdd/plans/018/artifacts/task-03/knowledge-document.schema.json:7` 设置 `additionalProperties: false`，且属性表没有 `auto_requeued_chunkers`。
3. `backend/app/knowledge_base/infrastructure/migration.py:212-220` 的 `_validate()` 将 schema 错误统一转换为 `MIGRATION_INPUT_INVALID`；`:223-238` 的 `_read_metadata_for_write()` 对上传写路径中的全部既有记录执行该校验。
4. 当前真实 API E2E 已记录：Markdown 与固定 PDF 新上传均为 HTTP 400 `MIGRATION_INPUT_INVALID`，没有 `document_id`（见 `docs/sdd/plans/018/artifacts/task-07/current-api-e2e-report.md` §2–§5）。静态对照同时发现当前 40 条记录中 13 条含 schema 禁止字段。

影响：启动恢复功能与上传/metadata 写入合同不能同时成立；修复前不能把“启动自愈已接入”视为安全合并，也不能继续以旧文档替代新上传完成验收。修复方案需由负责实现的 Agent 明确选择并测试（例如演进冻结 schema，或将恢复幂等标记移至经过审计的旁车存储），并补齐真实 API E2E 与严格 schema 回归；本评审不代行修复。

#### P1-2：全量回归非零，验收仍未闭环

`docs/sdd/plans/018/artifacts/task-07/current-full-regression-report.md` 记录本基线命令退出码 `1`，结果为 `2872 passed / 10 failed / 3 skipped`。失败项的逐项根因与后续任务已在该报告登记（来源同步入口、FinalizeStore 路径、evaluator allowlist、worker test double、API infrastructure 边界等）。这些失败尚不能归因于本次合并冲突本身，但在复跑并关闭前，验收不得写成 PASS。

## 关键行为共存核对

| 目标 | 最终树证据 | 判定 |
|---|---|---|
| Spec032 恢复/交接能力 | `backend/app/api/routes_conversations.py:735-918` 仍有 sticky Skill 退出/下载 handoff、目录搜索 fallback、最新候选读取和 conversation-scoped Skill 恢复；`backend/app/api/routes_paper.py:1120-1160` 仍保留按 import item 隔离的浏览器 session 关闭、登录与 resume 恢复路径；`backend/app/paper_discovery/application/catalog_runtime.py:1-6` 仍复用统一 search/fetch/provenance store。 | 保留，未见被 037/041 覆盖或回退。 |
| Spec037 启动自愈 | `backend/app/main.py:58-65` 在 lifespan 调用 `recover_failed_reindexes()`，单项失败只记录并继续启动；实现位于 `backend/app/knowledge_base/application.py:875-921`。 | 逻辑存在，但触发 P1-1 合同阻塞。 |
| Spec037 SQLite 连接生命周期 | `backend/app/research/infrastructure/research_store.py:1192-1217` 将 `_connect()` 改为 context manager，事务内 yield、finally close；全文件调用点保持 `with self._connect()` 形态。 | 保留，静态核对未发现裸连接调用。 |
| 系统消息合并 | `build_role_aware_messages()` (`backend/app/chat/application/chat_runner.py:42-53`) 保持平台 system、用户规则、advisory 的角色消息；`normalize_ollama_messages()` (`backend/app/platform/ollama_direct.py:55-72`) 只在下发 provider payload 时把所有 system 合并到首条，并保持其他消息相对顺序与观测输入原形。 | 保留；未回退 041 的合并修复。 |
| 默认 direct | `backend/app/platform/config.py:130-134` 的 `OLLAMA_ROUTE` 默认值仍为 `direct`；`chat_runner.py:146-179` 对本地模型走 direct，对线上模型保留明确的 langchain 回退。 | 保留；没有被 merge 改回 langchain 默认。 |
| “定位”与原文切片链 | `frontend/research-tasks.js:2045-2172` 仍将 evidence locator 解析为 document/chunk/page/chunker 并可打开知识库切片；`frontend/kb-inspection.js:807-820,1042-1141` 仍绘制 PDF bbox、anchor 关系和 unmapped 原因；对应 `frontend/index.html:501-555` inspection DOM 契约存在。 | 保留，未见前端冲突解覆盖定位行为。 |

## 前端冲突与静态门禁

- `frontend/index.html` 当前资源版本为 `styles.css?v=56`、`app.js?v=57`、`research-tasks.js?v=15`、`kb-inspection.js?v=23`；与本次合并后的 app/style/task 变更相符。
- `node --check frontend/app.js frontend/research-tasks.js frontend/kb-inspection.js`：退出码 0。
- `git diff --check 8392d14^1 7bd9602 --`（限定上述后端/前端整合文件）：退出码 0。
- 前端既有 `frontend51pass` / `matrix2pass` 参考结果只能作为历史/范围参考；本评审未将其当作当前 Spec018 验收通过证据。当前真实 API 上传阻塞优先级更高。

## 评审独立性与测试文件说明

本 Agent 之前仅按 test-naming 要求完成 5 个测试文件的目录/编号整理（以及 `tests/evaluation/test_memory_probe.py` 的精确导入路径修正）；该整理不是本次代码整合评审对象，也不对这 5 个测试自评。它们须由 `/root` 独立复核；当前全量失败报告同样不能由本 Agent 代签。

## 待复审条件

1. 负责 Agent 修复 `auto_requeued_chunkers` 与 018 schema/写入合同，并补充针对“启动恢复后仍可上传”的回归。
2. 在不删除现有用户文档的前提下，重新执行 Markdown 与 PDF 真实上传，取得新 `document_id`，再完成状态、v1/v2 inspection、定位和 source Range/ETag 验证。
3. 关闭当前全量回归的 10 个失败项，重新运行同一全量命令；测试布局整理与 5 个移动测试由 root 独立复核。
4. 复审通过前，Spec018 保持 `NOT READY/BLOCKED`，不得更新为已完成或对用户宣称部署验收通过。

## 签字

- Architect（独立整合复核）：`/root/branch_inventory`，2026-10-06 21:49 +0800
- 判定：**P0=0；P1=2（其中 P1-1 为已复现运行时合同阻塞，P1-2 为全量回归非零）；暂不批准验收/部署放行，待修复后复审。**

---

## 最终候选复审：`ecbb91f` + `9a9733f`

### 复审范围与独立性

- 最终生产修复：`ecbb91f`；最终候选：`9a9733f`（HEAD）。
- 本次只复审 `ecbb91f` 的生产改动：`auto_requeued_chunkers` 严格 schema/迁移兼容、`SourceRegistry.adapter` 同步预检、`paper_discovery.application.entry` 受控导出。
- `9a9733f` 仅含三份测试合同更新。该测试改动由 `/root` 独立核对，本 Architect 不把自己此前参与的测试修改作为独立 review 证据。
- 未读取 `.env`，未修改业务代码或前端代码，未执行 Git 写操作。

### 生产修复核对

| 领域 | 证据 | 结论 |
|---|---|---|
| `auto_requeued_chunkers` strict schema | `knowledge-document.schema.json` 在顶层 `additionalProperties: false` 下声明可选 marker；仅允许 `v1`/`v2`、带时区 RFC3339 时间戳。`migration.py` 将 marker 纳入 legacy 白名单、原样保留，并同时执行显式 marker 校验与 Draft 2020-12 schema 校验。 | 通过；没有关闭 strict，也没有把恢复状态静默丢弃或移入未审计用户字段。 |
| 上传/迁移运行时闭环 | `current-api-e2e-success-report.md` / `current-api-e2e-success-evidence.json` 记录本轮真实 Markdown `a95357cf37344160859a812852f7863f` 与 PDF `f51024342ecd46a7a0c17adefbd67abd` 均 POST 201，最终 indexed；四个 v1/v2 inspection 均 200、manifest ready、非空 anchors、source hash verified；HEAD/Range 206/条件 GET 304/缺失 ID 404 均通过。服务重启提交为 `ecbb91f`，报告明确没有把后续 `9a9733f` 推断为已加载。 | P1-1 已由真实 API E2E 复验关闭；证据未覆盖既有用户文档删除或重建，且报告明确写明本轮仅新增授权样本。 |
| SourceRegistry 预检 | `sync_paper_source()` 在创建 `SearchJob`/progress 前调用唯一 `registry.adapter(...)` 组合入口；异常或 `None` 返回 409 `SYNC_ENTRYPOINT_UNAVAILABLE`，不可用来源不会写 durable job、不会提交后台调度。成功响应固定标记 `source_registry.adapter`。 | 通过；没有恢复第二份入口 map。 |
| application entry 边界 | Semantic Scholar client 与长度常量从 `paper_discovery.application.entry` 显式导出；`routes_paper.py` 不再直接 import `paper_discovery.infrastructure.semantic_scholar_metadata`。 | 通过；API→application→infrastructure 边界恢复。 |

### 最终验证证据

- 定向回归：`.venv/bin/python -m pytest -q tests/kb/test_metadata_auto_requeue_compatibility.py tests/paper_discovery/test_paper_sources_api.py tests/paper_discovery/test_catalog_runtime.py tests/system/test_api_module_boundaries.py` → **50 passed**, exit code 0。
- 最终全仓回归：`.venv/bin/python -m pytest tests --cov=backend --cov-report=term --cov-report=json:/private/tmp/researchagent-integration-final-coverage.json -q` → **2893 passed, 3 skipped, 67 subtests passed, 5 warnings**, exit code 0；总覆盖率 81.79139962786851%。该结果已追加至 `current-full-regression-report.md`，并保留首次 `2872 passed / 10 failed / 3 skipped` 历史段，不以新结果覆盖历史证据。
- 全仓结果仍有 43 个文件低于 80%；这不是本次候选的 P0/P1，但不能把总体覆盖率解读为逐文件达标。OpenTelemetry 向本机 `127.0.0.1:3000` 的导出失败/超时为运行环境告警，未改变 pytest 退出码，应与部署观测分开记录。

### 最终复审结论

**P0=0；当前候选未发现新的 P1；批准代码整合验收继续放行，Spec018 的最终状态仍以主会话完成部署/运行时验证及状态台账收口为准。**

原报告中的 P1-1（marker 与 strict schema 冲突）和 P1-2（全量回归非零）作为历史问题保留；本节仅依据 `ecbb91f` 重启后的真实 API E2E 与 `9a9733f` 最终全仓回归关闭它们，不删除或改写原始失败记录。

### 签字

- Architect（独立整合复审）：`/root/branch_inventory`，2026-10-06 22:11 +0800
- 候选：`ecbb91f` 生产修复 + `9a9733f` 最终树
- 判定：**P0=0；P1=0（历史 P1-1/P1-2 已由本节证据关闭）；代码整合复审通过，后续仅剩主会话按收口门禁完成部署/状态台账。**
