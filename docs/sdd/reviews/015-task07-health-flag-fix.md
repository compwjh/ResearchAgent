# Spec015 Task07 健康检查功能开关修复记录

- 关联 spec：`docs/sdd/specs/015-security-paper-discovery.md`
- 关联计划：`docs/sdd/plans/015/task-07-paper-discovery-tab.md`
- 执行角色：junior-dev
- 修复时间：2026-09-05（Asia/Shanghai）
- 进展日志：`.codebuddy/agent-logs/junior-dev-spec015-task07-health-flag-20260905-003749.md`

## 修复目标

让 `GET /api/health` 返回服务端论文检索功能开关 `paper_discovery_enabled`，供前端首屏决定是否显示入口。值复用 `_paper_discovery_enabled()` 的请求时解析结果；响应不包含配置路径或其他内部配置。

## 改动范围

- `backend/app/api/routes.py`：在既有健康响应中增加布尔 `paper_discovery_enabled`。
- `tests/test_paper_discovery_api.py`：增加默认开启和 `PAPER_DISCOVERY_ENABLED=false` 两种环境回归测试，并断言响应 key 集合不扩张到敏感配置字段。

## 自测结果

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_paper_discovery_api.py` | 通过，`14 passed, 9 subtests passed` |
| `.venv/bin/python -m compileall -q backend/app` | 通过 |
| `git diff --check -- backend/app/api/routes.py tests/test_paper_discovery_api.py` | 通过 |

## 结论与边界

修复满足 Task07 功能开关健康字段契约；关闭开关时接口仍返回 HTTP 200，并仅报告布尔状态。未修改前端或其他后端接口，未进行外部论文源访问。

本切片未执行 commit、push、reset、stash 或 clean；由主会话统一集成。
