# Spec022 Task05 前端测试报告

## 结论

**PASS（前端定向范围，最终 A/B 切换竞态修复后）**。来源时序、0–5 上限、单项展开互斥/XSS、安全原文入口、历史处理步骤 hydrate、hydrate 与 openConversation 切换竞态、无 done EOF 中断、处理过程状态、reconnect/failure、reduced-motion、旧 DOM/资源版本及既有 Node 合同均通过。

## 命令与结果

| 检查 | 命令 | 退出码 | 数量/结果 |
|---|---|---:|---|
| JavaScript 语法 | `node --check frontend/app.js` | 0 | 通过 |
| 新来源行为合同 | `node tests/test_frontend_conversation_research.js` | 0 | PASS（0–5、互斥展开/收起、XSS、URL 白名单） |
| 前端静态契约 | `./.venv/bin/python -m pytest -q tests/test_frontend_conversation_contract.py tests/test_frontend_paper_contract.py tests/test_frontend_management_contract.py` | 0 | **43 passed** |
| 既有前端 Node 合同全集 | `rg --files tests \| rg 'test_frontend_.*\\.js$' \| sort \| while read -r test_file; do node "$test_file" \|\| exit 1; done` | 0 | **5/5 PASS**（含新增来源合同） |
| 新模块语法 | `node --check frontend/conversation-research.js` | 0 | 通过 |

## 覆盖矩阵

- **sources 时序/0–5**：SSE `sources/citations` 先暂存；只有 generation completed 后 render；模块截断到 5。
- **详情安全**：document/file/page/chunk/score/text 使用 textContent；恶意标签只作为文本；原文 URL 仅匹配既有 GET source 路由。
- **单项交互**：点击展开一个来源；点击另一个关闭前一项；再次点击当前项收起。
- **处理过程**：真实 progress 的 running/completed/failed/skipped 对应紫色海浪/静态紫色/红色/灰色；done 后默认折叠；reconnect 与连接失败进入可见状态。
- **历史步骤**：初次消息加载及向上分页均串行 GET `/api/messages/{message_id}/processing-steps`；generation/message ID 守卫阻止旧会话污染；失败显示灰色降级且不把摘要当 Markdown。
- **切换竞态**：历史 hydrate 不持有全局 `loadingMessages`；消息网络请求按会话 ID/请求令牌区分，hydrate 共享串行队列且每个 await 后复核代际、会话和消息 ID。
- **EOF/取消**：无 done EOF 标记 interrupted、保留已生成内容并清除 sources；AbortController 取消不产生网络失败提示。
- **动画与旧契约**：`prefers-reduced-motion` 关闭海浪动画；项目/会话/记忆/知识库/论文 DOM 与既有 Markdown/DOMPurify 契约保留；资源 v28 同步。

## RED 记录

- 实现前静态契约：**4 failed / 6 passed**，缺少 v28、sources 门控、来源模块和 skipped 状态，符合先测后写的 RED 门。

## 未执行/阻塞

- 未运行后端 pytest、全量回归、浏览器 E2E、部署或跨端 smoke，符合 frontend-dev 单端边界。
- 当前无前端测试阻塞。跨端 smoke 需主 Agent 在后端服务可监听环境执行。

## 评审修复记录

- P1-1：关闭历史处理步骤缺失与无控并发；串行 hydrate、代际/消息 ID 守卫和灰色降级已补齐。
- P1-2：关闭无 done EOF 静默结束；显式区分 reader EOF 与 AbortController 取消。
- P2：reconnect 不再遗留 running 占位，统一为 skipped/可重试状态。
- 复审剩余 P1：关闭 hydrate 阻塞新会话及旧 hydrate 污染游标/滚动/状态问题。
- 最终竞态修复：消息加载按 conversation ID + Symbol token，新会话不再被旧 hydrate 阻塞；hydrate 队列每个 await 后复核代际/会话/消息 ID。
- A/B 延迟切换修复：`openConversation` 使用独立 token/generation；列表、消息请求成功/失败和最终 UI 收尾均有 guard，旧 A 结果不覆盖 B。

## 运行信息

- 开始：2026-09-11 约 07:00（Asia/Shanghai）
- 结束：2026-09-11 约 07:58（Asia/Shanghai）
- 耗时：约 58 分钟（含四轮评审修复）
- 验收角色：frontend-dev（定向自测）
- 模型：临时 Luna high（按主 Agent 分派）
- token/精确工具统计：运行时不可用
- 进展日志：`.codebuddy/agent-logs/spec-022/task-05/frontend-dev/20260911-000000.md`

## 主 Agent 后续

请由 `frontend-reviewer` 复核 DOM/XSS/资源版本，再由 tester 进行桌面 SSE smoke；最终全量回归与部署留给 Task08。
