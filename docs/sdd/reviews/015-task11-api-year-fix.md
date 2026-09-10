# Spec015 Task11 accepted API 默认年份修复记录

- 角色：初级开发（junior-dev）
- 关联任务：`docs/sdd/plans/015/task-11-usenix-accepted-and-arxiv-fallback.md`
- 关联技术评审：`docs/sdd/reviews/015-task11-tech-review.md`（T11-B1）
- 进展日志：`.codebuddy/agent-logs/junior-dev-spec015-task11-api-year-fix-20260905-033018.md`

## 结果状态和摘要

已完成本切片。accepted API 在未显式指定年份时现在使用最近五个完整年份，范围与搜索服务默认 published 逻辑一致；显式当前年份仍可透传，未来年份被拒绝并返回稳定的 `INVALID_ACCEPTED_YEAR` 错误。

## 改动文件

- `backend/app/api/routes.py`
  - 默认年份由 `range(current_year - default_years + 1, current_year + 1)` 改为 `range(current_year - default_years, current_year)`。
  - accepted API 显式年份增加当前年份上界校验，并更新稳定错误消息。
- `tests/test_paper_discovery_api.py`
  - 增加冻结时间下的默认完整年份、显式当前年份透传和未来年份拒绝回归。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_paper_discovery_api.py` | 0 | 16 passed，9 subtests passed |
| `.venv/bin/python -m py_compile backend/app/api/routes.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

## 决策依据

Spec015 要求默认取最近五个完整年份；搜索服务的默认分支已实现 `current_year-default_years` 到 `current_year-1`。accepted 路由保留显式当前年份能力（accepted 论文可属于当前年份），但不接受未来年份。

## 风险与阻塞

本切片未发现阻塞。USENIX 缓存/节流、PDF 安全探测及跨来源合并优先级仍属于技术评审列出的其他阻塞，不在本切片范围内。

## 主 Agent 后续动作

读取两份改动文件并将本报告与日志纳入 Task11 复评证据；随后由 tech-lead 复核 T11-B1。

## 执行时间

- 开始：2026-09-05 03:18 +0800
- 结束：2026-09-05 03:30 +0800
- 总耗时：约 12 分钟
- 模型：gpt-5.6-luna/high（本次调度）
