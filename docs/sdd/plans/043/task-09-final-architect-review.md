# Task09 架构师最终验收预审与正式裁决

## 当前最终裁决（正式架构师签字）

**`READY_FOR_USER — GO`（2026-10-24，独立架构师最终签字）。**

第二轮完整回归已在矩阵维护后以退出码 `0` 通过：`3384 passed / 0 failed / 2 合法 skip / 67 subtests / 5 warnings`，coverage `82.37974239901867%`（82.38%）。当前候选绑定为 `HEAD=458da1b35238691cbe9447c71bf7a1afbb08728f` 加未提交工作树源指纹 `6fda3d07731f9bd820653faac22ddb9fb615fe22c393ac69e0560fe968feb059`；第二轮日志、coverage 与原临时产物 SHA 一致。QA 当前准备度为 `10/10`、P0/P1=`0/0`，真实 API/full gate、浏览器和稳定人工案例均有可追溯证据。

该 GO 只表示当前候选已具备交付用户人工验收的条件，不代替用户实际验收，也不在本报告中修改 Spec、README、Task 或状态台账。fresh 地图的来源 `partial`、18 条非空摘要与 2 个无摘要安全 skip 按合同如实保留；它们不是被伪造为全来源 complete 的结果。首轮全量失败、早期 review BLOCK/P1、旧 `a328932` 双签和失败导入 artifact 均保留为历史。

## 预审阶段结论（历史，2026-10-24）

以下结论产生于第二轮全量之前，保留以证明阻塞曾被如实记录：

**`BLOCKED — PENDING_FINAL_REGRESSION`。**

当时全量报告仍为 `3383 passed / 1 failed / 2 skipped / 67 subtests`、退出码 `1`；失败是冻结 closure matrix 中 `backend/app/knowledge_base/application.py` 的旧哈希。matrix entry/digest 随后按 Task04 维护规约更新，并由新的全量回归验证通过；该历史阻塞不应覆盖当前 GO，也不能被删除。

## 1. 预审范围与候选绑定

- Spec/Task：`043` / `09`。
- 分支：`codex/spec043-map-interaction`。
- 当前服务：`http://127.0.0.1:8000/`，部署记录中的最终修复候选 PID 为 `2252`，loopback-only；`GET /api/health=200`、`/api/ready` 为 ready。
- 页面资源：`literature-maps.js?v=18`、`literature-maps.css?v=12`、`app.js?v=60`。
- 部署记录的工作树源差异指纹：`6fda3d07731f9bd820653faac22ddb9fb615fe22c393ac69e0560fe968feb059`；这是未提交工作树候选指纹，不是新 commit SHA。
- 预审阶段只读 Spec、Task09 交接/评审/验收 Artifact 和当前状态；正式签字阶段仅修改本报告、当前验收评审和稳定人工案例页眉，没有修改业务代码、测试、Spec、服务或 Git 状态。

证据入口：

- [Task09 API E2E](task-09-api-e2e.md)
- [Task09 导入/全文 API E2E](task-09-import-api-e2e.md)
- [Task09 部署验证](task-09-deployment-verification.md)
- [Task09 最新全量回归](task-09-final-regression.md)
- [最新浏览器人工案例](task-09-runs/20261024-211542-task09-browser-full/task-09-manual-acceptance.md)
- [浏览器结构化证据](task-09-runs/20261024-211542-task09-browser-full/browser-e2e.json)

## 2. 真实 API E2E 与产物核对

### 2.1 Fresh 地图、引用层与自动摘要队列

`task-09-api-e2e.md` 的真实创建请求为当前服务上的 `POST /api/literature-maps`，HTTP `202`，主题为 `graph attention networks`、`limit=20`，得到：

