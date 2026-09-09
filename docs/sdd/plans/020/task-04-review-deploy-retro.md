> 关联：[spec-020 零碎 bug 解决](../../specs/020-misc-bug-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02、03；当前状态：`已完成`

# Task04 评审、部署与复盘

## 状态与一句话目标

`待执行`。完成需求/技术/验收三份评审，实际重启服务并做运行时验证（点击即有反馈、计数非 0、卡片动画、v2 状态流转），最后落盘复盘。

## 背景与前置条件

- 前置：Task02（前端）、Task03（后端）完成且单端回归通过。
- 服务：`http://127.0.0.1:8002`（8000 端口属另一目录 `/Users/wjh/ResearchAgent`，**严禁触碰**）；启动命令
  `nohup .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8002 > deploy/run-8002.log 2>&1 &`
- **uvicorn 无 `--reload`**：Task03 的后端改动必须**重启服务**才生效（spec-019 已因此踩坑）。
- Python 用 `.venv/bin/python`。

## 数据、配置与接口

- 不适用（评审与验证任务）。
- 验证接口：`POST /api/papers/imports`、`GET /api/kb/papers`、`POST /api/kb/papers/{id}/reindex`。

## 实施步骤与文件边界

1. 需求评审 + 技术评审（评审子代理），问题关闭后才转验收。
2. **重启服务**并确认 `GET /api/papers/conferences` 为 200。
3. 运行时验证：
   - 单次点击导入即出现"正在提交 N（≥1）个导入批次…"（不点第二次）；
   - 批次卡片立即出现、非终态有动画、完成后停止；
   - 导入完成后 `/api/kb/papers` 中该论文 `chunkers.v2.status` 由 `pending` 变为 `indexing`/`indexed`；
   - 上传路径行为未回归。
4. 验收评审 + 签字（由 tester 执行，主 agent 代行开发主管签字并标注）。
5. 复盘落盘。

**文件边界**：只写评审/复盘文档与 task 回填；不改业务代码。

## 子代理分派

- `backend-reviewer` / `frontend-reviewer`（hy3）分别只评各自端。
- `tester`（hy3）跨端验收并产出 `docs/sdd/reviews/020-acceptance-review.md`。
- 日志：`.codebuddy/agent-logs/spec-020/task-04/<role>/<时间戳>.md`。

## 边界与明确不做

- 不做：借评审扩大范围（新需求另立 spec）。
- 不做：操作其它目录的服务。

## 验收、风险与回滚

- 验收：三份评审真实落盘；四类运行时结论明确；spec 转 `已完成` 且 changelog 已记。
- 风险：v2 依赖 27B LLM，本机可能显存不足或超时 → 允许失败但状态必须真实可见，并在复盘记录降级结论。
- 回滚：按任务逆序 revert。

## 产出物、执行结果与变更日志

待执行后填写。
