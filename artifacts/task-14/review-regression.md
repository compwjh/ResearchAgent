# Spec032 Task14：评审、回归与复用审计交接

> 日期：2026-09-20（Asia/Shanghai）
> 评审执行：Task14 review-regression 子 Agent（临时 Luna high）
> 范围：Spec032、Spec032.1、Task06–13 交接物、当前工作树 diff；未修改业务代码。

## 状态摘要

**离线回归绿，P1 已修复；受控目录 smoke 通过，收口仍阻塞。** Task08 已将新来源接入统一 `paper_discovery` Worker Tool，并补齐了 source-selection 离线契约；Task07 仍只有 IEEE S&P/NDSS 2024 固定样本，CCS 与其余年度未验证。服务已在 18080 启动，健康/就绪检查、浏览器加载、USENIX 2024 和 NDSS 2024 目录同步及重启后状态读取均通过；IEEE 外站本轮返回 `SOURCE_FAILED`，登录/导入、完整四会年度覆盖和业务批次恢复 smoke 仍未形成可签收证据。

## 测试命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec032*.py tests/test_paper_discovery*.py tests/test_research*.py tests/test_skill*.py tests/test_frontend*.py tests/test_spec029_frontend_acquisition_progress.py tests/test_spec030_frontend.py tests/test_spec031_frontend.py` | 0 | **751 passed**（P1 修复前基线），15 subtests passed，5 个 SwigPy* DeprecationWarning，13.78s |
| `.venv/bin/python -m pytest -q tests/test_spec032*.py tests/test_paper_discovery*.py tests/test_research*.py tests/test_skill*.py tests/test_frontend*.py tests/test_spec029_frontend_acquisition_progress.py tests/test_spec030_frontend.py tests/test_spec031_frontend.py` | 0 | **765 passed**（Task07/Task08/Task11 follow-up 后），15 subtests passed，5 个 SwigPy* DeprecationWarning，14.14s |
| `git diff --name-only -- '*.py' \| xargs .venv/bin/ruff check` | 0 | All checks passed |
| `.venv/bin/python -m compileall -q backend` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| `node --check frontend/app.js` | 0 | 通过 |
| `node --check frontend/research-tasks.js` | 0 | 通过 |
| `PORT=18080 RERANKER_ENABLED=false ./deploy/start.sh` | 0 | 启动成功；Uvicorn PID 40763，服务监听 18080，Reranker disabled |
| 真实浏览器打开 `http://127.0.0.1:18080/` 与 `#papers-view` | 0 | 页面加载成功，通知流请求返回 200 |
| `curl -sS http://127.0.0.1:18080/api/health` | 0 / HTTP 200 | `status=ok`，模型列表与 `paper_discovery_enabled=true` |
| `curl -sS http://127.0.0.1:18080/api/ready` | 0 / HTTP 200 | `ready=true`；jieba、Ollama、embedding、Qdrant 均 ready |

完整 pytest 原始输出：本机 `/tmp/spec032-task14-full-pytest.log`（运行产物，不作为仓库交接依赖）。

## P1 阻塞证据（历史复现，已修复）

1. `backend/app/research/application/planner.py:83-107` 接受并规范化七来源 `source_ids`，`backend/app/research/application/search_catalog_adapter.py:165-190` 也接受 `ieee_sp/ccs/ndss/openalex/crossref`。
2. 但 `CatalogSourceFactory.build` 在 `backend/app/research/application/search_catalog_adapter.py:95-96` 只允许 `usenix|dblp|all`；实际调用 `CatalogSourceFactory().build(source_scope="ieee_sp")` 返回 `ValueError: invalid catalog source scope`。因此 Planner 产生的新来源计划进入实际搜索 Worker 会降级为不可用，而不是调用对应 Adapter/Skill。
3. `backend/app/research/application/search_catalog_adapter.py:344-348,454-455` 的本地快照和远端 Graph 仍固定 `usenix-security`/`dblp`；未按新来源选择 `paper_discovery` 的统一 Worker Tool。
4. `backend/app/skills/registry.py:51-90` 的旧 `search_paper_catalog` schema 只允许 `usenix/dblp/all`；`backend/app/research/application/session_plan_generation.py:19-23,94` 的默认能力也固定 `usenix-catalog-orchestration + search_paper_catalog`，未包含 IEEE S&P/CCS/NDSS Skill 或 `paper_discovery`。

