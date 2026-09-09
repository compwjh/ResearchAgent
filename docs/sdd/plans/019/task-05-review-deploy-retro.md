> 关联：[spec-019](../../specs/019-paper-import-status-feedback.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03、04；当前状态：`已完成`

# Task05 评审、部署与复盘

## 状态与一句话目标

`待执行`。完成需求/技术/验收三份评审，实际启动服务并在浏览器可访问的地址上做运行时验证（导入成功/部分失败/上下文不可用三类场景），最后落盘复盘。

## 背景与前置条件

- 前置：Task03（前端）、Task04（后端）均已完成且单端回归通过。
- 服务现状：本项目 FastAPI 跑在 `127.0.0.1:8002`（8000 端口被另一目录 `/Users/wjh/ResearchAgent` 占用）；启动命令
  `nohup .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8002 > deploy/run-8002.log 2>&1 &`
- 注意：uvicorn **未启用 `--reload`**，任何后端改动必须**重启服务**才生效（本次已因未重启导致修复"看起来没生效"）。

## 数据、配置与接口

- 不适用（评审与验证任务）。
- 验证接口：`POST /api/papers/imports`、`GET /api/papers/imports/{id}`、`POST .../retry`、`GET /api/kb/papers`。

## 实施步骤与文件边界

1. 需求评审 + 技术评审（开发主管），问题关闭后才转验收。
2. 重启服务并确认 `GET /api/papers/conferences` 为 200。
3. 运行时验证三类场景：
   - 正常导入 → 状态栏给出确定结论，论文落盘且 `status: indexed`；
   - 构造失败项（如失效候选）→ 与成功项**同时**呈现，不出现先错后完成；
   - 检索上下文不可用 → 提示与"未就绪/已过期/不存在"对应且可行动。
4. 验收评审 + 开发主管签字。
5. 复盘落盘（含"未重启导致修复看似失效""后端 503 兜底掩盖真实缺陷"两条经验）。

**文件边界**：只写评审/复盘文档与 task 回填；不改业务代码。

## 子代理分派

- `backend-reviewer` / `frontend-reviewer`（`qwen3.8:27b-mlx`）分别只评各自端。
- `tester`（`qwen3.5:9b`）跨端验收并产出 `docs/sdd/reviews/019-acceptance-review.md`。
- 日志：`.codebuddy/agent-logs/spec-019/task-05/<role>/<时间戳>.md`。

## 边界与明确不做

- 不做：借评审扩大范围（新需求另立 spec）。
- 不做：操作其它目录的服务（`/Users/wjh/ResearchAgent` 的 8000 端口进程禁止触碰）。

## 验收、风险与回滚

- 验收：三份评审真实落盘、运行时三类场景结论明确、spec 状态转 `已完成` 且 changelog 已记。
- 风险：端口冲突 → 换可用端口并在回复中明确告知实际端口与启动命令。
- 回滚：按任务逆序 revert。

## 产出物、执行结果与变更日志

待执行后填写。
