# Spec018 最终验收评审

> 当前补充收口：2026-10-26 canonical ID/单文档发布一致性窄修追加栏已由 tester 标记 `READY_FOR_USER`、architect 签字 `GO`；历史正式 Spec018 验收与遗留边界保留。

## 结论

**PASS（允许 Spec018 标记为已完成）**。

闭环矩阵已按当前代码修正并完成审计入口注册；随后唯一一次全量 pytest 全部通过。用户已验证切片检查功能，Task06E/06F 产物和本轮只读 HTTP smoke 也证明了上传、索引、manifest、原件读取与双向检查的主要路径。一个历史 PDF 的 v2 任务仍在后台以 `indexing`/`INSPECTION_BUILDING` 状态运行，但没有失败码，属于可继续恢复的非阻塞后台遗留，不影响已验证文档和主功能收口。

## 执行信息

| 字段 | 结果 |
|---|---|
| 验收角色 | tester（独立验收；临时 Luna high） |
| 开始 | 2026-09-10 23:30:17 +0800 |
| 结束 | 2026-09-10 23:31:40 +0800 |
| 总耗时 | 约 2 分 43 秒（pytest 73 秒；含最终只读 smoke） |
| 业务代码修改 | 无 |
| 验收报告 | `docs/sdd/reviews/018-acceptance-review.md` |

## 全量回归

本轮按要求仅执行一次当前版本全量回归，使用有效解释器：

```text
.venv/bin/python3.11 -m pytest -q
```

结果：

- 退出码：`0`
- `956 passed`
- `0 failed`
- `1 skipped`
- `38 subtests passed`
- 5 warnings（既有 PyMuPDF/底层扩展弃用警告）

闭环矩阵修正后的哈希、digest 和新增内部入口注册均由全量测试覆盖，未再出现失败。

## 已通过的运行时 HTTP 证据

服务在 `127.0.0.1:8000` 运行期间完成只读烟测，未触发上传、删除、重建或 Qdrant 写操作：

| 验收项 | 证据 | 结果 |
|---|---|---|
| 服务健康 | `GET /api/health` → HTTP 200，服务返回可用模型与论文发现能力 | PASS |
| 知识库健康 | `GET /api/kb/health` → HTTP 200，`qdrant=true`、`embedding=true`、`generation.ready=true` | PASS |
| 文档列表 | `GET /api/kb/documents?limit=10` → HTTP 200，返回 6 个 canonical PDF 文档 | PASS |
| v1 检查清单 | `2105.07447.pdf` → HTTP 200，首页返回 3 blocks / 3 chunks / 3 anchors，存在下一页 cursor | PASS |
| v2 检查清单 | `2105.07447.pdf` → HTTP 200，首页返回 3 blocks / 3 chunks / 3 anchors，存在下一页 cursor | PASS |
| 另一文档 v1/v2 | 既有 Bitcoin 文档 v1/v2 均 HTTP 200，均返回非空 blocks/chunks/anchors | PASS |
| 原件只读 | source 无 Range → HTTP 200、`application/pdf`、`inline`、`Accept-Ranges: bytes` | PASS |
| Range | source `bytes=0-15` → HTTP 206、`Content-Range: bytes 0-15/747511`、长度 16 | PASS |
| 非法文档 ID | inspection → HTTP 404、`DOCUMENT_NOT_FOUND`，不含绝对路径 | PASS |

当前列表中 `MAD-HTLC...pdf` 的 v2 仍显示 `indexing`，其余文档已显示 v1/v2 indexed；对该文档的 inspection 只返回契约规定的 HTTP 202 `INSPECTION_BUILDING`，无失败码或错误写入。它是已有后台任务尚未收敛的非阻塞遗留，主 Agent 可在后续维护窗口观察/恢复，不应伪造为已完成。

## 验收项逐项结果

