# Spec 030 Task 09 前端评审

日期：2026-10-30  
评审角色：frontend-reviewer  
范围：本次 `frontend/**` 差异及对应前端测试；未评审 `backend/**`，未运行后端测试、全量回归、部署或 Git 操作。

## 结论

**PASS / Approve。** 当前差异没有未解决的 CRITICAL 或 HIGH 问题。首轮与窄复审阶段记录的三项 HIGH 缺陷均已由作者修复，并在最终差异上复核通过；问题历史保留如下。

## 历史发现与修复复核

| 历史发现 | 当前修复与证据 | 当前状态 |
|---|---|---|
| 正式发布门禁只看 `quality_validation.status=pass`，未要求 `schema_version`、`count_method` 同为 `report-quality-v1`，可把字段不完整的版本标成已发布。 | [research-tasks.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/research-tasks.js:301) 定义完整 schema 检查；`isQualityValidated` 同时要求 completed、published=true 与质量 pass。生成和轮询均复用该判定（约 312、1974、2139 行）。 | 已修复；畸形质量对象不再正式发布或提供下载。 |
| 选择旧报告版本时把 `previousReport` 与目标版本合并，缺质量字段的旧版会继承当前版的通过状态和指标。 | 版本选择现从目标 `canonical` 构造 `state.report`，不继承前一版字段（[research-tasks.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/research-tasks.js:2895)）。Fake DOM 复现现返回旧版未知且不显示质量指标。 | 已修复。 |
| 下载兼容分支把所有 completed 且 publication 字段缺失的响应当作旧版，可能让含质量字段但缺少 published 标记的版本出现下载链接。 | [research-tasks.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/research-tasks.js:317) 现在只对质量字段完全不存在的历史版本保留兼容；质量合同存在时必须通过完整发布门禁。测试覆盖畸形/缺发布标记与纯旧版兼容（`test_research_session_workspace.js:107–130`）。 | 已修复。 |

## 前端四项必守

| 检查项 | 结果 | 代码依据 |
|---|---|---|
| DOM / CSS 契约 | PASS | 新增反馈区 ID/class 在 [index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:331)、[research-tasks.js](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/research-tasks.js:2761) 与 [styles.css](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/styles.css:3719) 双向对应。新增 CSS 钩子均限定在 `#research-view`。 |
| 资源版本 | PASS | `research-tasks.js?v=17` 与 `styles.css?v=67` 已同步递增，见 [index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:8) 和 [index.html](/Users/wjh/.codex/worktrees/map-usability/ResearchAgent/frontend/index.html:804)。 |
| XSS | PASS | `frontend/research-tasks.js` 无 `innerHTML`；新反馈字段以 `textContent` 写入（约 2753–2770 行），报告正文仍使用既有安全 Markdown / HTML 渲染路径。 |
| CSS 作用域 | PASS | 新增样式均以 `#research-view` 开头，见 `frontend/styles.css:3719–3727`；没有裸全局选择器。 |

## 指定行为核对

- POST 的 202 只显示“已受理 / 生成中”；完成状态要求版本已发布且质量合同完整通过。测试覆盖 202 pending、随后轮询至发布。
- 幂等 key 使用 UUID 并持久化；提交结果不确定时重试复用同 key，收到受理后清理；用户主动重试使用新 key。`test_report_action_race.js` 覆盖同 key 网络重试和新 key。
- 版本竞态由 request ID 守卫；切换任务时递增 task generation 并取消定时器。正在飞行的轮询响应再检查 poll identity 和 task generation，离开当前任务后不写入状态。
- 阶段、版本、改写轮数、实测 elapsed 与稳定原因码通过安全文案显示；离页重进从当前报告恢复 generating 并重新启动版本轮询。
- 草稿和质量失败报告不显示 Artifact 下载链接；仅纯旧版（没有 `quality_validation` 字段）继续保留历史下载兼容。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/research-tasks.js` | 0 | 语法通过 |
| `node tests/frontend/test_research_session_workspace.js` | 0 | 前端会话/质量/旧版/下载契约通过 |
| `node tests/frontend/test_report_action_race.js` | 0 | 任务隔离、版本竞态、202、幂等重试通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_evidence_report_frontend_contract.py -q` | 0 | 3 passed |
| `git diff --check -- frontend/index.html frontend/research-tasks.js frontend/styles.css tests/frontend/test_evidence_report_frontend_contract.py tests/frontend/test_report_action_race.js tests/frontend/test_research_session_workspace.js` | 0 | 无空白错误 |

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | info |
| LOW | 0 | note |

Verdict: **APPROVE** — 当前差异无未解决的 CRITICAL 或 HIGH 问题。

评审日志：`.codebuddy/agent-logs/spec-030/task-09/frontend-reviewer/20261030-125831.md`
