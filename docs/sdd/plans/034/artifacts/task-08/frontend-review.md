# Spec034 Task08 前端终审报告

评审角色：frontend-reviewer（只评 `frontend/**`；跨端契约问题单独标注）  
评审范围：Task08 最后 HTML inline URL 修复、Task08/Task07 前端交付与合同、Spec034 Report/Artifact/Notification/UI 验收，以及后端实际下载响应和历史消息 projection。  
评审时间：2026-09-13（Asia/Shanghai）

## 结论

**GO（前端终审通过）**。最后修复已正确接通 HTML 阅读 URL：会话历史与 Research Tab 都先通过 owner-bound 路径白名单，再由固定 artifact type helper 追加唯一的 `?mode=inline`；外部 URL、已有 query、恶意参数被拒绝，Markdown/citation manifest 仍保持 attachment 下载。此前 P1 已关闭；两个 P2 仍记录为后续改进，不阻断本 Task 前端收口。

真实浏览器/服务 smoke 尚未在本受限环境执行；发布收口仍应补验真实响应头、HTML XSS、通知 SSE/read/jump 与刷新后的历史报告面板。

## 本轮修复复核

### HTML inline URL：通过

- Research Tab `renderReportArtifacts()` 使用 `artifactActionUrl(kind, url)`；该 helper 先调用 `safeArtifactUrl()`，只接受 `/api/research-sessions/{id}/artifacts/{artifact}/download`，HTML 才返回 `${safeUrl}?mode=inline`，Markdown 和 citation manifest 原样返回安全基础 URL（`frontend/research-tasks.js:100-110,985-999`）。
- 会话历史 `renderConversationReport()` 同样先取 `safeBaseUrl`，再调用共享 helper；旧 fallback 也只会为已通过固定路径正则的 HTML 追加固定参数（`frontend/app.js:1216-1225`）。
- `safeArtifactUrl()` 拒绝 `https://`、`javascript:`、任意 query 或外部参数；已有 `?mode=inline` 不会被二次拼接，helper 直接返回空（`frontend/research-tasks.js:100-111`）。
- HTML 链接使用 `_blank` 和 `rel="noopener noreferrer"`；Markdown/manifest 使用 `download`。后端仅对 HTML 接受 inline，默认仍为 attachment（`backend/app/api/routes_research.py:413-440`）。

### P1 回归：已关闭

- 最终 assistant 历史消息现在由 owner/session/task/final-message 绑定的后端 projection 提供 `report`/`research_report`、版本/status/safe summary、三类 Artifact metadata/download URL 和 citation manifest Artifact；前端 `reportMetadataFrom()` 能消费并按 status → summary → actions → citations 顺序渲染（`backend/app/api/routes_conversations.py:268-313`；`frontend/app.js:1173-1236,1279`）。
- 通知遵循 Spec034 五态：`completed/partial/failed/waiting_approval/interrupted`，无 `retry` kind。重试事实由 `failed` payload 的 `retryable`/`retry_attempt` 文案表达；未知 kind/status 丢弃并显示同步错误，heartbeat 不进入列表（`frontend/research-tasks.js:8-17,124-147,252-268,311-315`；后端 `backend/app/research/application/report_synthesis.py:516-530`）。
- HTML inline 的前端 URL 现在与后端 `mode=inline` 契约一致，先前唯一 P1 已关闭。

## 仍存在的 P2

### P2-01：citation projection 是 manifest Artifact metadata，不是逐条 citation

历史消息 projection 的 `citation_manifest` 当前是 metadata 对象（`artifact_id`、`artifact_type`、`content_hash`、`download_url`），前端会以 `textContent` 安全显示，因此“字段可渲染”通过；但逐条引用内容仍只能下载 JSON Artifact。Research Tab 的旧 report endpoint 也只返回 markdown/limitations/selections 等字段，不带 manifest 内容（`backend/app/api/routes_conversations.py:305-312`；`frontend/app.js:1228-1234`；`frontend/research-tasks.js:1003-1010`；`backend/app/api/routes_research.py:813-838`）。若最终验收要求在 UI 展示可追溯引用条目，应增加安全 manifest-entry projection 或明确 UI 为 metadata/下载。

### P2-02：历史消息 projection 固定扫描 100 个 task

`_research_report_projection()` 使用 `store.list_tasks(owner_id, limit=100)` 后内存匹配 final message（`backend/app/api/routes_conversations.py:273-283`）。超过 100 个研究任务后，较旧报告可能无法在刷新会话中恢复操作面板。建议改用持久化 final-message→session/task 关系或完整 keyset 分页。

## 安全、可访问性与兼容性复核

- 动态报告、通知、引用、Artifact 标签均使用 `textContent`/DOM API；新增 renderer 区域没有 `innerHTML`、`eval` 或 `document.write`。历史 Markdown 仍走既有 `marked → DOMPurify → DOMParser` 净化管线（`frontend/research-tasks.js:889-912`）。
- Artifact type 仅允许 `markdown`、`html`、`citation_manifest`；不暴露 `storage_ref`。HTML 新窗口具备 `noopener noreferrer`，下载类型具备 `download`。
- 通知 SSE 继续使用 `after_seq`，结合 EventSource `Last-Event-ID`、`notificationLastSeq` 和 seq/id 去重；断线重连从游标之后继续。read 使用原子 POST 后再按 conversation/session/task 跳转，可聚焦消息（`frontend/research-tasks.js:311-375,378-436`）。
- Task07 ProcessingTree 未被 Task08 破坏；处理树的三层顺序、upsert/idempotency、ARIA、展开恢复、滚动保护和 `prefers-reduced-motion` 仍通过。
- 新增 CSS 作用域保持在 `.sidebar`、`#research-view`/报告类；`frontend/index.html` 的 `app.js`/`styles.css` 均为 `?v=47`，旧版本 marker 保留。

## 验证记录

| 检查 | 结果 |
|---|---|
| `node --check frontend/app.js && node --check frontend/research-tasks.js` | 退出码 0 |
| `node tests/test_frontend_spec034_task08.js` | 退出码 0；Artifact URL、inline 参数、通知五态/去重通过 |
| `node tests/test_frontend_processing_tree.js` | 退出码 0；Task07 ProcessingTree Fake-DOM 通过 |
| 全部 `tests/test_frontend*.js` | 退出码 0；7/7 PASS |
| `.venv/bin/python -m pytest -q tests/test_frontend_spec034_task08_contract.py tests/test_frontend_spec034_task07_contract.py` | 退出码 0；12 passed |
| `.venv/bin/python -m pytest -q tests/test_frontend*.py` | 退出码 0；198 passed |
| `.venv/bin/python -m pytest -q tests/test_spec034_task08_backend.py` | 退出码 0；21 passed，包含 HTML inline/attachment 与历史 projection 跨端合同 |
| `git diff --check -- frontend/... tests/...` | 退出码 0 |
| 真实浏览器/服务 smoke | 未执行；需在服务可达环境补验 |

## Review Summary

| Severity | Count | Status |
|---|---:|---|
| P0/CRITICAL | 0 | pass |
| P1/HIGH | 0 | closed |
| P2/MEDIUM | 2 | follow-up |

Verdict: **GO** — 前端 Task08 终审通过；保留 P2-01 citation 条目 projection 和 P2-02 历史 task 分页改进，并在 Spec 收口前补真实浏览器 smoke。