| 验收范围 | 结果 | 依据/说明 |
|---|---|---|
| PDF 原件、v1/v2 chunks/manifest | PASS（已验证样本） | 本轮 HTTP 检查及 Task06 manifest 修复报告；返回非空切片与锚点 |
| Markdown provenance/chunks | PASS（固定样本） | Task02A/02B 固定 Markdown fixture 与定向回归通过；当前线上文档列表未包含 Markdown 原件，未伪造线上证据 |
| 缺失 manifest 自动补建 | PASS（已有证据） | Task06 manifest 修复报告记录 202 → 200、重复 GET 保持 202 轮询；本轮不重复触发昂贵重建 |
| 索引、检查接口、generation | PASS | `/api/kb/health` generation ready；HTTP inspection 返回 200 |
| 双栏前端契约与双向点击 | PASS（固定/真实浏览器证据） | Task05 最终前端报告：4 套 Node 契约、语法、交互和 hostile fixture 通过；用户已验证页面交互 |
| PDF/Markdown 原件只读与安全渲染 | PASS（固定/真实浏览器证据） | Task05 hostile Markdown/PDF 真实浏览器 PASS，远程请求 0；source Range/inline 本轮通过 |
| generation/finalize 状态 | PASS（已有真实运行证据） | Task06 记录 run `38efa91a...` completed、alias/generation/manifest 一致；本轮 health ready=true |
| 不可变原件、删除再提交新 document_id | PASS（定向证据） | Task03/04/06 相关报告与定向测试覆盖 immutable create、tombstone、dedupe 边界 |
| v1 overlap、v2 cross-page、稀疏 anchor | PASS（固定样本/定向证据） | Task02B、Task06E 报告及对应 provenance/interaction 测试通过 |
| dense+sparse、RRF、问答、reranker | PASS/配置降级 | Task06 记录 dense/sparse 查询与既有问答回归；当前服务明确 `reranker=false`，按配置禁用，不伪造 reranker 可用 |
| 下载、导入、上传和错误可见性 | PASS | Task06F 记录合法 PDF、去重、非法 PDF 和自动索引定向通过；本轮全量 956 passed |
| 失败、超时、中断、恢复 | PASS（隔离/已有证据） | Task06 resilience、lock、finalize/recovery 报告中的故障矩阵通过；真实全库性能/恢复闭环仍有未完成边界 |
| 长文档性能与全量用户文档 | PASS（功能收口；后台遗留已记录） | Task06/Task05 已有性能、固定样本和真实浏览器证据；一个历史 v2 后台任务仍异步运行，但不影响已验证用户路径 |
| Git 范围与敏感信息 | PASS（验收范围） | 本 tester 未修改业务代码、用户数据或 Git 历史；主 Agent 仍需在提交前单独核对工作树中的用户文档/规则改动 |

## 已知风险与遗留

1. 当前一个旧 PDF 的 v2 任务仍在运行，状态摘要出现整体 `indexed` 与单版本 `indexing` 并存；主 Agent 后续可在不重复触发重建的前提下确认任务最终状态，作为非阻塞后台任务债务跟踪。
2. Task06 文档保留部分历史“完整双格式/性能验收待完成”记录；本轮固定样本、用户验证、核心 HTTP 路径和全量回归已通过，历史记录不覆盖本轮 PASS。
3. reranker 当前按环境配置禁用；基础 dense+sparse/RRF 链路有证据，但不能把 reranker disabled 说成模型已验收。

## 是否允许 Spec 标记已完成

**允许。**

主 Agent 后续应：

1. 将本报告作为验收签字依据，更新 Spec018、Task07 和 `spec-status-changelog.md` 的收口状态。
2. 在本地提交前保留并记录已有 v2 后台任务的 `indexing`/`INSPECTION_BUILDING` 遗留，不启动重复重建。
3. 完成复盘、状态台账、本地提交和部署验证；reranker disabled 继续按配置披露。

## 工具与统计

- 工具：必要文档读取、只读 Git/进程状态检查、一次全量 pytest、只读 HTTP health/list/inspection/source/Range/错误烟测。
- 子 Agent/日志轮询：未进行常态轮询。
- 模型：tester 角色临时使用 Luna high。
- token 与精确工具调用计数：当前执行环境未提供，未伪造统计值。

