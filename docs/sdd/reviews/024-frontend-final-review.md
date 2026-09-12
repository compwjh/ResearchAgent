# Spec024 Task05 前端最终独立复审

## 复审范围

- Spec：`docs/sdd/specs/024-visible-reasoning-controls.md`
- Task：`docs/sdd/plans/024/task-05-review-regression-deploy.md`
- Repair 交接物：`docs/sdd/plans/024/artifacts/task-05/frontend-repair-report.md`
- 最终实现：`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`
- 合同测试：全部前端合同定向测试（9 个测试文件）

本轮只评审前端，不修改业务代码，不运行后端全量 pytest，不执行 reset/stash/clean/push/merge。

## 结论

**GO（前端最终复审通过）**。

前一轮发现的 event_seq P1 已由 repair agent 修复并经本轮独立复核；当前 P0=0、P1=0、P2=0。Task05 指定的五档选择/能力降级、当前会话 PATCH 与新会话默认、用户→思考→正文顺序、自动折叠/重开、历史恢复、事件终态、XSS/innerHTML、ARIA/键盘和 `?v=35` 资源版本均通过静态核对。

## 前一轮 P1 复核：已修复

### P1-1：event_seq 校验绕过重复 meta、非法序号和终态缺口 — 已修复

- `frontend/app.js:1818-1833` 现在要求首个 `meta` 的 `event_seq` 为 1，并先经过 `acceptConversationEvent()`；后续 meta 也统一经过该守卫，重复/迟到 meta 不会重复创建 assistant DOM。
- `frontend/app.js:668-697` 对缺失、非法或非正整数序号设置粘滞 `sequenceGap`/`terminal`/`interrupted`，显示“事件流中断”并拒绝事件，不再接受无序号事件。
- 同一守卫在 `frontend/app.js:686-694` 对 `done/error` 终态也检测 gap；终态事件可用于收口，但 `frontend/app.js:1894-1903` 依据 `sequenceGap` 强制最终状态为 `interrupted`，不能恢复为 completed。
- abort 终态仍由 `frontend/app.js:1361-1377` 设置 `doneSeen`、`streamActive=false` 并停止推理/处理动画；之后的 token/reasoning/meta 由序号/终态守卫丢弃。

Repair report 新增的 `tests/test_frontend_task05_repair_contract.py` 已覆盖 meta 序号接收、非法序号拒绝和 final gap 粘滞中断；本轮重新执行并通过。

## Task05 指定范围核对

### 五档选择、能力降级与会话默认

- `frontend/index.html:86-94` 提供 off/low/medium/high/xhigh 五档。
- `frontend/app.js:368-390` 读取 reasoning-options；能力接口失败只启用 off 并将默认值设为 off。
- `frontend/app.js:393-417` 对当前会话执行 PATCH；失败时恢复选择器、`lastEffort` 和新会话默认值。
- `frontend/app.js:1401-1405,1423-1425` 分别恢复当前会话档位和新会话继承值；`frontend/app.js:1805,1851` 将本轮档位冻结进请求和 meta。

### 用户→reasoning→正文、自动折叠/重开与历史恢复

- `frontend/app.js:723-749` 先挂载 assistant bubble/answer，再把历史 reasoning 插入 answer 前；历史 reasoning 为空/null 时不创建空面板。
- `frontend/app.js:571-625` 创建独立 reasoning 面板；`frontend/app.js:1880-1885` 在 reasoning_completed 或首正文 token 时终止并折叠；`frontend/app.js:614-619` 支持键盘可操作的 toggle 重新展开。
- `frontend/app.js:629-666` 更新 `aria-busy`、摘要和折叠状态；`frontend/styles.css:94-109` 覆盖 running/completed/failed/interrupted 和 reduced-motion 样式。

### XSS/innerHTML、ARIA/键盘与资源版本

- `frontend/app.js:489-561` 维护跨 chunk carry，过滤 think/analysis/INST、角色/控制分隔符和不可显示控制字符；reasoning 内容使用 `textContent`/`createTextNode`（`545,558,605`）。
- 正文 Markdown 继续经 `renderMarkdown()` 的 DOMPurify（`frontend/app.js:3644-3653`）；本 Task 未新增 reasoning `innerHTML` 写入。
- 选择器 `frontend/index.html:88` 和 reasoning toggle `frontend/app.js:582-604` 均为原生键盘控件，并维护 `aria-expanded`/`aria-busy`。
- `frontend/index.html:8,505` 的 `styles.css`/`app.js` 资源版本已递增到 `?v=35`。

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | PASS |
| `.venv/bin/python -m pytest -q tests/test_spec024_frontend_contract.py tests/test_frontend_conversation_contract.py tests/test_frontend_management_contract.py tests/test_frontend_paper_contract.py tests/test_frontend_skill_tool_contract.py tests/test_frontend_task05_repair_contract.py tests/test_frontend_task06_mobile_contract.py tests/test_frontend_task09_project_tree_contract.py tests/test_frontend_task10_system_rule_contract.py` | 0 | PASS，96 passed |
| `git diff --check -- frontend tests/test_spec024_frontend_contract.py tests/test_frontend_task05_repair_contract.py` | 0 | PASS |

未运行后端 pytest、全量回归或真实 Ollama/browser smoke；这些属于 Task05 主 Agent 的跨端收口范围。

## 交接与主 Agent 后续动作

1. 将本报告作为前端最终复审 GO 证据，汇总后端最终复审与跨端验收。
2. Task05 继续执行唯一一次全量回归、部署和运行时 smoke；前端静态门禁无需追加修复。

## 产物与日志

- 本报告：`docs/sdd/reviews/024-frontend-final-review.md`
- Repair 报告：`docs/sdd/plans/024/artifacts/task-05/frontend-repair-report.md`
- 复审日志：`.codebuddy/agent-logs/spec-024/task-05/frontend-reviewer/20260912-014812.md`

## 时间与模型

- 本轮开始：2026-09-12（Asia/Shanghai）
- 本轮结束：2026-09-12（Asia/Shanghai）
- 模型：临时 Luna high
- 未执行业务代码修改、reset/stash/clean/push/merge
