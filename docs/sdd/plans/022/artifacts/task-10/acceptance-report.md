# Spec022 Task10 跨端定向验收报告

## 结论

**PASS（Task10 定向验收范围；不等同于 Spec022 已完成）**。

Task10 指定后端测试 64 项全部通过，前端 Task10/受影响合同 44 项全部通过，JavaScript 语法与 5 个 Node 合同全部通过，差异空白检查退出码为 0。现有后端/前端 reviewer 均为 GO。没有发现 P0/P1 验收阻塞。

本轮未运行全量 pytest，未修改业务代码，未执行独立浏览器 Chromium 点击/视觉交互；浏览器风险和 reviewer 已注明的两个 P2 保留项交由主 Agent/Spec022 收口阶段处理。

## 执行信息

| 字段 | 结果 |
|---|---|
| 角色 | tester（临时 Luna high） |
| 关联 | `docs/sdd/specs/022-project-conversation-memory.md`、`docs/sdd/plans/022/task-10-system-rule-project-memory-navigation.md` |
| 业务代码修改 | 无；仅新增本报告、追加验收评审章节和进展日志 |
| 进展日志 | `.codebuddy/agent-logs/spec-022/task-10/tester/20260911-174203.md` |
| 报告时间 | 2026-09-11（Asia/Shanghai） |

## 定向命令与真实结果

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| Task10 后端及受影响后端 | `./.venv/bin/python -m pytest -q tests/test_task10_backend.py tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_chat_route.py tests/test_kb_ask_trace.py tests/test_task05_backend.py --tb=short` | 0 | **64 passed in 5.78s** |
| 前端 Task10/受影响合同 | `./.venv/bin/python -m pytest -q tests/test_frontend_task10_system_rule_contract.py tests/test_frontend_task09_project_tree_contract.py tests/test_frontend_conversation_contract.py tests/test_frontend_management_contract.py tests/test_frontend_task05_repair_contract.py --tb=short` | 0 | **44 passed in 0.04s** |
| JavaScript 语法 | `node --check frontend/app.js && node --check frontend/conversation-research.js` | 0 | PASS |
| 前端 Node 合同 | `node tests/test_frontend_conversation_research.js && node tests/test_frontend_kb_inspection_interaction.js && node tests/test_frontend_kb_inspection_pdf.js && node tests/test_frontend_kb_inspection_renderer.js && node tests/test_frontend_kb_inspection_runtime.js` | 0 | **5/5 PASS** |
| 差异空白 | `git diff --check -- frontend/index.html frontend/app.js frontend/styles.css backend tests` | 0 | PASS |
| 冲突标记检查 | `if rg -n --hidden -g '!**/.git/**' -g '!**/.venv*/**' -g '!**/vendor/**' -g '!**/.codebuddy/skills/**' -g '!**/.codebuddy/agent-logs/**' -e '^<<<<<<<|^=======|^>>>>>>>' backend frontend tests docs/sdd/plans/022 docs/sdd/reviews/022-acceptance-review.md; then exit 1; else exit 0; fi` | 0 | 未发现冲突标记 |

pytest 结束时观测导出器曾尝试访问本地 `127.0.0.1:3000` 并最终报告 exporter timeout；pytest 仍以退出码 0 完成，未改变 64 项测试结果。该本地观测端点问题记为环境风险，不判为 Task10 测试失败。

## 固定验收点