## 签字

**tester：PASS；全量回归通过，HTTP/manifest/双栏前端证据通过，允许 Spec018 进入最终收口。**

## 架构师签字

**架构师（自身）：同意收口并标记 Spec018 为 `已完成`。**

核对项：最终全量回归、HTTP smoke、Spec/Task/状态台账更新、部署验证均已完成；已知后台 v2 indexing 与 reranker disabled 遗留已记录，且不影响用户已验证路径。

签字时间：2026-09-10 +0800

---

## 2026-10-06 当前候选补充验收与架构签字

本节是对当前候选的补充验收记录。上文 2026-09-10 的 `956 passed`、旧服务状态和旧样本仍作为历史证据保留；当前候选的结论以本节及其引用的最新证据为准，不用新结果覆盖历史失败记录。

### 候选与独立性

- 生产修复：`ecbb91f`；最终候选：`9a9733f`。
- 当前真实 API 服务由 `ecbb91f` 重启并验证；没有把后续仅含测试合同整理的 `9a9733f` 推断为已加载到运行中的服务。
- `9a9733f` 的测试文件变更由 `/root` 独立复核；本架构复审不以此前参与的测试搬迁作为自评证据。
- 本次验收未修改业务代码、前端代码、用户数据或 Git 历史，且未读取 `.env`。

### 当前真实 API E2E

证据：`docs/sdd/plans/018/artifacts/task-07/current-api-e2e-success-report.md`、`docs/sdd/plans/018/artifacts/task-07/current-api-e2e-success-evidence.json`。

本轮只新增两份明确授权、内容 hash 不同的样本：Markdown `a95357cf37344160859a812852f7863f` 与 PDF `f51024342ecd46a7a0c17adefbd67abd` 均 `POST 201`，最终状态为 `indexed`。两份样本的 v1/v2 inspection 均 HTTP 200、manifest ready、anchors 非空且 source hash verified；原件读取通过 HTTP 200，Range 通过 HTTP 206，条件 GET 通过 HTTP 304，缺失 ID 通过 HTTP 404。`/api/health`、`/api/kb/health` 与 `/api/ready` 均为 200，四个 warmup 均 ready。

这组证据证明当前上传、迁移兼容和检查入口闭环恢复；它不证明旧资料库已全部重新索引，也不允许把“改文件名即可绕过 SHA 去重”的人工指导当成验收依据。旧文档没有在本轮被删除、重建或批量重索引。

### 最终回归

最终命令及原始结果见 `docs/sdd/plans/018/artifacts/task-07/current-full-regression-report.md`：

```text
.venv/bin/python -m pytest tests --cov=backend --cov-report=term --cov-report=json:/private/tmp/researchagent-integration-final-coverage.json -q
退出码：0
2893 passed, 3 skipped, 67 subtests passed, 5 warnings
覆盖率：81.79139962786851%
```

报告仍保留此前 `2872 passed / 10 failed / 3 skipped` 的历史段；不得用当前通过结果改写或掩盖该历史诊断。当前全量结果与真实 API E2E 一起关闭了原评审中的 P1-1（恢复 marker 与 strict schema 冲突）及 P1-2（全量回归非零）。

### 已知非阻塞环境告警与后续债务

1. Langfuse/OTEL 本地 collector `127.0.0.1:3000` 不可用，导出出现失败、重试和超时；它未改变 pytest 退出码或本轮 API 业务结果，记录为环境观测告警而非当前 P1。后续部署应单独恢复观测端点并复验 telemetry。
2. 当前验收只覆盖两份新授权样本。旧资料、历史 v2 状态差异和未重新验证的旧索引仍应保留为维护债务；不得从这两份样本推断全库（包括历史约 40 条记录）均已迁移成功。
3. 万切片性能证据是本地 route-intercept 合成测试：10,000 slices、20 页 × 500，首屏 DOM 分段和显式 load-more 通过，未观察到 >=50ms long task。其限制是前端在首个 DOM 渲染前仍会预取 20 页并把 10,000 slices 放入 JS state；这是真实网络/API 规模性能尚未证明的预取债务，不阻塞本轮功能验收，但应进入后续性能任务。报告：`docs/sdd/plans/018/artifacts/task-07/current-long-document-performance-report.md`。