上述证据记录的是 Task08 修复前的缺口。修复后，`CatalogSourceFactory` 已接受七类来源，generic source 通过 `PaperDiscoveryToolFacade` 统一落入既有目录/缓存/provenance 链；新增离线契约覆盖了 source-selection、Worker Tool envelope 和结果物化。真实来源抓取仍需在可用网络环境中复验。

## 复用审计

| 能力 | 复用事实 | 结论 |
|---|---|---|
| 目录、缓存、provenance | `CatalogSourceRuntime` 写入既有 `PaperDiscoveryStore` 的 `search_jobs`、`source_fetch_units`、`catalog_papers`、`field_provenance`；SourceRegistry 只做工厂/缓存 | 未发现第二套目录缓存 |
| 下载、URL/SSRF、PDF 校验 | `paper_import.py`、`paper_download.py`、`_paper_candidate_hosts` 和既有 DOI/重定向安全链仍为唯一执行路径 | 未发现旁路下载器或任意 URL 信任 |
| 批任务、登录、恢复 | `PaperImportBatchService`、既有 import-item login/resume/retry API；Research acquisition 只做投影/策略 | 未发现第二套批状态机 |
| KB 上传/导入 | issue upload 调用既有 `routes_kb.upload_document`；自动导入复用 `ResearchAcquisitionService.confirm()` | 未发现第二套 PDF 仓库/导入器 |
| embedding/RAG | 新增 runtime/Worker 未创建 embedder；既有 `CatalogSearchGraph`/KB 能力保持单一出口 | 未发现第二套 embedding/RRF |
| Worker Tool | `PaperDiscoveryToolFacade` 是统一 envelope facade；generic source 已由 `CatalogSourceFactory` 注入 Research 搜索适配器 | 复用边界通过；真实来源抓取待 Task14 smoke |

## Task06–13 事实汇总

- Task06：统一合同定向回归通过。
- Task07：仅 IEEE S&P 2024 固定官网样本验证；CCS/NDSS 和其余年度为 NO-GO/未验证。
- Task08：Registry/同步 runtime 与 generic source Worker bridge 已定向通过；Task14 仍需真实来源 smoke。
- Task09：`worker-tool-v1` 注册/分派和两个来源契约测试通过；未验证来源保持 blocked。
- Task10–12：自动导入、issue recovery、前端契约的离线/定向测试通过；真实登录、上传、部署 smoke 留待服务启动。
- Task13：静态/契约通过，真实服务检索→导入 smoke blocked；032.1 评审台账仍未完成。

## Task07/Task08 follow-up 复评（2026-09-20）

- Task08 的多来源 source selection、`CatalogSourceFactory` 和统一 `paper_discovery` Worker Tool bridge：**离线 PASS**；相关定向测试与全套 Spec032 相关回归均通过。
- Task07 的覆盖状态：**PARTIAL_GO**。IEEE S&P 2024 与 NDSS 2024 仅有受边界约束的官方固定样本；CCS 以及其余年度仍是 `NO-GO`/`unverified`，不能据此宣称四大会议逐年覆盖。
- CCS bounded gate 已补证：56 项子 Agent 报告、主 Agent 复跑的 21 项定向测试均通过；官方身份键/动态页面不足仍保持 NO-GO，不新增不可靠 parser。
- Task11 recovery bridge 定向验证：`106 passed, 12 subtests`；waiting_login/failed/resolved 动作、resume 审计和重复上传保护已通过，仍未替代真实 headed-browser/远程上传 smoke。
- 运行时补充：沙箱外 `curl` 已验证 health/ready 为 HTTP 200；受控 USENIX 2024 sync 最终 `completed`、`paper_count=227`；修复后的 NDSS 2024 official route 最终 `completed`、`paper_count=142`，服务重启后两个 sync 句柄仍可读取 completed 状态；IEEE S&P 2024 本轮外站返回 `SOURCE_FAILED`/degraded，已如实记录。
- 当前结论：P1 已从“实现缺口”转为“需要更完整真实环境复验”；Task14 仍不得签收 Spec032，直到来源覆盖、候选评估→导入、登录/失败恢复和业务批次重启证据补齐。

## 主 Agent 需要执行的真实 smoke（本轮未执行）

