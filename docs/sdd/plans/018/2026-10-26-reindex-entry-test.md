# Spec 018 KB 重建入口前端回归报告

> 当前收口状态：本次 canonical ID 入口窄修已完成；本报告保留历史精确回归/未就绪段落，最终真实验收以追加验收报告为准。

日期：2026-10-26。角色：frontend-tester（临时模型档位 Luna max）。本报告只记录 `frontend/**`、`frontend/contract-tests/**` 与受影响的 `tests/frontend/test_frontend_paper_contract.py` 验证；未运行 backend pytest、全仓回归、真实生产 POST、部署、模型或远程调用。

## 范围与稳定状态

- author 当前稳定版本：生产 `app.js?v=61`、`styles.css?v=61`、地图 `literature-maps.js?v=21`。
- `frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` 是既有 frontend contract-tests 文件的修改，不移动到 `tests/frontend`，也未创建带 Spec/Task 编号的新测试文件。
- 验证 canonical `document_id` 优先、旧 DTO `paper_id` 回退、canonical-only endpoint/body、缺 ID 零 POST、202 排队、409 busy、503 message、同步双击锁、生产 markup 与 KB 输入草稿保持不变。

## 精确命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | `0` | JavaScript 语法通过 |
| `node --test frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` | `0` | `14 passed`，`0 failed`，`0 skipped` |
| `node --test frontend/contract-tests/context-meter-and-kb-count.test.mjs frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` | `0` | `22 passed`，`0 failed`，`0 skipped` |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_paper_contract.py` | `0` | `23 passed in 0.20s`，无 skip |
| `env PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false .venv/bin/python -m pytest --confcutdir=tests/frontend --collect-only -q tests/frontend/test_frontend_paper_contract.py` | `0` | `23 tests collected`，无 collecting error |
| `.venv/bin/python scripts/check_test_naming.py` | `0` | 无 spec/task 数字违规 |
| `.venv/bin/python scripts/check_test_layout.py` | `0` | `test layout: ok` |
| `git diff --check -- frontend tests/frontend` | `0` | 无空白/冲突标记错误 |

### 生产 markup 隔离 Chromium smoke

使用临时 localhost 静态服务器映射真实 `frontend/index.html` 与 `/assets/*`，Playwright 拦截所有 `/api/**`；没有请求真实生产服务。实际执行的 smoke 为 `.venv/bin/python - <<'PY' ... PY`（`ThreadingHTTPServer` + `sync_playwright`），验证生产 markup、canonical DTO、同步双击、请求 DTO 和输入草稿。

结果：退出码 `0`，无 skip、无 page error：

```text
production_markup: app.js?v=61
data_document_id: d4dfd2a620384ad5bece27320661f8f0
post_count: 1
post_url: /api/kb/documents/d4dfd2a620384ad5bece27320661f8f0/reindex
post_body: {"chunker":"all"}
status: 已提交重建：...（v1 + v2，任务 task-smoke 已排队）
draft_untouched: true
page_errors: []
```

另行静态断言确认生产 markup 同步包含 `/assets/app.js?v=61`、`/assets/styles.css?v=61`、`/assets/literature-maps.js?v=21`。

首次临时 smoke 尝试因本地静态服务器未提供 `/assets/` 别名，页面未加载 app bundle，等待 DTO 超时并退出 `1`；这属于测试 harness 配置问题，未发出 POST，不是产品断言失败。补齐本地 asset 映射后立即重跑，上述退出码 `0` 为最终结果。

## 关键契约结论

- canonical DTO 使用实际 `document_id`，请求只发一次到 `/api/kb/documents/{document_id}/reindex`，body 严格为 `{ "chunker": "all" }`；URL 不含 `undefined`。
- legacy `paper_id` 仅在缺少 `document_id` 时回退到同一 canonical endpoint；目标 legacy record smoke/contract 支持通过。
- `document_id` 与 `paper_id` 均缺失时显示“未提交请求”，POST 数量为 `0`。
- 202 显示排队成功与 task id；409 `INDEX_ALREADY_RUNNING`/running 显示 busy 提示且不误报成功；503 保留服务端 message，未渲染 `undefined`。
- 同一按钮同步双击只产生一个 POST；生产 markup smoke 中真实 DOM `data-document-id` 与 canonical target 一致。
- 重建动作不会改写 `#kb-question`，预填草稿在 smoke 后完全保持不变。

## 交接边界

本轮前端回归结论：**PRECHECK PASS（Node 14/14；合跑 22/22；Python 23/23；生产 markup smoke PASS；0 skip）**。本报告不替代主会话对指定真实文档的 canonical API 202/任务/v1-v2 终态验收；本轮未触碰真实生产数据。

## 后续 reviewer 阻断：当前结果不构成最终批准（2026-10-26）

在本轮 precheck 完成后，独立 reviewer 发现 author 候选仍有两个 P1，root 已交回 author 修复；因此上面的 14/22/23 与 production markup smoke 结果只保留为修复前历史证据，不能作为最终 GO/PASS：

- 非 `202` 的成功态 `2xx` 响应不能伪造“已排队”成功；必须收紧为带有效 `task_id` 的 `202` 才显示排队提示，并覆盖 invalid-2xx/no-task 场景。
- 同一文档的跨按钮/列表轮询重渲染必须共享 document-level in-flight guard，不能因 DOM 重渲染后换了按钮而产生第二个 reindex POST。

等待 author 明确稳定后，frontend-tester 将重新执行同一 Node 14/22、affected Python/static 与生产 markup smoke；在新结果前，本报告状态为 **NOT READY / BLOCKED（P1=2）**，不签最终验收。

## author P1 修复后的最终前端回归（2026-10-26）

root 已确认 author 修复稳定，本节为独立于前述 precheck 的最新结果；不聚合其他 Spec、全仓或后端计数。本轮验证范围仍仅为 KB reindex 前端合同与生产 markup 隔离 smoke。

### 精确命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | `0` | 通过 |
| `node --test frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` | `0` | `18 passed`，`0 failed`，`0 skipped` |
| `node --test frontend/contract-tests/context-meter-and-kb-count.test.mjs frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` | `0` | `26 passed`，`0 failed`，`0 skipped` |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_paper_contract.py` | `0` | `23 passed in 0.21s`，无 skip |
| `.venv/bin/python scripts/check_test_naming.py` | `0` | 无 spec/task 数字违规 |
| `.venv/bin/python scripts/check_test_layout.py` | `0` | `test layout: ok` |
| `git diff --check -- frontend tests/frontend` | `0` | 通过 |

受影响 Python 文件 collect-only 仍为 `23 tests collected`，无 collecting error；本轮没有运行 backend pytest 或全仓 `pytest`。

### 新增 P1 覆盖

- 只有 HTTP `202` 且有非空 `task_id` 才显示排队成功；`202` 缺 ID、`200` 带 task id、`204` 空 body、`202` malformed JSON 均显示失败，不伪造成功。
- `document_id` 级 in-flight lock 跨列表重渲染/新按钮保持；失败后释放允许重试；不同 document ID 可并行各发一条 POST。
- 既有 canonical-only、legacy `paper_id` fallback、缺 ID 零 POST、409 busy、503 服务 message、同步双击 guard 与 failure-label 契约继续通过。

### 最终生产 markup 隔离 Chromium smoke

使用临时 localhost 静态服务器映射真实 `frontend/index.html`/`/assets/*`，Playwright 拦截全部 `/api/**`，不触发真实生产请求。退出码 `0`、无 skip、无 page error：

```text
production_markup: app=61, styles=61, map=21
data_document_id: d4dfd2a620384ad5bece27320661f8f0
post_count: 1
post_url: /api/kb/documents/d4dfd2a620384ad5bece27320661f8f0/reindex
post_body: {"chunker":"all"}
status: 已提交重建：...（v1 + v2，任务 task-final-smoke 已排队）
draft_untouched: true
page_errors: []
```

### 当前前端结论

当前 Spec018 KB reindex 前端范围：**PASS（Node 18/18；合跑 26/26；Python 23/23；production markup smoke PASS；0 skip）**。该结论仅覆盖前端回归；主会话仍需完成 root 指定的真实单文档 API E2E 与任务/v1-v2 终态证据后，才能决定整体验收状态。最新日志：`.codebuddy/agent-logs/spec-018/task-00/frontend-tester/20261026-012859.md`。