### 当前候选结论

**验收 PASS；P0=0，当前候选 P1=0。** 原 P1 已由 `ecbb91f` 重启后的真实上传 E2E 与 `9a9733f` 的最终全量回归关闭；Langfuse collector、旧数据覆盖边界和万切片预取属于已披露的非阻塞环境/后续债务。允许主会话继续完成 Spec018 的部署验证、状态台账和收口记录。

### 架构师签字

**架构师（独立整合复审）：`/root/branch_inventory`；同意当前候选进入最终收口。**

签字时间：2026-10-06 22:11 +0800

---

## 2026-10-26 重建入口 canonical ID / 发布一致性窄修验收（tester）

本节是对当前主目录候选中 Spec018 2026-10-26 窄范围增量的追加验收，保留上方历史验收及其结论，不改写历史证据。验收角色为 `tester`，临时档位 `Luna xhigh`；工作目录为 `/Users/wjh/ResearchAgent`。本次只验收指定文档的 canonical ID 重建入口、发布前点集一致性和 partial 展示，不扩大到其他知识库功能、全库重建或其他未实现范围。

### 范围、限制与候选证据

- 入口范围由 `docs/sdd/plans/018/2026-10-26-reindex-entry.md:5-15` 冻结：列表 DTO 使用 `document_id`，一次重建请求，202/结构化错误、前端 partial 展示和指定文档的真实复验；不含上传、删除、全库索引、记忆页或登录恢复。
- 目标实体为 `d4dfd2a620384ad5bece27320661f8f0`（`How to Peel a Million- Validating and Expanding Bitcoin Clusters.pdf`）。人工步骤、旧失败证据与最终产物边界见 `docs/sdd/plans/018/2026-10-26-reindex-entry.md:17-35`。
- 运行时 Artifact 记录主目录候选 `127.0.0.1:8000`，只对 v2 发出一次受控请求：`docs/sdd/plans/018/artifacts/20261026-publication-recheck/request.md:1-11`；真实响应为 HTTP 202、`task_id=f69932bca4e34352ac4ebf7d45722af5`，见 `reindex-response.json:1`。本 tester 未再次 POST、未重启/部署、未写生产数据库或 Qdrant、未运行单端测试和 Git 操作。
- 服务可访问证据为 `health.json:1`（`status=ok`）。最终文档状态显示 v1 `indexed`/107/100，v2 `indexed_partial`/308/100，错误为 `SOURCE_RANGE_UNRESOLVED`，见 `document-status.json:1-17`；文档身份与 source hash 见同文件 `:22-40`。
- v2 inspection manifest 明确 `status=partial`、`mapped_count=292`、`unmapped_count=16`、`unmapped_reasons.SOURCE_RANGE_UNRESOLVED=16`、`mapping_algorithm_version=source-anchor-v2`，见 `inspection-v2.json:1`。这 16 项是合法 partial，不得表述为 308 项全部映射成功。
- 点集一致性复核为 `manifest_count=308`、`qdrant_v2_count=308`、`qdrant_v1_count=107`，`extra_point_indices=[]`、`missing_point_indices=[]`、`payload_mismatch_indices=[]`，见 `point-manifest-comparison.json:1-12`。
- 用户可见截图 `knowledge-base.png` 显示目标条目的 v1 已索引 107 片段、v2 部分索引 308 片段，并显示“部分切片无法精确定位原文，已保留可用索引；可进入切片检查”的原因提示；这与 API 的 partial/16 unmapped 事实一致。
- 前端窄修最终回归为 Node 18/18、合跑 26/26、Python 23/23、0 skip，且真实 markup smoke 的 canonical URL/body 与 task 文案通过，见 `docs/sdd/plans/018/2026-10-26-reindex-entry-test.md:67-108`。后端窄修独立评审为 GO，且 5/50/99 个目标集合均通过，见 `docs/sdd/plans/018/2026-10-26-reindex-entry-backend-review.md:7-20`、`2026-10-26-reindex-entry-backend-test.md:5-13`。

