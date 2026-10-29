# Spec030 Task08 Artifact 发布可见性隔离

日期：2026-10-29  
状态：路由隔离已实现，待独立后端评审。范围仅限现有 Research Session Artifact 读取路由；未新增 endpoint、数据库 schema 或 store API。

## 规则

- 对一个 Artifact 所属 task/report_version，若存在 canonical `ResearchReport` row，只在 row `status == "completed"` 且其 `report_json.generation.published is True` 时公开。
- canonical JSON 缺失、解析失败、版本/task 身份不一致、状态非 completed 或 published 不是 JSON literal `true` 时 fail closed，list 不返回，download 返回既有 `ARTIFACT_NOT_FOUND`。
- 若该版本不存在 canonical report row，按历史 legacy Artifact 兼容路径继续显示/下载，不改变旧 report delivery 语义。
- list/download 先用 `OWNER_ID` 验证 session，再用 owner-scoped Store 读取并匹配 session 的 task；身份校验通过后才读取 Artifact。Session detail 内嵌的 artifacts 使用相同发布过滤，且先验证当前 owner/task。

## 改动

- `backend/app/api/routes_research.py`：新增 `_canonical_report_is_published` 和 `_visible_session_artifacts` 作为共享投影；接入 session Artifact list、download、session detail。Download 在 task/session 和 Artifact 所属 task/owner 校验后，以 canonical report version 检查发布标记，再返回内容。
- `tests/research/test_report_artifact_visibility.py`：覆盖 unpublished、draft、completed 但 unpublished、非 boolean published、畸形 JSON、published canonical、legacy 无 canonical、session/task 校验顺序，以及 session detail 投影。
- `tests/research/test_report_synthesis_contract.py`：给原 HTML inline/attachment 路由契约的 Fake Store 补 owner-scoped task 和 legacy canonical-row 读取，保持既有兼容测试有效。

没有修改 `ResearchStore`、Orchestrator、ReportDeliveryService 或 Artifact 创建流程；发布 CAS 仍是 canonical report row 的唯一可见性开关。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_artifact_visibility.py tests/research/test_report_synthesis_contract.py` | 0 | 41 passed in 1.63s |
| `/Users/wjh/ResearchAgent/.venv/bin/ruff check --ignore I001,SIM105 backend/app/api/routes_research.py tests/research/test_report_artifact_visibility.py tests/research/test_report_synthesis_contract.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/api/routes_research.py tests/research/test_report_artifact_visibility.py tests/research/test_report_synthesis_contract.py` | 0 | 通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |

未忽略规则的精确 Ruff 命令退出码为 1，显示 `routes_research.py` 既有 import 排序 `I001`（第 53 行）和 `SIM105`（第 615 行）；它们位于本次变更之外。忽略这两条既有诊断后，改动文件无 Ruff 问题。未运行全量测试、模型、部署或 Git 操作。

## Review focus

独立评审请确认 list、download 和 session detail 没有未发布 canonical Artifact 的旁路；owner/session/task 绑定先于 Artifact 访问；legacy 无 canonical row 保持可读；published predicate 对 malformed JSON、状态和 literal boolean 使用 fail-closed 语义。Artifact 读取测试在 Fake Store 上执行，数据库查询与请求路由器级 HTTP 集成未在本 Task 重跑。