| 验收点 | 判定 | 证据 |
|---|---|---|
| 项目树单列、项目标题与文件夹状态 | PASS | `test_frontend_task09_project_tree_contract.py`、`test_frontend_task10_system_rule_contract.py`；覆盖唯一单列、长/空名称可见、顶部“项目 ▼”、内联 SVG、`aria-hidden`/`aria-expanded` 与键盘语义。 |
| 会话点击导航 | PASS（合同） | Task10 前端合同断言记忆管理来源会话先保存视图快照、调用 `showView('chat')` 再 `openConversation()`，并恢复 scope/status/project/scroll/展开项目状态；未执行真实浏览器点击。 |
| SystemRule CRUD、边界与 owner 隔离 | PASS | `test_task10_backend.py` 覆盖 GET/PUT/PATCH/DELETE、空内容启用 409、12,000 Unicode 成功、12,001 返回 400、停用保留、清空停用以及服务端 owner 作用域；前端合同覆盖独立卡片、编辑/启停/清空二次确认。 |
| 真正 system role 与 fail-closed | PASS（自动化/既有 reviewer smoke） | 后端合同覆盖 role-aware system/user 消息、无规则会话仍保持独立 user、观测 content 脱敏、损坏 v6 schema 拒绝启动；既有 reviewer 报告记录启用规则读取失败时 `SYSTEM_RULE_UNAVAILABLE`、无 token、模型不调用。 |
| 项目优先记忆路由 | PASS | 后端合同覆盖原始用户文本 global 门禁与 project snapshot；绑定项目普通“记住”只能项目范围，明确 global fixture 才允许 global。 |
| 未绑定会话普通记忆询问 | PASS | 后端受影响 API/记忆测试与前端合同覆盖未绑定普通记忆保持待确认；前端仅提供已有 active 项目选择，不提供自由文本 global。 |
| 旧 `/api/chat` 与 KB 门禁 | PASS | `tests/test_chat_route.py`、`tests/test_kb_ask_trace.py` 纳入 64 项；覆盖 role-aware 入口、观测脱敏和 KB 当前问题不重复进入 system 内容。 |
| ProcessingStep 去重 | PASS（合同） | Task10 前端合同断言 `system-rule-applied` 稳定标识只渲染一次；既有 Task05 后端集合纳入本轮 64 项，保持处理步骤终态契约。 |

## 主 Agent 运行时证据

主 Agent 已提供当前工作树的受控 runtime smoke：

| 检查 | 结果 | 说明 |
|---|---|---|
| `GET /api/health` | HTTP 200 | 服务健康。 |
| 首页 `GET /` | HTTP 200 | 首页可访问。 |
| `GET /api/system-rule` | 成功返回稳定对象 | 规则读取入口可用；无规则场景保持 disabled/空内容语义。 |

此外，主 Agent 使用本机 Chromium 无头 `--dump-dom` 加载首页，确认唯一项目树标题、顶部“项目 ▼”、悬浮操作按钮、内联文件夹 SVG、项目名称和记忆治理入口均存在，旧常驻创建表单和旧项目选择器未出现在首页 DOM。该检查属于首页静态/DOM 冒烟，不替代 Task08 的全量浏览器交互验收。

本 tester 隔离环境再次访问 `127.0.0.1:8000` 得到 HTTP 000（服务不可达），因此没有把该隔离限制重复判为产品失败；以上三项以主 Agent 已完成的 smoke 记录为准。本轮未执行真实 Chromium 的记忆页→绑定/未绑定会话点击、返回筛选/滚动恢复、长名/空项目视觉折行、文件夹开合焦点和 SystemRule 对话框交互。

## 风险与后续动作

1. **P2：后台 analysis worker 时序波动。** backend reviewer 记录过组合运行时的 worker timing flaky，但独立重跑通过；本轮六文件组合已 64 passed。Spec 收口全量回归前继续观察。
2. **P2：四类用户可见入口与后台模型隔离矩阵仍有少量自动化空白。** 当前 direct、无规则会话、KB、观测和损坏 schema 已有合同/探针，完整失败矩阵仍需收口阶段补齐或由主 Agent smoke 覆盖。
3. **浏览器交互未由本 tester 执行。** 需主 Agent 在可见 Chromium 中完成 Task10 T5 的真实点击/视觉/焦点矩阵；不能以本报告静态合同通过替代浏览器验收。
4. 本轮严格未运行全量 pytest；Spec022 仍需按收口流程完成全量回归、最终部署、运行时验证、状态台账更新和架构师签字。

## 签字

- 验收执行：tester（临时 Luna high）
- 验收结论：PASS（Task10 定向范围）
- 架构师签字：待主 Agent 复核并签署