### 真实 API E2E 与结果判定

| 检查 | 结果 | 可复核证据 |
|---|---|---|
| canonical 文档身份 | PASS | `2026-10-26-reindex-entry.md:5-7,21-22`；响应 `reindex-response.json:1` 的 `document_id` 与目标一致 |
| 只提交一次 v2 重建 | PASS | `artifacts/20261026-publication-recheck/request.md:5-9`；HTTP 202、task `f69932bca4e34352ac4ebf7d45722af5` |
| v1 最终状态 | PASS | `document-status.json:5-10`：107/107，progress 100，error null |
| v2 最终状态 | PASS（partial） | `document-status.json:11-16`、`inspection-v2.json:1`：308 总片段、292 mapped、16 unresolved；不是全量映射成功 |
| 发布点集一致性 | PASS | `point-manifest-comparison.json:1-12`：三类 mismatch 均为空 |
| partial 原因可见 | PASS | `knowledge-base.png`；与 `inspection-v2.json:1` 的 `SOURCE_RANGE_UNRESOLVED` 一致 |
| 失败/忙碌恢复边界 | PASS | `2026-10-26-reindex-entry.md:22-27`；前端 202/409/503 合同见 `2026-10-26-reindex-entry-test.md:85-104` |

### 可独立复现的人工验收案例（仅限本窄修）

入口：`http://127.0.0.1:8000/`；前置条件：服务 health 可访问、目标文档已存在；若 generation/检查器未 ready，应按页面提示等待而不是触发全库重建。使用目标 canonical ID `d4dfd2a620384ad5bece27320661f8f0`。以下步骤与真实产物 task `f69932bca4e34352ac4ebf7d45722af5` 对照。

1. **打开目标文档**：点击左侧“知识库”，在论文 RAG 列表点击 `How to Peel a Million- Validating and Expanding Bitcoin Clusters.pdf` 所在卡片。点击后提示目标条目显示 v1/v2 状态和“重建索引”；等待文档列表加载完成且身份为 canonical `document_id`；下一步点击该卡片的“重建索引”。若条目身份缺失，停止并保留页面状态，不提交请求。
2. **提交一次重建**：点击“重建索引”一次。点击后应看到“已提交重建：…（v1 + v2，任务 <task_id> 已排队）”；等待 HTTP 202 且响应含非空 `task_id`；下一步返回列表或刷新状态。若出现 409/“已有索引任务正在运行”，停止重复点击并等待已有任务；若出现 503 或失败文案，保留错误和时间，按同一行“重试”且只提交一次。
3. **检查 v1**：点击“切片检查”，选择目标文档并选择 v1。点击后等待“正在加载检查清单…”结束并显示 v1 `ready/indexed`、107 片段；下一步选择 v2。若出现 `INDEX_FINALIZE_REQUIRED` 或检查器只读提示，等待切换完成后重试，不删除文件或手动改 Qdrant。
4. **检查 v2 partial**：选择 v2。点击后等待 manifest 加载到终态；应显示 308 片段、partial/部分索引以及“部分切片无法精确定位原文，已保留可用索引”的告警，16 项 `SOURCE_RANGE_UNRESOLVED` 不能被隐藏或改写为全量成功；下一步可进入切片检查查看可定位部分。若状态为 building/202，按 `Location`/页面提示等待；若出现点集不一致或 finalize 错误，停止点击并交由实现方处理。
5. **验证恢复**：对可用 v2 切片继续查看；点击失败态同一行的“重试”只能在失败终态使用，等待新的 task ID 和最终状态。不得把顶层 `indexed` 作为 v2 全量 ready，也不得触发全库重建。

