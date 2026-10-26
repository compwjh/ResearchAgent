# 2026-10-26 管理复接与相邻恢复工作复盘

> 本文只记录 2026-10-26 已发生的证据、边界和交接教训，不新增长期规则，不改变 AGENTS.md，不把任何未完成 Spec 标记为完成。

## 1. Spec018：canonical ID 与索引尾点必须分开看

- 重建入口的真实文档 DTO 使用 canonical `document_id`；旧前端仍读取 `paper_id` 时，会把请求发到错误目标或把结构化错误显示成重复的“重建失败”。窄修复优先使用 `document_id`，仅保留必要的旧 DTO 回退；空 ID 不提交请求。
- 独立复审还抓到两个高风险 P1：成功响应缺少非空 `task_id` 也可能被当成排队成功，以及列表重绘后按钮级 in-flight 锁可被替代按钮绕过。修复后以 HTTP 202 + 非空 `task_id` 为成功门槛，并按 canonical 文档 ID 持有模块级锁；这两项有独立合同测试与 GO 复审记录。
- 单文档真实诊断显示 v2 manifest 为 297 个 chunk（`0..296`），同一文档的 Qdrant v2 point 仍有 308 个（`0..307`），多出的 `297..307` 是 11 个旧尾点。另有 20 个图表/表格碎片无法唯一定位，属于 `SOURCE_RANGE_UNRESOLVED` 的合法 partial，不能用模糊匹配伪造成完整来源。
- 因此“manifest 297”与“索引实际 308”是发布一致性缺陷，不是 20 个 unresolved 项的来源算法缺陷。删除旧点失败吞掉、发布前不核对目标文档+chunker 的实际 point 集合，是本次必须由 fail-closed 接缝修复覆盖的边界；本复盘不把隔离缩容探针当成真实生产重建成功。

证据：[`2026-10-26-reindex-entry-frontend.md`](../plans/018/2026-10-26-reindex-entry-frontend.md)、[`2026-10-26-reindex-entry-review.md`](../plans/018/2026-10-26-reindex-entry-review.md)、[`2026-10-26-reindex-entry-range-diagnosis.md`](../plans/018/2026-10-26-reindex-entry-range-diagnosis.md)、[`2026-10-26-reindex-entry-backend-test.md`](../plans/018/2026-10-26-reindex-entry-backend-test.md)。

## 2. Spec032：search TTL 与 browser session TTL 不是同一个生命周期

- 登录恢复窄修复的事实是：搜索会话过期后，如果已有导入条目的 durable snapshot 完整、hash 和 candidate/search 身份校验通过，登录入口可以继续从服务端快照恢复受控 ACM/IEEE URL；这不是延长 live-search TTL，也不是重新检索。
- browser session TTL 仍是临时 page/context/profile lock 的生命周期，过期后照常回收并 fail-closed；批次和 item 的 `waiting_login` 持久状态不因此删除或取消。再次点击登录时复用既有 persistent profile。
- Task11 的精确候选测试与静态评审通过，managed worktree 中一个既有 storage-lock 节点曾受默认目录不可写阻塞，不能改写成产品失败或候选通过。Spec032 原整体仍处于暂停/未收口状态；本窄修复不代表 Spec032 完成。

证据：[`2026-10-26-login-recovery-plan.md`](../plans/032/2026-10-26-login-recovery-plan.md)、[`2026-10-26-login-recovery-test.md`](../plans/032/2026-10-26-login-recovery-test.md)、[`2026-10-26-login-recovery-review.md`](../plans/032/2026-10-26-login-recovery-review.md)。

## 3. Spec038：退役 API 与 pending 真写闭环

- 旧 `/api/memories*` 是退役端点；`GET /api/memories?scope=global&status=active` 的 404 是真实路由事实，不是 SPA 兜底。复接方案没有恢复旧 `MemoryRecord`/evidence CRUD，也没有把 404 伪装成空列表。
- 当前页面使用固定文档 GET/PUT，真相源是 `MEMORY.md`、`projects/<project_id>.md`；页面不再假装提供旧式逐条 status/evidence/undo 行操作。项目写入只使用专用 active 项目 `a4a1745f801441188dc1f75b0534be11`，未修改全局用户记忆。
- pending 闭环使用分析项的稳定 `item_id`。真实自然语言案例的 conversation 为 `6a59bd0707d54761a6cd3a5a68e88ecf`，user message 为 `a0c88d0bbf7043b88459c07864d9a264`，analysis 为 `a3d8ad2a46a1406cb020db450954834e`；分析最终 `status=completed`、`saved_count=1`、`pending_count=0`，项目文件独立 GET 确认含“本项目的验收代号是蓝色松果”。这证明的是文件真实写入与 pending 消费，不是 `memory_id` 旧字段恢复。
- 自然语言请求的 SSE capture `events` 为空，原因是解析未命中；因此它不能被当作原始事件序列。最终状态以独立真实 GET 和落盘文件确认作为证据，不能补造不存在的 SSE event。