1. 在可用端口启动 `./deploy/start.sh`（若 8000 被占用选可用端口），确认 `/api/health` 和 `/api/ready` 的真实状态。
2. 调用 `/api/papers/sources`，逐项检查 verified years、partial/NO-GO；对已验证年份执行受控 sync，轮询到真实终态并核对 SQLite 重启后状态。
3. 创建一份来源为 USENIX、IEEE S&P 2024 的批准 Research plan，确认实际 Worker 分别调用统一 `paper_discovery`，再对 CCS/NDSS 记录明确 blocked，而不是伪造覆盖。
4. 受控小样本执行候选评估→自动导入；模拟 `waiting_login`、错链、身份不确定、正确上传和重试，核对 issue/actions、KB document 句柄、`report_action=generate_new_version` 与旧报告不可变。
5. 重启服务后读取 source progress、issue、批任务快照，确认不重复 KB 文件/报告版本；保存脱敏响应和端口/命令到 Task14 artifact。

## 评审结论

三份门禁报告分别记录：需求评审打回（产品使用步骤仍为占位且覆盖范围未完全可操作化）、技术评审历史打回（P1 已通过 follow-up 修复）、验收不通过/阻塞（来源覆盖与真实 smoke/deploy 证据仍缺失）。因此 Spec032 不得标记 `已完成`，也不得声称四会议逐年覆盖或真实导入成功。

## 交接字段

- 状态摘要：离线回归绿；P1 已修复；官方年度覆盖、外部来源与真实 smoke/deploy 证据仍阻塞收口。
- 改动文件：仅新增 `artifacts/task-14/**`、`docs/sdd/reviews/032-*.md`、`docs/sdd/retro/2026-09-20-spec032-task14-review.md`、本 Agent 日志；未改业务代码。
- 测试命令/结果：见上表；765 passed，静态检查全通过；health/ready HTTP 200，IEEE 外站 degraded 已记录。
- 产物路径：`artifacts/task-14/review-regression.md`、`artifacts/task-14/live-smoke-checklist.md`、`docs/sdd/reviews/032-requirement-review.md`、`docs/sdd/reviews/032-tech-review.md`、`docs/sdd/reviews/032-acceptance-review.md`。
- 评审结论：打回/阻塞，见三份 review。
- 阻塞风险：官网年度覆盖不完整；真实外部来源、登录/导入、重启恢复及 API health 证据缺失；032.1 评审未闭环。
- 主 Agent 后续动作：补齐可验证的官方来源覆盖或记录 NO-GO；在可用网络环境完成 source-selection、候选评估、导入、重启恢复 smoke；由独立 tech-lead/tester 复评；再更新 spec、状态台账和复盘。
- 耗时：约 18 分钟（06:05–06:23 CST）。
- 模型：Luna high（临时执行配置）。

## Authority 与产品步骤 follow-up（2026-09-20）

- 已补齐 Spec032 产品使用步骤，覆盖来源选择、缓存进度、候选评估、批准导入、登录/上传/重试、重启恢复和报告版本。
- 已修复官网路由与 DOI 元数据共用 source ID 的权威混淆：官网 provenance 使用 `:official`，权威等级为 10；DOI 为 20；聚合来源为 30；低权威来源不能覆盖高权威字段。
- Authority/runtime 定向测试 `187 passed`；Spec032 Task06–13 合同复跑 `49 passed`；本轮审计范围 Ruff 检查通过。
- 以上修复不改变公开七来源 schema；四会议年度覆盖、真实候选导入、登录/上传、业务批次重启和独立签字仍未完成，结论继续为 `NO-GO`。

- 本轮新增字段 provenance 查询端点：`GET /api/papers/{paper_id}/provenance` 复用既有目录 Store；成功/404/503 契约与来源运行时定向组合回归为 `56 passed`，Ruff、compileall、`git diff --check`、两个前端 `node --check` 均通过。

## 2026-09-22 继续收口追记

- Semantic Scholar 429 合同补强：429 + `Retry-After` 后接网络异常时，网络异常使用指数退避，不复用旧响应头；OA 适配器与 Graph 客户端测试通过。
- Semantic Scholar bulk recall 的真实 SQLite 持久化/重启测试通过：fetch unit、目录论文、来源记录和字段 provenance 可读回，同 query 只发生一次 bulk 请求。
- paper_discovery/research/skills 集合回归：`1506 passed, 38 subtests`；测试布局、Ruff、`git diff --check` 通过。
- 18080 受控运行时证据：USENIX 2024 sync `sync-usenix-2f71bd0968624480` 完成 227 篇；NDSS 2024 sync `sync-ndss-6a4e6e04bb1641b5` 完成 142 篇；USENIX 2024 缓存检索冻结 227 篇、结果第一页 10 篇。检索终态 `partial/degraded=true` 仅反映当前索引/RAG 环境降级，目录结果仍可读。
- 以上新增证据仍不足以关闭 Task14：IEEE S&P/CCS 及未验证年度、候选评估→导入/人工恢复、业务批次重启和独立签字尚未完成。