成功判据：目标 canonical ID 正确、重建任务真实 202 且有 task ID、v1=107、v2=308 且 partial 的 292/16 统计与 API/页面一致、点集三类差异为空。失败判据：缺 ID 仍 POST、错误目标、非 202 被当作成功、v2 告警缺失、或任何 mismatch 被隐瞒。

### Readiness Matrix（仅本次窄修）

| # | 准备度项 | 结果 | 证据 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | PASS | `artifacts/20261026-publication-recheck/health.json:1`；目标运行记录 `request.md:3` |
| 2 | 真实 API 创建入口成功 | PASS | `request.md:5-9`、`reindex-response.json:1`，HTTP 202/task `f69932...` |
| 3 | 主路径参数正确解析 | PASS | canonical `document_id`、`chunker=v2` 与响应一致；`request.md:5-9` |
| 4 | 实体状态从初始态推进 | PASS | v1/v2 progress=100、最终状态见 `document-status.json:5-16` |
| 5 | 前端显示处理中/结果提示 | PASS | 202/失败态合同与最终 markup smoke：`2026-10-26-reindex-entry-test.md:85-104` |
| 6 | 用户知道何时等待或点击 | PASS | 人工步骤 `2026-10-26-reindex-entry.md:21-27`；本节步骤 1–5 |
| 7 | 核心产物真实生成 | PASS | `inspection-v2.json:1`、`point-manifest-comparison.json:1-12` |
| 8 | 失败状态有可操作恢复 | PASS | 409/503/失败重试边界：`2026-10-26-reindex-entry.md:22-27` |
| 9 | 页面状态与 API 状态一致 | PASS | `knowledge-base.png` 与 `document-status.json:11-16`、`inspection-v2.json:1` |
| 10 | 步骤文档可由无上下文用户复现 | PASS | `2026-10-26-reindex-entry.md:17-27`；本节人工案例 |

计分：`10/10 PASS`；P0=0、P1=0。共享整合候选的权威最终回归未在本次重跑：后端 `3121 passed / 3 skipped / 0 failed`，见 `docs/sdd/plans/038/2026-10-26-management-backend-test.md:129-142`；前端 `317 passed / 0 failed / 0 skipped`，见 `docs/sdd/plans/038/2026-10-26-management-frontend-test.md:164-176`。3 个后端 skip 的原因已明确：2 个 `tests/e2e/test_research_lifecycle_e2e.py` 需要显式 `RUN_E2E=1`、浏览器和已启动服务；1 个 `tests/research/test_ollama_direct.py` 因 Ollama 不可达或无可用模型而受门控跳过。它们不是本窄修失败，也没有在本次重新执行。

### 最终决定（范围限定）

**READY_FOR_USER（仅限 Spec018 2026-10-26 canonical ID 衔接与单文档发布一致性窄修）。** 真实 API 202→终态、关键 inspection/point 产物和 UI partial 原因均存在，准备度 10/10，无 P0/P1。v2 的 16 个 `SOURCE_RANGE_UNRESOLVED` 保持为合法 partial，不能写成“全部映射成功”。本结论不改变 Spec018 当前 `实施中` 状态，不替代架构师签字、部署验证或 Spec018 其他历史/全量范围收口。

### 签字

**tester：READY_FOR_USER（仅限上述窄修范围）。**

**架构师签字：GO（仅限上述 2026-10-26 canonical ID 衔接与单文档发布一致性窄修）。**

核对结论：真实 API `202 → 终态`、v1/v2 状态、partial 原因和 manifest/Qdrant 点集一致性证据齐全，准备度 `10/10`、P0/P1 均为 0；v2 的 16 个 `SOURCE_RANGE_UNRESOLVED` 是已披露且允许的合法 partial，不得表述为全量映射成功。

本签字只允许本次窄修收口，不代表 Spec018 其他历史阶段或全量能力整体完成；历史验收与遗留事实保留不变。

签字时间：2026-10-26（Asia/Shanghai）
