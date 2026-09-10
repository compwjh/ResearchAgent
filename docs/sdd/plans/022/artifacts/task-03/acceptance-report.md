# Spec022 Task03 验收交接

## 结论

**PASS（无 P0/P1/P2）**。后端/前端定向回归通过，当前工作树服务经重启后 API smoke 全部通过。此前前端记忆治理入口的键盘激活 P2 已修复并由新增契约测试覆盖。Task02 原验收证据保留在 `docs/sdd/reviews/022-acceptance-review.md` 的 Task02 章节，本文件仅交接 Task03 增量。

## 定向验证

- `.venv/bin/python -m pytest -q tests/test_memory_repositories.py tests/test_conversations_api.py tests/test_chat_route.py tests/test_api.py`：退出码 0，36 passed in 4.29s。
- `.venv/bin/python -m pytest -q tests/test_frontend_management_contract.py tests/test_frontend_conversation_contract.py tests/test_frontend_paper_contract.py`：退出码 0，**35 passed**（含记忆治理导航 Enter/Space 键盘激活契约）。
- `node --check frontend/app.js`：退出码 0。
- `for test_file in tests/test_frontend_*.js; do node "$test_file" || exit 1; done`：退出码 0，4/4 PASS。
- 未运行全量 pytest、浏览器 E2E 或无关领域测试。

## API smoke

使用唯一 tag 的临时项目 A/B、global/project memory 和一条会话验证：项目创建 201；global candidate 创建/confirm=201/200；PATCH 记忆返回新版本且旧版本 superseded；disable/delete/undo=200/204/200；global/project 列表和 SSE global+project recall 通过；跨项目移动无确认=409、带 `confirm_move=true`=200；删除附着会话的项目=204 且会话 GET=404；删除项目后 global memory 仍可见。所有临时项目、会话和 global memory 均已清理，tag 查询无残留。

为确保 smoke 使用当前代码，发现旧监听服务 OpenAPI 只暴露 GET memory 后，已停止旧 PID 并以 `RERANKER_ENABLED=false ./deploy/start.sh` 启动当前工作树；重启后 health=200，Task03 memory 管理端点齐全。

## 固定旅程判定

- 项目/会话生命周期：PASS；API、repository 测试和前端契约覆盖创建、归档/恢复、删除、稳定记录。
- 绑定/移动确认：PASS；无确认拒绝，确认后切换项目并按 binding cutoff 隔离旧历史；解绑边界测试通过。
- global/project 隔离与治理：PASS；owner + scope 约束、global→project 召回顺序、candidate 确认、evidence、版本编辑、停用、删除、undo 均通过。
- 项目删除级联/全局保留：PASS；事务级联删除所属会话/项目记忆，global memory 保留；真实 smoke 已验证。
- 会话删除不联动记忆：PASS；补充 disposable 会话 SSE 完成后 DELETE conversation=204，关联 project memory GET=200；随后项目删除清理该记忆。repository 仅软删会话，既有测试证实记忆治理数据不被联动抹除。

## 风险与后续动作

- 运行时模型响应耗时有波动：一次带较长临时 tag 的 disposable 首条消息达到客户端 90 秒上限，改用简短 `hello` 后在 45 秒内 HTTP 200 且 `done=1`；不影响本次 CRUD/删除判定，临时数据均已清理。
- 主 Agent 复核本报告并填写统一 acceptance review 架构师签字；Spec 收口仍需最终全量回归、状态台账、部署与运行时验证。

## 运行信息

- 验收角色：tester（临时 Luna high）。
- token / 工具精确统计：当前子代理运行时不可用。
- 进度日志：`.codebuddy/agent-logs/spec-022/task-03/tester/20260911-acceptance.md`。