证据：[`2026-10-26-management-contract.md`](../plans/038/2026-10-26-management-contract.md)、[`2026-10-26-management-runtime.md`](../plans/038/2026-10-26-management-runtime.md)、[`natural-memory-analysis.json`](../plans/038/artifacts/20261026-file-management/natural-memory-analysis.json)、[`natural-memory-file-confirmation.json`](../plans/038/artifacts/20261026-file-management/natural-memory-file-confirmation.json)。

## 4. 独立复审抓到的 P1 与关闭方式

- Spec038 前端首轮独立复审抓到 P1：项目列表异步刷新后，用户可见选择与 `memoryState.projectId` 可能脱节，保存可能写入错误项目。修复后使用 canonical memory state、失效项目清空并禁用保存，GET/PUT 迟到响应增加 generation/key 守卫；最终窄复审为 GO，P1=0。
- 相邻的 Spec018 重建入口复审抓到的 P1（缺 `task_id` 的伪成功、重绘后重复提交）也说明：静态“调用存在”不能替代成功响应门禁和异步状态验证。该两项已由真实 app.js 合同测试覆盖并 GO，但仍需把真实生产 API 验收与静态合同分开记录。

这些 P1 是独立 reviewer 在实现后发现的范围内缺陷；修复没有扩大 Spec038 的数据模型或恢复退役 API。

## 5. 全量 inventory 与 synthetic 性能测量窗

- 后端第一次 Spec038 收口全量（排除 `tests/frontend`）为 `3120 passed, 3 skipped, 1 failed, 67 subtests passed`。唯一失败是 `tests/kb/test_kb_upload_closure_matrix.py` 的冻结 inventory hash：`routes_paper.py` 存在已授权的 durable snapshot 三行变更，但清单仍要求旧 SHA-256。该失败是 inventory/基线同步问题，不是 memory 管理断言失败。
- inventory 最小更新经独立复审 GO 后，完全相同的隔离命令最终为 `3121 passed, 0 failed, 3 skipped, 67 subtests passed`；3 个 skip 有明确环境门控。首轮失败与最终通过数字均保留，不能用最终数字抹去基线漂移过程。
- 前端完整回归首轮为 `315 passed, 1 failed, 0 skipped`。唯一失败是 synthetic 地图 fixture 的 `longTaskCount=3`；其 observer 从页面初始化/布局直到最终快照持续累积，测量窗包含交互前生命周期。单用例精确重放通过，随后 fixture 在最终交互窗口前清理前阶段 observation，保留 `longTaskCount == 0` 门槛；最终完整回归为 `317 passed, 0 failed, 0 skipped, 59.01s`。这属于 Spec043 synthetic 测量窗问题，不应归因于 Spec038 memory editor。

## 6. 精确测试与真实 E2E 的差异

| 证据层 | 本次实际结果 | 能证明什么 | 不能替代什么 |
|---|---|---|---|
| 后端精确 pytest / 隔离 HTTP smoke | 最终全量 `3121/3121`，3 skip；管理定向集合 `104/104` | store/API 合同、OCC、路径/owner/active 校验、pending 故障边界 | 不替代部署后的真实页面与跨端人工验收 |
| 前端静态/Node 合同 | Node `33/33`；最终 `tests/frontend` `317/0/0` | DOM、XSS、资源版本、异步守卫和 synthetic fixture | 不替代真实 memory GET/PUT、真实文件 bytes/hash 或人工操作 |
| 真实项目 API trace | `api-e2e.json`：GET → PUT → GET → stale PUT 409 → 最新版本 GET | 项目文件读写、revision 冲突和不覆盖 | 原始 trace 第 5 步没有合并 PUT，不能声称它包含合并请求 |
| 真实两页面浏览器案例 | 页面 B 先保存并发版本，页面 A 触发 409、保留草稿、人工合并后保存；最终 runtime/status 与截图落盘 | 页面行为、提示、草稿保护和最终合并结果 | 不能把截图或 runtime 倒写成 `api-e2e.json` 的原始事件 |
| 自然语言项目案例 | 消息/分析 completed，`saved_count=1`，独立 GET 文件含“蓝色松果” | 产品主路径的真实 pending 消费与文件落盘 | SSE `events=[]` 不能提供原始事件证据 |

