# Spec030 Task08 Artifact 可见性后端独立评审

日期：2026-10-29  
范围：仅复审 `backend/app/api/routes_research.py` 的 Research Session Artifact list/download 与 session detail 投影，以及 `tests/research/test_report_artifact_visibility.py`。未修改业务代码或测试。

## 复审结论

**PASS** — 初审指出的 MEDIUM 问题已修复：公开投影只包含 `markdown`、`html`、`citation_manifest`；已发布和 legacy 版本中的 `intermediate` 都不会出现在列表或 session detail，下载返回 `ARTIFACT_NOT_FOUND` 404。canonical 发布、owner/session/task 绑定和无 canonical row 的 legacy 兼容均符合本次复审范围。

> 初审的 **BLOCK** 和问题记录保留在下方作为历史；它不再是当前开放阻塞项。

## 初审记录（保留）

初审发现 `_visible_session_artifacts` 未限制正式类型，导致已发布版本的 `intermediate` 会暴露在 list/session detail 并附下载 URL，虽然下载端返回 404。修复方向是共享投影仅保留三类正式产物，并用已发布和 legacy 版本的中间产物反例覆盖列表、详情和下载。本次复审已验证修复完成，当前状态：**已解决**。

## 复审核查

- **Owner/session/task 顺序：通过。** List 先以 `OWNER_ID` 读取 Session，再 owner-scoped 读取并匹配 Task，随后才列 Artifact（`routes_research.py:1139-1151`）。Download 先校验 Session、Task，再 owner-scoped 读取 Artifact，并要求 Artifact task 与 Session task 相同（`routes_research.py:1163-1172`）。Session detail 也先以 owner 读取 Session/Task，再构建共享 Artifact 投影（`routes_research.py:1271-1288`）。
- **Canonical 发布标记：通过。** report row 的 task/version/status 必须分别匹配且为 `completed`；JSON 解析失败或结构异常会关闭；发布标记使用 `generation.get("published") is True`，拒绝字符串 `"true"` 等非布尔值（`routes_research.py:800-817`）。
- **Legacy 兼容：通过。** 指定版本没有 canonical row 时保留既有 Artifact 读路径（`routes_research.py:802-803`）；下载 legacy 版本的测试返回 200（`test_report_artifact_visibility.py:183-190`）。
- **正式类型与中间产物：通过。** 类型 allowlist 精确为 `markdown`、`html`、`citation_manifest`（`routes_research.py:81`）；共享 list/detail 投影按 allowlist 过滤（`routes_research.py:820-840`），download 对其外类型返回 `ARTIFACT_NOT_FOUND` 404（`routes_research.py:1182-1183`）。测试覆盖 published 与 legacy 中间产物不出现在 list/session detail，以及 published intermediate 下载 404（`test_report_artifact_visibility.py:92-143`）。

## 验证

- 命令：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_artifact_visibility.py`
- 结果：退出码 0；8 passed。
- 独立内存 Store 路由核验：三类正式 Artifact 均能列出并下载；`intermediate` 不列出且下载 404 / `ARTIFACT_NOT_FOUND`；跨 task Artifact 下载 404；各访问均传入 `OWNER_ID`。退出码 0。
- 未运行全量测试、真实数据库/HTTP 集成、部署或 Git 操作。

## Review Summary

| Severity | Count | Status |
|----------|------:|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **PASS** — 初审 BLOCK 的 MEDIUM 问题已修复并经定向验证；当前无开放阻塞项。