- `map_id=858b78f0d9e047efa6d8d1559d83a6de`；create job 为 `f98611b16e23478d94a3035add7e6861`。
- 图谱落盘 20 节点、11 条关系；地图最终为 `status=partial`，原因是 references/similarity provider 的 `SEMANTIC_SCHOLAR_RATE_LIMITED`。
- 自动摘要队列为同图持久队列 `a73b6881b56a41a78fc8d48abbc30f54`，最终 `total=20、completed=18、queued=0、running=0、failed=0、skipped=2`。
- 两个无摘要节点明确以 `MAP_ABSTRACT_UNAVAILABLE` 安全跳过；没有用标题冒充摘要，也没有把队列 `completed` 改写成地图完整成功。
- pause/resume、同键 ensure 重放、单地图串行、手动 regeneration 版本化和旧图 GET 无副作用均有真实状态轨迹。唯一 `version=2` 已由浏览器证据归因为用户主动的 manual regeneration，不是 ensure 重复。

该 `partial` 是 Spec 允许且必须如实呈现的来源结果，不是本次收口的 P1；最终报告仍必须同时保留 `map.status=partial` 与 `queue.status=completed` 两个不同状态。

### 2.2 真实导入与全文 source gate

`task-09-import-api-e2e.md` 保留了原失败 run 和最终新 run，且没有以旧 artifact 覆盖失败事实：

- 原失败 `20261024-160056-task09-import-api`：一次导入 POST 返回 HTTP `202`、业务 `failed`，持久化 `ARXIV_IDENTITY_CONFLICT + SEMANTIC_SCHOLAR_RATE_LIMITED`，`retryable=true`、无 PDF/document；这证明失败诊断与身份未改写。
- 最终导入 `20261024-204558-task09-import-api-final`：同一节点只发一次 `POST /imports`，HTTP `202`，`status=indexed`、`download_status=indexed`，生成 `document_id=ae3a1c3f7ee746bba031b06306ff3230`；后置 GET 的诊断已清除，外部身份和 source URL 未改变。
- 真实 PDF 产物为 `data/kb/papers/2018-Conference-Exploring-Visual-Relationship-for-Image-Captioning.pdf`，`3088287` bytes，SHA-256 `d923185e9e7a8887b2a10f7f6f9041cd7182fb63a6cd6b603aefc78d07394644`；v1 index 为 66 chunks、100%。
- `20261024-210815-task09-full-analysis-v1` 只执行一次既有 v1 reindex，随后 source gate 变为 `fulltext_ready=true`；canonical/indexed/manifest/原件四处 SHA-256 一致，manifest 为 `ready`、100%、`source_hash_state=verified`。
- 唯一 full analysis 为 `analysis_id=04ff00a37f8247379878ecaf7fc6703e`、`job_id=ca2e1852b8cc49cab80300c84347c89c`，状态 `queued → running → completed`；结果非空 592 字符、5 条 citation records，所有引用绑定目标 document。

浏览器页面显示“受控来源引用：6 条”，API artifact 记录 5 条 citation records；两者分别是 UI 受控片段计数和 API citation record 计数，最新人工案例已明确保留两个真实值，不能强行合并为同一计数。

## 3. 人工验收案例可操作性预审

`20261024-211542-task09-browser-full/task-09-manual-acceptance.md` 已提供入口、资源版本、前置条件、实体 ID、产物路径和步骤 0–7。逐步核对结果如下：

| 项目 | 预审结论 | 证据 |
|---|---|---|
| 入口、端口、资源版本 | PASS | `http://127.0.0.1:8000/#literature-maps-view`、v18/v12/v60、health 200 |
| 每步包含点击/输入、点击后提示、等待条件、等待中显示、下一步、失败恢复 | PASS | 步骤 0–7 每步均具备六项字段；未用固定睡眠替代终态条件 |
| Fresh 队列可观察性 | PASS | 20 节点、11 关系；`18/20 completed + 2 skipped`；pause/resume/retry 文案与 API 一致 |
| 全文成功态可复现 | PASS | map/node/document/analysis ID、source version、manifest 和截图均有路径 |
| 失败恢复不误导 | PASS | 失败地图保留 `retryable`、人工重试入口；不自动下载、导入或发消息 |
| 草稿不覆盖、不发送 | PASS | 真实 conversation ID、无 `/messages`/SSE；已有草稿保留，空草稿可编辑预填 |
| 产物查看路径 | PASS | `browser-e2e.json`、截图、导入 evidence、full-analysis evidence、PDF 路径均存在 |

