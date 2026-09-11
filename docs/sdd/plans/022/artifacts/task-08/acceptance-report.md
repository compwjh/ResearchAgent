# Spec022 Task08 最终候选验收报告

## 结论

**PASS（最终候选自动化、静态检查、部署与桌面/手机 DOM smoke 通过；模型依赖场景按真实环境记录为阻塞）。**

当前工作树唯一最终全量回归退出码为 0，未发现全量测试失败、冲突标记或 diff 空白错误。由于本机 Ollama 返回 `models=[]`，对话生成探针真实返回 `503 MODEL_UNAVAILABLE`；本报告不把该环境阻塞伪造为 token/progress/done 或 RAG 成功。

## 执行信息

| 字段 | 结果 |
|---|---|
| 日期 | 2026-09-11（Asia/Shanghai） |
| 验收角色 | tester |
| 业务代码修改 | 无；仅更新验收/复盘文档、进展日志，并移除验收文档尾随空格 |
| 进展日志 | `.codebuddy/agent-logs/spec-022/task-08/tester/20260911-full-regression.md` |
| 默认端口 | 8000 已被 PID 60107 占用；未停止或覆盖该进程 |
| 本轮部署端口 | 8001；服务仍由 `RERANKER_ENABLED=false ./.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8001` 运行 |

## 唯一最终全量回归

| 检查 | 命令 | 退出码 | 真实结果 |
|---|---|---:|---|
| 全量 pytest | `./.venv/bin/python -m pytest -q` | 0 | **1168 passed、1 skipped、5 warnings、41 subtests passed**，72.91s |

该命令在后端共享 URL 安全边界修复、SystemRule fail-closed 修复、Task05 global 门禁测试基线及前端合同修复后的最终候选上执行，未使用排除参数或历史结果替代。

## 静态与前端合同检查

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| 前端脚本语法 | `node --check frontend/app.js` | 0 | PASS |
| 前端脚本语法 | `node --check frontend/conversation-research.js` | 0 | PASS |
| 前端脚本语法 | `node --check frontend/kb-inspection.js` | 0 | PASS |
| Node 合同 | `node tests/test_frontend_conversation_research.js` | 0 | PASS |
| Node 合同 | `node tests/test_frontend_kb_inspection_interaction.js` | 0 | PASS |
| Node 合同 | `node tests/test_frontend_kb_inspection_pdf.js` | 0 | PASS |
| Node 合同 | `node tests/test_frontend_kb_inspection_renderer.js` | 0 | PASS |
| Node 合同 | `node tests/test_frontend_kb_inspection_runtime.js` | 0 | PASS；合计 **5/5** |
| 后端语法 | `find backend -name '*.py' -type f -exec ./.venv/bin/python -m py_compile {} +` | 0 | 全部通过 |
| 冲突标记 | `rg -n '^<<<<<<<|^=======|^>>>>>>>' --glob '!**/.venv/**' --glob '!**/.git/**' .` | 0 | 无命中 |
| 空白检查 | `git diff --check` | 0 | 通过；初次命中本验收文档第 420 行尾随空格，已移除后重跑 |

## 部署与运行时 smoke

8000 已有用户进程监听，未停止。首次沙箱内监听 8001 被环境拒绝后，按环境规则以提升权限直接启动当前工作树；应用启动成功。

| 场景 | 结果与证据 |
|---|---|
| health | `GET http://127.0.0.1:8001/api/health` → HTTP 200；响应 `status=ok`、`model=qwen3.8:27b`、`models=[]`。 |
| 首页 | `GET http://127.0.0.1:8001/` → HTTP 200；首页返回 32422 bytes，资源标签包含当前 `app.js?v=32`、`styles.css?v=32`。 |
| SystemRule | `GET http://127.0.0.1:8001/api/system-rule` → HTTP 200；返回空内容、`enabled=false` 和有效 `updated_at`。 |
| 模型降级 | `POST /api/conversations/messages` 模型探针 → HTTP 503；响应 `{"detail":{"code":"MODEL_UNAVAILABLE","message":"无法连接 Ollama 服务","retryable":true}}`。本机无可用 Ollama 模型，未伪造成功 token/progress/memory/done SSE。 |
| 桌面 Chromium DOM | CUA 视口 1280×900，页面可达；AX/DOM 包含 `project-tree-toggle`、`project-list`、`new-project-button`、`conversation-list`、记忆治理导航、聊天输入和发送按钮。 |
| 手机 Chromium DOM | CUA 视口 390×844，页面可达；AX/DOM 包含唯一 `mobile-nav-toggle`、`mobile-sidebar`、`mobile-nav-close`，以及项目/会话/记忆导航、聊天输入和发送按钮。验收后已恢复默认视口。 |

## 覆盖边界

- 本轮全量 pytest 与规定静态/Node 合同均通过，上一候选的 3 个全量失败项已不再复现。
- 部署、health、首页、SystemRule、桌面和 390×844 DOM smoke 均在当前工作树真实执行。
- 对话生成、RAG citations、依赖模型的成功 SSE 链路因本机 `models=[]` 无法验证；这是真实环境阻塞，不判定为成功，也不伪造结果。应在有可用 Ollama 模型的环境补跑。
- 未修改业务代码、未提交、未停止 8000 上的用户进程。

## 签字

- 验收执行：tester
- 详细复盘：`docs/sdd/retro/2026-09-11-spec-022-memory-retro.md`
- 架构师签字：待主 Agent 按收口流程确认
