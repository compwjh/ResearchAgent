# Task02 后端测试报告

## 命令与结果

| 检查 | 命令 | 结果 |
|---|---|---|
| Python 语法 | `python -m py_compile backend/app/memory/*.py backend/app/chat/application/conversation_service.py backend/app/api/routes_conversations.py backend/app/api/schemas.py backend/app/api/routes.py` | 退出码 0 |
| Task02 精确回归 | `/Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py` | 退出码 0；6 passed |
| 旧聊天兼容回归 | `/Users/wjh/ResearchAgent_codebuddy/.venv/bin/python -m pytest -q tests/test_chat_route.py tests/test_api.py` | 退出码 0；16 passed |

## 覆盖项

- schema 幂等、WAL、owner 隔离、项目/会话/消息/记忆/证据/processing step 持久化。
- 消息 `target_chars` 分页及游标；首条消息项目绑定、SSE meta/memory/token/done。
- explicit 保存、ambiguous 待确认、未绑定项目记忆隔离。
- 三个真实处理阶段均有 `progress` SSE，且事件携带稳定 `step_id`、label、status、summary。
- 既有 `/api/chat` 与 `/api/agent/run` 回归保持通过。

## 未执行

- 未运行全量 pytest（Task02 阶段按 SDD 规则只跑精确及受影响回归）。
- 未执行部署与浏览器固定演示；待前端整合、验收 Agent 和主 Agent 收口时执行。

## 验收 Agent 补充（2026-09-11）

- 指定受影响测试：`.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_frontend_conversation_contract.py tests/test_frontend_paper_contract.py`，退出码 0，`35 passed in 1.01s`。
- JavaScript 语法：`node --check frontend/app.js`，退出码 0。
- 服务前置检查：`curl -sS -m 3 -w '\\nHTTP:%{http_code}\\n' http://127.0.0.1:8000/api/health` 返回连接失败/HTTP 000；本轮未执行 health/projects/conversations 只读 smoke，也未声称完成固定六步真实演示。
- 详细验收矩阵与阻塞原因见 `docs/sdd/reviews/022-acceptance-review.md`。

### 主 Agent 受控部署补充

- 主 Agent 受控服务 smoke：`GET /api/health` HTTP 200；临时 `POST /api/projects` HTTP 201。
- 临时首条消息 SSE 文件 `/tmp/spec022-sse` 事件顺序符合冻结契约：`meta → progress(memory_classification running/completed) → memory(saved/used) → progress(memory_recall running/completed) → progress(generation running/completed) → done(completed)`。
- 临时项目随后 `DELETE /api/projects/{project_id}` HTTP 204，数据已清理。
- 结论：此前 tester 子代理访问 127.0.0.1 HTTP 000 属环境限制，不是产品阻塞；结合上述运行时证据，验收报告整体结论更新为 PASS。