一个需要在最终验收文档中保持清楚的口径：API 原始 resolver code 为 `ARXIV_IDENTITY_CONFLICT`，v18 UI 诊断投影为安全文案/归一化 code `ARXIV_MATCH_UNCERTAIN`。这是原始错误码到用户显示码的投影，不应在最终报告中写成两个独立 provider 失败；应同时给出 raw code 与 UI projection 的对应关系。

人工案例当前主要复现已有真实地图卡片，完整“新建地图”请求由 API E2E Artifact 证明；若最终交付文档要让用户从空库完整照做，root 需补一段真实“新建地图”按钮路径，或明确该案例是“当前候选既有产物复核”而非从空库创建案例。该项不改变当前 API E2E 事实，但需在最终验收报告中避免把两种入口混写。

## 4. P0/P1 与评审范围核对

### 4.1 当前未发现可复现的未解决 P0/P1

- backend-review 最新独立窄复审已对 executor 隔离、live lease reaper、attempt cap/late finish、Timer shutdown 和 final-finish/shutdown barrier 给出 GO；arXiv 指定 ID 作者缩写和 KB canonical import 接缝也分别给出 GO。
- frontend-review 最新阶段对 P1-03（full-ready 误显示不可用文案）、P1-04（首次完成后立即 regenerate 丢旧结果）、标签重复后缀、JSv18 可读性/导出边界和 KB202 诊断投影给出各自范围内 GO。
- 上述 GO 都明确是窄范围复审，不能单独替代最终全量或 Task09 验收签字；早期 BLOCK/P1 历史必须保留，不能删除或改写。
- 当前唯一已记录的硬阻塞是全量回归尚未通过，而不是新的业务 P1：原失败 nodeid 为 `tests/kb/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered`。

### 4.2 覆盖与范围限制需如实保留

前端 reviewer 的最终窄段仍注明 queue-race/auth 浏览器专项及 200 节点锚点/尺寸专项的历史覆盖限制；前端 tester 后续记录八文件集合 `60 passed`，v18 窄集合 `12 passed`，全量回归应作为最终候选的总门禁。最终验收报告可以引用这些精确证据，但不能把窄复审标题扩写成“所有真实来源/所有故障注入均已覆盖”。

## 5. DoD 与数据一致性预审

### 5.1 已满足或已有证据

- Spec 当前仍为“实施中”，Task09 状态仍为“进行中”；这与本轮尚未完成最终回归和签字相符。
- 需求/技术评审、Task09 接口合同、前后端分端实现、独立 review、定向 tester、真实 API、部署和浏览器 artifact 均有落盘路径。
- 当前 matrix 已读回为：`backend/app/knowledge_base/application.py` SHA-256=`222bece39de4bd36aa0b033e96995292263fdc11e15557d48ba39b0af896a244`，`inventory_digest=38af1e9c3ea0eebd2315485e6ccfc2141ef8ea0c09f386b125d8f7bb1cb378e0`。backend report 记录 matrix 维护后目标测试 `2 passed`，没有改断言、entry 名单或安全门禁。
- 所有当前人工案例和 API 产物引用的文件已存在；没有使用旧 artifact 冒充当前 ready。

### 5.2 预审时待补齐事项的当前回填

