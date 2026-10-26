# Spec038 管理复接真实运行时人工验收交接

## 状态与范围

**当前状态：管理复接补充已完成（2026-10-26；tester READY_FOR_USER、architect GO）。** 本报告记录已落盘的隔离项目 API/UI 运行时案例；不将 pending-confirm 人工保存/忽略或 Spec038 历史其它潜在工作写成已执行。测试不使用全局 `MEMORY.md`、用户既有项目记忆或其他真实私人记忆作为写入目标。

- 服务地址：[`http://127.0.0.1:8000`](http://127.0.0.1:8000)
- 专用项目：`文件记忆验收 20261026`
- `project_id`：`a4a1745f801441188dc1f75b0534be11`
- 项目状态：`active`；owner：`local-user`
- 最终页面资源（同范围 P2 复开后）：`app.js?v=66`、`styles.css?v=66`、`literature-maps.js?v=21`、`literature-maps.css?v=13`；旧版 65/21/13 证据保留。

## 可复现人工案例

### 1. 进入专用项目文档

1. 打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。
2. 点击左侧“记忆治理”。等待页面出现“全局与项目记忆”编辑器；不要先编辑“系统规则”，它仍是独立的 `USER.md` 入口。
3. 在“作用域”下拉框选择“项目记忆”。等待“项目”下拉框加载 active 项目。
4. 在“项目”下拉框选择“文件记忆验收 20261026”，核对目标为 `a4a1745f801441188dc1f75b0534be11`。不要选择“全局记忆”，不要把测试内容写入其他项目。
5. 等待状态从“正在读取记忆文档…”变为“已加载 projects/<project_id>.md”或“文档为空，可开始编辑”。只有文档已读取、revision 已出现后，才继续编辑。

### 2. 保存并重读项目记忆

1. 在“文档内容”文本框输入带换行和 Emoji 的专用验收草稿，例如“浏览器保存验证。\n保留换行与 Emoji 😊。\n”。
2. 点击“保存文档”。等待按钮显示“保存中…”，然后等待状态显示“文档已保存（revision …）”。
3. 点击“重新读取”。等待“正在读取记忆文档…”结束，确认文本框内容与刚保存的原文一致、revision 已更新。
4. 如果出现“请先选择一个 active 项目”或项目选择变化提示，停止保存，重新选择上述专用项目并等待 GET 完成；不要通过切换到全局作用域绕过提示。

### 3. 制造 409 冲突并保留草稿

1. 在第一个真实页面（页面 A）的文本框末尾追加本地草稿，例如“冲突恢复新版本。\n”，保持页面 A 不刷新、不重新读取。
2. 打开第二个真实页面（页面 B，可用新标签页或新窗口），进入同一个服务地址，点击“记忆治理”，选择“项目记忆”及同一个专用项目 `a4a1745f801441188dc1f75b0534be11`；等待页面 B 读完同一 revision。两个页面必须都是真实 UI 页面，且目标项目相同。
3. 在页面 B 的文本框末尾追加服务器并发内容，例如“服务器并发版本。\n”，点击“保存文档”，等待“文档已保存（revision …）”。这一步只写专用项目，不触碰全局文件；请求/响应证据见 [`browser-conflict-server-write.json`](artifacts/20261026-file-management/browser-conflict-server-write.json)。
4. 回到页面 A 点击“保存文档”。等待状态显示“服务器已有新版本，请查看冲突副本并人工合并后重试”，并等待冲突区域出现“服务器已有新版本”。
5. 核对页面 A 文本框中的本地草稿仍在；冲突副本单独显示页面 B 已保存的服务器内容，不能用服务器副本自动覆盖文本框。若草稿消失，立即停止并记录失败，不继续保存。

### 4. 使用冲突恢复按钮并合并保存

1. 在页面 A 的冲突区域点击“读取最新版本并保留草稿”。等待按钮操作完成：先看到“正在读取最新版本（草稿保留）…”，再看到“已读取最新版本；草稿仍保留，请对照合并后再保存”。
2. 对照页面 A 的独立服务器副本，把需要保留的页面 B 新版本与页面 A 文本框草稿人工合并；不要把服务器副本整段覆盖草稿，也不要修改全局记忆。
3. 点击“保存文档”。等待“保存中…”结束并显示“文档已保存（revision …）”。
4. 点击“重新读取”，等待 GET 完成，核对最终文本包含合并后的内容，且 revision 与最新保存响应一致。
5. 最终浏览器记录显示 `browser_status=文档已保存`；最终内容与 revision 见 [`final-runtime.json`](artifacts/20261026-file-management/final-runtime.json)，P2 复开后的恢复截图见 [`recovery-saved-hidden-fixed.png`](artifacts/20261026-file-management/recovery-saved-hidden-fixed.png)。此前截图 [`recovery-saved.png`](artifacts/20261026-file-management/recovery-saved.png) 作为错误红框历史证据保留，不覆盖。

## 真实 API 顺序证据

`api-e2e.json` 已落盘以下实体和状态序列：

| 顺序 | 操作 | 结果 | 关键事实 |
|---:|---|---:|---|
| 1 | project GET | `200` | 初始空内容及空内容 SHA-256 revision |
| 2 | project PUT | `200` | 保存换行与 Emoji 原文，返回新 revision |
| 3 | project GET | `200` | 重读内容与 revision 与保存结果一致 |
| 4 | stale revision PUT | `409` | `MEMORY_DOCUMENT_CONFLICT`，返回当前副本；不覆盖已保存内容 |
| 5 | 最新版本 GET | `200` | stale 冲突后读取当前副本；`api-e2e.json` 原始 trace 在此结束 |

API 原始请求、响应、project ID 和 revision 见 [`api-e2e.json`](artifacts/20261026-file-management/api-e2e.json)。该文件不包含后续合并 PUT；合并 PUT 成功由最终浏览器 runtime、恢复截图、第二页面的冲突恢复写入证据共同证明，最终内容与 revision 见 [`final-runtime.json`](artifacts/20261026-file-management/final-runtime.json) 和 [`browser-conflict-recovery-server-write.json`](artifacts/20261026-file-management/browser-conflict-recovery-server-write.json)。最终 runtime 标记 `existing_user_memory_modified=false`，说明本案例没有修改现有全局用户记忆。

## 当前验证进度与未完成边界

- 后端全量回归最终为 `3121 passed, 0 failed, 3 skipped, 67 subtests passed`；3 个 skip 有明确环境门控。后端定向管理门禁与全量候选均已通过；本行仅记录测试证据，不以数字替代签字，最终验收签字见 [`038-acceptance-review.md`](../../reviews/038-acceptance-review.md)。
- 前端完整回归最终为 `317 passed, 0 failed, 0 skipped`，耗时 `59.01s`；Node 合同测试为 `33/33`。此前 `315 passed, 1 failed` 的唯一失败是 synthetic 地图性能项，已在独立复审确认测量窗修复后重新完整通过。前端精确测试与本报告的真实 runtime 证据仍分开记录。
- 同范围 P2 复开后的最终候选再次完整回归为 `318 passed, 0 failed, 0 skipped, 58.17s`；后端未变，仍为 `3121 passed, 0 failed, 3 skipped, 67 subtests passed`。本轮修复是 `#memory-view` scoped `[hidden]` 防止 CSS `display` 覆盖；候选 commit `87b0a88b` 为作者产出、未对外推送。页面资源为 `app.js?v=66`、`styles.css?v=66`、地图 21/13。
- root 的真实 CUA 复核记录为：初始状态 `none`，409 冲突网格为 `grid`，保存后回到 `none`；最终 revision 为 `e96ff2a825ed22acda7cd18eb35560bb575bd3c101c87866edf456d36f71cf51`，保留“蓝色松果”和此前 demo 内容。新证据见 [`hidden-before-fix.json`](artifacts/20261026-file-management/hidden-before-fix.json)、[`hidden-recheck.json`](artifacts/20261026-file-management/hidden-recheck.json)、[`hidden-recheck-final-document.json`](artifacts/20261026-file-management/hidden-recheck-final-document.json) 与 [`recovery-saved-hidden-fixed.png`](artifacts/20261026-file-management/recovery-saved-hidden-fixed.png)。
- 自然语言项目记忆案例已完成：conversation `6a59bd0707d54761a6cd3a5a68e88ecf`、user message `a0c88d0bbf7043b88459c07864d9a264`、analysis `a3d8ad2a46a1406cb020db450954834e`；分析结果 `status=completed`、`saved_count=1`、`pending_count=0`，项目文件独立 GET 确认含“蓝色松果”。`natural-language-memory.json` 的 SSE `events` 为空（解析未命中），不作为原始事件证据；最终文件确认见 [`natural-memory-file-confirmation.json`](artifacts/20261026-file-management/natural-memory-file-confirmation.json)。
- 独立验收报告已落盘并由架构师对管理复接补充签字 GO；本报告不把历史 P1/P2/P3 之外的潜在工作或 pending-confirm 人工流程标记为完成。
- QA 正在补本轮最终验收；本次只更新运行时候选与证据，不新增或改写 Spec/状态台账完成记录，等待 root 收到本轮 architect 结论后统一处理。

## 产物索引

- API E2E：[`api-e2e.json`](artifacts/20261026-file-management/api-e2e.json)
- 项目实体：[`project.json`](artifacts/20261026-file-management/project.json)
- 外部服务器写入：[`browser-conflict-server-write.json`](artifacts/20261026-file-management/browser-conflict-server-write.json)
- 冲突恢复后的服务器写入：[`browser-conflict-recovery-server-write.json`](artifacts/20261026-file-management/browser-conflict-recovery-server-write.json)
- 最终浏览器/runtime：[`final-runtime.json`](artifacts/20261026-file-management/final-runtime.json)
- 冲突草稿截图：[`conflict-draft.png`](artifacts/20261026-file-management/conflict-draft.png)
- 恢复保存截图：[`recovery-saved.png`](artifacts/20261026-file-management/recovery-saved.png)
- P2 复开隐藏状态修复前证据：[`hidden-before-fix.json`](artifacts/20261026-file-management/hidden-before-fix.json)
- P2 复开隐藏状态复核：[`hidden-recheck.json`](artifacts/20261026-file-management/hidden-recheck.json)、[`hidden-recheck-final-document.json`](artifacts/20261026-file-management/hidden-recheck-final-document.json)
- P2 复开最终恢复截图（实际无红框）：[`recovery-saved-hidden-fixed.png`](artifacts/20261026-file-management/recovery-saved-hidden-fixed.png)
- 健康检查：[`health.json`](artifacts/20261026-file-management/health.json)
- 自然语言请求/会话/消息/分析/文件确认：[`natural-language-memory.json`](artifacts/20261026-file-management/natural-language-memory.json)、[`natural-memory-conversations.json`](artifacts/20261026-file-management/natural-memory-conversations.json)、[`natural-memory-messages.json`](artifacts/20261026-file-management/natural-memory-messages.json)、[`natural-memory-analysis.json`](artifacts/20261026-file-management/natural-memory-analysis.json)、[`natural-memory-file-confirmation.json`](artifacts/20261026-file-management/natural-memory-file-confirmation.json)


## 最终后台部署复核（2026-10-26）

前台终端服务在会话中断后退出；普通 `start.sh -d` 虽返回 PID，但进程随后被执行环境清理，故该次启动不算部署成功。随后使用当前 macOS 登录会话的 `launchctl submit` 托管既有启动脚本，标签 `com.researchagent.recovery8000`；未安装开机启动配置，仍为 `HOST=127.0.0.1 PORT=8000 RERANKER_ENABLED=false`，未改变 Ollama 的局域网部署。

最终真实 GET 复核：`/api/health` 成功，`/api/kb/health` 的 Qdrant 与 embedding 均为 true，专用项目文件读取成功且保留“蓝色松果”。当前 macOS 登录会话托管标签为 `com.researchagent.recovery8000`，地址为 `http://127.0.0.1:8000`，P2 复开后的页面源码资源为 `app.js?v=66`、`styles.css?v=66`、地图 21/13；旧版 65/21/13 运行证据保留。证据：`final-background-health.json`、`final-background-kb-health.json`、`final-background-project.json`。实际托管启动/停止命令见 `deploy/README.md` 当前登录会话章节；普通 `start.sh -d` 返回 PID 后被执行环境清理的重复 PID/假启动事实已保留，不作为部署成功。旧的启动失败与早先成功运行证据均保留，未用新结果覆盖旧证据。

## 最终 P2 收口绑定（2026-10-26 23:27，北京时间）

可见性修复候选为 `87b0a88b`，当前 app/styles 为 66，地图为 21/13；完整前端回归 318 passed、0 failed、0 skipped。`038-acceptance-review.md` §7 的 tester 与 architect 补签均已通过，本次管理复接补充已完成。此前“待补签”仅为历史阶段记录；旧错误截图保留，当前正确截图为 `artifacts/20261026-file-management/recovery-saved-hidden-fixed.png`。后台服务仍由当前登录会话的 `com.researchagent.recovery8000` 托管，原用户记忆未用于测试写入。
