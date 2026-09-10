# Task 06E-C 前端稀疏来源锚点报告

- 任务：Spec 018 Task 06E-C
- 角色：frontend-dev（临时 Luna xhigh）
- 状态：通过
- 范围：`frontend/kb-inspection.js`、`tests/test_frontend_kb_inspection_runtime.js`

## 实现摘要

1. 移除旧的首批 hotfix：不再收到第一页后强制清空 `cursor`，每个 200 响应继续按 `next_cursor` 请求，直到游标为空。
2. 加载阶段显示“正在加载定位关系：已获取 X / 约 Y”；只有所有 blocks、chunks、anchors 完整收齐后才渲染源文档、切片并绑定双向点击/键盘交互。
3. 检查清单缓存只有 `complete=true` 才允许用于 304；历史不完整缓存不会被消费。
4. 若 200 响应显式声明非 `source-anchor-v2`，前端 fail-closed 显示维护状态；已有 409 `INDEX_REBUILD_REQUIRED` / `INDEX_FINALIZE_REQUIRED` 继续走维护提示，不显示模糊服务错误，也不发起后续请求。
5. 删除映射展示的前端 top-3 截断，让后端提供的稀疏关系完整可见；未增加选择器 API、模糊匹配或文本猜测。

## 验证证据

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/kb-inspection.js` | 0 | 通过 |
| `node tests/test_frontend_kb_inspection_runtime.js` | 0 | 通过：文档分页、两页 v2 anchors、稀疏 b1→0/2、409 无后续 fetch、304 cache |
| `node tests/test_frontend_kb_inspection_interaction.js` | 0 | 通过：双向点击/键盘、跨页、窄屏、切片批量显示 |
| `node tests/test_frontend_kb_inspection_renderer.js` | 0 | 通过 |
| `node tests/test_frontend_kb_inspection_pdf.js` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 决策依据

- `source-anchor-v2` 的关系必须以真实原文区间交集为事实；前端不能用不完整第一页关系推断跳转。
- 加载完成以 `next_cursor` 为空为准；关系未完整加载时不创建任何可点击源/切片视图。
- 维护/重建提示是用户可观察状态，不能降级成“论文/服务不可用”。

## 风险与阻塞

- 真实 v2 manifest 重建和运行时 PDF 点击仍需 Task 06E-D/E 在后端版本门禁完成后验证。
- 本任务没有修改旧 manifest、Qdrant、embedding、原件或服务运行状态。

## 主 Agent 后续动作

1. 审阅 `kb-inspection.js` 与 runtime 测试 diff，确认 backend 返回的分页 `total.anchors` 与 `mapping_algorithm_version` 字段名一致。
2. 复跑前端测试并与 backend source-anchor-v2/inspection 409 门禁合并验证。
3. 仅在 fingerprint 校验通过后执行单文档 manifest 重建，再做真实浏览器 Introduction/第三页双向点击验收。

## 执行数据

- 开始：2026-09-10（本轮任务启动时间，精确秒未由调度器提供）
- 结束：2026-09-10（本轮验证完成）
- 总耗时：约 10 分钟（含一次中断后续作）
- 模型：Luna xhigh（临时分派）
- token / 工具调用统计：调度器未提供；可由主 Agent 运行记录补充
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06e/frontend-dev/20260910-sparse-anchor-frontend.md`

## 追加部署端口修复

- `deploy/start.sh` 的端口预检已从宽泛的 `lsof -ti:"$PORT"` 改为只匹配 TCP LISTEN：`lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t`。
- 这样已关闭的客户端连接不会再被当作服务端口占用；其他启动、Reranker 和前后台行为未改动。
- `bash -n deploy/start.sh`：退出码 0。
- 端口预检静态契约检查：退出码 0，确认旧宽泛检查不存在且 LISTEN 过滤存在。
- `shellcheck`：当前环境未安装，未执行。

## 追加浏览器缓存修复

- `frontend/index.html` 中检查器脚本版本由 `kb-inspection.js?v=22` 提升为 `kb-inspection.js?v=23`，确保浏览器加载完整分页版本，而不是旧首批 hotfix。
- 未修改业务逻辑。
- `git diff --check`：退出码 0。