1. `task-09-final-regression.md` 已追加 matrix 维护后的当前章节：完整 `tests` 退出 0、`3384/0/2/67/5`，coverage `82.38%`；首轮 `exit 1` 与原始日志仍保留，不能被覆盖。
2. `docs/sdd/reviews/043-acceptance-review.md` 已追加当前 Task09 tester `READY_FOR_USER` 段并完成本架构师独立 `READY_FOR_USER / GO` 签字；旧 `a328932` 验收段继续作为历史，不替代当前候选绑定。
3. `docs/sdd/plans/043/README.md` 顶部旧候选已明确标为历史；其当前 Task09“实施中/进行中”文字仍待 root 在 Spec 状态台账统一收口时同步更新，不能与最终状态长期并存。
4. Spec 第 190 行继续引用同一 `043-acceptance-review.md`，该文件当前内容已绑定 Task09 候选；root 仍需在状态变更时同步 `spec-status-changelog.md`，保持引用路径和结论一致。
5. 新全量、验收评审签字、复盘与关键产物现已满足；只有 root 按完整 DoD 完成 Spec/README/Task09/台账状态同步和机械校验后，才可把 Spec 状态改为“已完成”。

## 6. Readiness Matrix（当前预审，不是最终签字）

| # | 准备度项 | 当前预审 | 依据/限制 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | PASS | deployment verification；health/ready 200 |
| 2 | 真实 API 创建入口成功 | PASS | fresh map create 202，`858b…`，真实 graph/queue 终态 |
| 3 | 主路径参数正确解析 | PASS | 真实主题、limit=20、节点详情和全文 source gate 均可读 |
| 4 | 实体状态从初始态推进 | PASS | `generating → partial/finished`，queue pause/resume/completed，full analysis completed |
| 5 | 前端显示处理中提示 | PASS | 暂停/运行/完成、全文未就绪与全文完成文案均有浏览器证据 |
| 6 | 用户知道何时等待或点击 | PASS | 队列控制、重试入口、全文 source gate、手动分析提示均有具体文案 |
| 7 | 核心产物真实生成 | PASS（partial 如实保留） | 图谱、18 条摘要和合法 v1/full analysis 真实存在；2 个无摘要节点不伪造结果 |
| 8 | 失败状态有可操作恢复 | PASS | retryable 导入诊断、人工重试、旧摘要保留、全文 gate 恢复路径 |
| 9 | 页面状态与 API 状态一致 | PASS | map partial 与 queue completed 分开；source version、document、analysis 与页面一致 |
| 10 | 无上下文用户可复现步骤 | PASS（当前产物复核范围） | 最新 manual case 步骤 0–7（共八步）字段齐全；若要求空库创建，需补 UI 新建段 |

功能运行时准备度为 `10/10`，且第二轮最终全量、关键产物、P0/P1 和 tester/architect 正式签字均已满足；因此本次正式裁决为 `READY_FOR_USER`。这仍不表示用户已经执行人工验收。

## 7. Root 最终收口事项（不由本次架构师签字代行）

1. 已完成：matrix 最小维护、第二轮全量归档与 SHA 核对、当前候选 tester 验收段和本架构师签字、稳定人工案例页眉同步。
2. 已完成：复盘已落盘；首轮失败、早期 BLOCK/P1、provider `partial`、无摘要 skip 和旧候选签字均保留。
3. 待 root 统一执行：按项目流程同步 Spec、README、Task09、`spec-status-changelog.md` 的最终状态，并完成收口前机械校验；本次签字不代行这些状态变更。
4. 若服务继续运行，最终回复应提示用户入口 `http://127.0.0.1:8000/#literature-maps-view`、实际端口 `8000` 和启动命令 `HOST=127.0.0.1 PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`。

## Final Decision

**`READY_FOR_USER — GO`。**

当前候选可以交付用户人工验收。交付口径必须继续区分：地图来源 `partial` 与摘要队列 `completed`；2 个无摘要安全 skip 与最终回归的 2 个生命周期合法 skip；API 的 5 条 citation records 与 UI 的 6 条受控片段计数；以及历史失败和当前成功。Spec 的最终“已完成”状态由 root 按完整 DoD 另行统一回填，本次不修改。