## 主 Agent 受控 smoke 追记（2026-09-20）

- 服务：当前工作树前台启动于 `http://127.0.0.1:18080`，`RERANKER_ENABLED=false`。
- `GET /api/health`：HTTP 200；`GET /api/ready`：HTTP 200，jieba/Ollama/embedding/Qdrant 均 ready。
- `GET /api/papers/sources`：HTTP 200，返回 7 个受控来源；`verified_years` 只列已验证年份，IEEE S&P/NDSS 目前仅为 2024，CCS 为空，未把参数范围冒充覆盖证明。
- `GET /api/papers/458fd85c96aad64a9e36b9dbe8dad834/provenance`：HTTP 200，返回论文元数据和字段级 `source_id/source_record_id/observed_at`；未知论文返回 `PAPER_NOT_FOUND`/HTTP 404。
- `POST /api/papers/sources/ndss/sync`，范围 `2024`：HTTP 202，句柄 `sync-ndss-4d8028019cda49e8`；随后终态为 `completed`、`paper_count=142`、`error_code=null`，目录阶段未下载 PDF。
- `POST /api/papers/sources/usenix/sync`，范围 `2024`：HTTP 202，句柄 `sync-usenix-2f42eab646c74c19`；随后终态为 `completed`、`paper_count=227`、`error_code=null`，目录阶段仍未下载 PDF。
- 这组证据只证明服务、来源同步和 provenance 查询链可运行，不替代四会议逐年覆盖、ACM/IEEE 登录、PDF 导入和重启恢复的最终门禁。

## 进度投影修复追记（2026-09-20）

- Luna high 修复 `CatalogSourceRuntime` 的终态进度构造：成功抓取、缓存命中会写入真实 `fetch_unit_id`；失败单元不会进入 `completed_units`；partial 状态保留合法的 `merging` 进度状态并最终落为 `partial`。
- 定向验证：`.venv/bin/python -m pytest tests/test_catalog_runtime.py tests/test_spec032_task06_contract.py -q`，退出码 0，`15 passed`；Ruff 与 compileall 均通过。
- 重启当前工作树服务后，缓存优先 USENIX 2024 同步：句柄 `sync-usenix-09d551560dff4f0f`，HTTP 202，终态 `completed`，`paper_count=227`；`completed_units` 与 `cached_units` 均包含两个真实单元：
  - `usenix|usenix-security|/conference/usenixsecurity24/summer-accepted-papers/`
  - `usenix|usenix-security|/conference/usenixsecurity24/fall-accepted-papers/`
- 因此之前“同步已完成但 UI 显示 0 个完成单元”的投影缺陷已复现、修复并通过真实 API 验证。Spec032/032.1 仍不收口，外站覆盖、候选评估→导入及登录恢复等独立验收阻塞仍有效。

## Task13 真实 Skill smoke 追记（2026-09-20）

- 运行 `.venv/bin/python .codebuddy/skills/usenix-paper-assistant/scripts/search_papers.py --base-url http://127.0.0.1:18080 --query agent --years 2024 --limit 3`：退出码 0，返回 `search_id=f830dfc9d80e4c25bfd8a1da808c6cc6`、状态 `partial` 和 3 篇真实候选，候选含标题、年份、USENIX 详情页和摘要状态。
- 运行导入脚本：第一篇返回 HTTP 409（已在知识库），第二篇返回 HTTP 424（导入失败），第三篇 `077bbff9185f9f53d049e966115d36d3` 返回 `paper_id=7dfec772f919481aad9fc3bcbcf96041`、`status=indexed`、`existing=false`。
- 该结果证明 IDE Skill → 产品检索 API → 服务端候选快照 → 既有安全下载/导入链真实打通，同时保留 partial、重复和失败状态；不代表四会议逐年覆盖或 Spec032/032.1 已可收口。
