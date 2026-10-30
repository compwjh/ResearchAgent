# Spec 030 Task 09 前端实施报告

日期：2026-10-30  
角色：frontend-dev  
范围：仅报告工作区前端与对应前端契约测试；未修改后端、Spec、部署配置或 Git 状态。

## 实施内容

- 在既有报告卡片增加发布状态、报告阶段/实测耗时、质量指标、稳定原因码和未发布版本重试入口。
- 仅在 `report-quality-v1` 与 `count_method=report-quality-v1` 均存在时显示 CJK 正文、有效逐篇、比较、支持发现、定向改写与证据等级；不完整的历史 JSON 标记为“旧版，未按本质量合同核验”。
- 每个新报告提交创建 UUID `Idempotency-Key` 并暂存到本地存储；提交结果不确定时重试复用同一 key，成功受理后清除；后续用户主动重试生成新 key。
- 将 POST 响应视为受理信号，读取服务端 `report_url` 并轮询版本 JSON；只有 `completed + published=true + report-quality-v1 pass` 才显示“正式发布”。离开后重新打开任务时，沿用任务报告 GET 与既有事件游标恢复 generating 状态。
- 版本切换时重新取得对应版本的 artifact 列表。明确 `published=false` 或质量不通过时不渲染下载链接；保留旧版报告选择和已有发布版本的下载。
- 报告事件按合同阶段映射为安全文案，显示版本、改写轮数、实测耗时与稳定原因码；动态内容使用 `textContent` 和既有安全 Markdown 渲染。

## 变更文件

- `frontend/research-tasks.js`
- `frontend/index.html`（资源版本升至 `research-tasks.js?v=17`、`styles.css?v=67`）
- `frontend/styles.css`
- `tests/frontend/test_evidence_report_frontend_contract.py`
- `tests/frontend/test_research_session_workspace.js`
- `tests/frontend/test_report_action_race.js`

## 前端自查

1. 新增 `research-report-*` DOM class 都有 CSS 规则，样式限定在 `#research-view`。
2. `research-tasks.js` 与 `styles.css` 均已同步更新 `index.html` 缓存版本。
3. `frontend/research-tasks.js` 未出现 `innerHTML`；报告状态、质量和原因码都通过 `textContent` 写入。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/research-tasks.js` | 0 | 语法通过 |
| `node tests/frontend/test_research_session_workspace.js` | 0 | 质量指标、正式/草稿/旧版状态、事件阶段/耗时、原因码及未发布/错误质量元数据下载门禁通过 |
| `node tests/frontend/test_report_action_race.js` | 0 | 任务/版本竞态通过；新增网络重试同 key、202 pending、GET 追踪至发布、malformed quality async poll 与 v2→legacy v1 隔离场景通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/frontend/test_evidence_report_frontend_contract.py -q` | 0 | 3 项静态契约测试通过 |
| `git diff --check` 及 CSS class、缓存版本、`innerHTML` 核对 | 0 | 无空白错误；样式/版本/XSS 自查通过 |

本 worktree 未配置本地 `.venv`，静态契约测试使用同一工作区的可用虚拟环境运行。

## 残项

- 未启动服务或执行浏览器视觉验收；本 Task 分派范围要求前端定向测试，不包含部署。需由后续验收角色在当前部署上验证自然语言主流程、报告事件恢复与实际 artifact 可见性。
- 未运行后端 pytest 或全量回归。

## 独立评审跟进

- 统一使用 `isQualityValidated` 判断正式发布：报告必须同时为 `completed`、`published=true`、质量 schema/count method 均为 `report-quality-v1` 且 `quality_validation.status=pass`。异步 poll 和提交读取路径不再单独相信 `status=pass`。
- 版本选择只使用目标版本的 canonical JSON、Markdown 与 artifact 结果构造 `state.report`，不再把当前版本对象 spread 到另一版本；这样旧版缺少质量/发布字段时显示未核验并清空质量指标。
- 增加恶意/陈旧 schema 的异步 poll 断言、v2→legacy v1 版本隔离断言；保留并发版本请求迟到响应不覆盖当前版本的测试。
- legacy 下载兼容现在只适用于完全没有 `quality_validation` 字段的 completed 旧报告；只要质量字段存在，就必须由 `isQualityValidated` 验证，不能因 `published` 缺失而走旧版回退。新增质量通过但发布字段缺失、malformed quality 且发布字段缺失、显式 `quality_validation: undefined` 均不可下载，同时保留纯旧版下载断言。