人工复现步骤已收敛到两个真实页面同时编辑同一专用项目：页面 A 保留旧 revision 草稿，页面 B 先保存服务器版本，A 再保存触发 409；等待文案、恢复按钮、人工合并和最终重读均记录在 [`2026-10-26-management-runtime.md`](../plans/038/2026-10-26-management-runtime.md)。本段保留验收签字落盘前的历史交接状态；随后独立验收报告已签字 `GO`，当前管理复接补充完成，见 [`038-acceptance-review.md`](../reviews/038-acceptance-review.md)。

## 7. 最终真实回归与后台托管边界

- 最终后端全量为 `3121 passed, 0 failed, 3 skipped, 67 subtests passed`；最终前端全量为 `317 passed, 0 failed, 0 skipped, 59.01s`，Node 合同 `33/33`。Spec043 synthetic 性能 fixture 的独立测量窗修复已由其独立 review 判定 GO；本次只记录该最终回归结果，不改 Spec043 原状态。
- 管理复接运行版本为 `app.js?v=65`、`styles.css?v=65`、`literature-maps.js?v=21`、`literature-maps.css?v=13`；后台由当前 macOS 登录会话的 `launchctl submit` 标签 `com.researchagent.recovery8000` 托管，地址 `http://127.0.0.1:8000`。`/api/health`、`/api/kb/health` 与专用项目文件 GET 均有独立 JSON 证据，见 `final-background-health.json`、`final-background-kb-health.json`、`final-background-project.json`。
- 先前普通 `start.sh -d` 返回 PID 但进程随后被执行环境清理，属于重复 PID/假启动现象，不算部署成功；旧失败与后续 launchctl 托管成功证据同时保留。未安装 plist、未形成开机自启，也未改变 Ollama 部署。启动/停止命令已由 root 统一记录在 [`deploy/README.md`](../../deploy/README.md)，本复盘不重复建立独立部署规则。
- 该托管复核只证明当前登录会话下的运行时可访问与依赖健康，不改变 Spec032 整体暂停、不把认证后 resume/download/import 写成已验证，也不扩大 Spec038 管理复接补充的完成范围。

## 8. 同范围 P2 复开：落盘截图必须实际目视核验

- `#memory-view` scoped `[hidden]` 修复后，独立 review 为 `GO`，最终前端完整回归为 `318 passed, 0 failed, 0 skipped, 58.17s`；后端保持 `3121 passed, 0 failed, 3 skipped, 67 subtests passed`。页面资源为 `app.js?v=66`、`styles.css?v=66`、地图 21/13，旧版 65/21/13 及旧错误截图均保留。
- root 的真实 CUA 复核明确记录初始隐藏状态为 `none`、409 冲突区域为 `grid`、保存后恢复为 `none`；最终 revision 为 `e96ff2a825ed22acda7cd18eb35560bb575bd3c101c87866edf456d36f71cf51`，文件仍保留“蓝色松果”和此前 demo 内容。证据为 [`hidden-before-fix.json`](../plans/038/artifacts/20261026-file-management/hidden-before-fix.json)、[`hidden-recheck.json`](../plans/038/artifacts/20261026-file-management/hidden-recheck.json)、[`hidden-recheck-final-document.json`](../plans/038/artifacts/20261026-file-management/hidden-recheck-final-document.json) 与 [`recovery-saved-hidden-fixed.png`](../plans/038/artifacts/20261026-file-management/recovery-saved-hidden-fixed.png)。
- 这次复开再次说明：JSON、DOM 状态或最终 revision 只能证明结构化状态，不能证明用户实际看到的 CSS 展开/隐藏结果；落盘截图可能保留旧红框、遮罩或 stale UI 状态，必须实际打开并目视检查，才能确认截图与当前页面结果一致。旧的错误截图 [`recovery-saved.png`](../plans/038/artifacts/20261026-file-management/recovery-saved.png) 因此保留为历史基线，不能拿它替代无红框的新截图。
- QA 正在补本轮最终验收；本节只记录同范围复开证据，不把本轮再次写成新的 Spec/状态台账完成变更。
