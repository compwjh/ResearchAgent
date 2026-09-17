# Spec030 Task05 前端交接报告

## 结果状态和摘要

`PASS`。研究工作台现在展示版本化证据矩阵、显式覆盖缺口和只读报告视图；Markdown、HTML、JSON 通过统一版本端点读取，Markdown/JSON 提供只读下载。引用 manifest 编号渲染为键盘可操作按钮，展开后显示论文、证据等级、页码、chunk 定位，并复用现有知识库切片检查器跳转。动态报告/论文内容只经 `textContent`、DOMPurify + DOMParser 或 `pre` 文本边界，不使用 `innerHTML`。

## 改动文件

- `frontend/index.html`
- `frontend/research-tasks.js`
- `frontend/styles.css`
- `tests/test_spec030_frontend.py`

## 测试命令/退出码/结果

- `node --check frontend/research-tasks.js` — 退出码 `0`。
- `.venv/bin/python -m pytest -q tests/test_spec030_frontend.py tests/test_frontend_spec034_task08_contract.py tests/test_frontend_spec034_task09_contract.py tests/test_frontend_conversation_contract.py` — 退出码 `0`，`35 passed`。
- `git diff --check` — 退出码 `0`。

## 产物路径

`docs/sdd/plans/030/artifacts/task-05/frontend-report.md`

## 决策依据

- 证据矩阵读取 `/api/research-tasks/{id}/evidence-matrix`，按 canonical `cells` 展示结论/论文/维度/关系，并将 `limitations` 原样作为显式缺口；缺口单元格不补写事实。
- 报告先读取兼容的 `/report`，再读取 Task04 的 `/reports/{version}?format=json|markdown|html`，以兼容旧报告并保证三种视图共享版本和引用 manifest。
- 引用编号只从 manifest 建立 `citation_no → evidence_id` 索引；详情显示 `paper_id`、Evidence 等级和 locator，全文 locator 通过现有 `__kbInspectionController` 选择文档、chunker 并定位 chunk。
- 下载链接只允许经过既有 artifact 路由校验或严格的版本化报告路由；没有报告编辑入口，也不向页面写入原始 HTML。
- 报告脚本和样式资源的缓存版本已分别更新至 `research-tasks.js?v=9`、`styles.css?v=54`，保留旧版本合同标记。

## 风险阻塞

- Task05 未运行全量后端回归、真实服务部署或浏览器端到端 smoke；这些属于 Task06 收口范围。
- 后端当前没有独立的报告版本列表端点，版本选择器展示当前已知版本；切换到已知版本后按版本端点读取，历史版本列表扩展需后端提供列表接口。
- 旧 `/report` 响应若没有 canonical manifest，矩阵仍可展示，但编号详情要等版本化 JSON 可用；这避免前端猜测引用编号。

## 主 Agent 后续动作

读取本报告并检查前端评审合同（DOM/XSS/键盘/窄屏/资源版本），随后执行 Task05 前端验收；Task06 统一做全量回归、浏览器 smoke、启动和部署验证，并更新 Spec030 状态台账。

## 开始/结束/总耗时

- 开始：`2026-09-17T02:38:00+08:00`（约）
- 结束：`2026-09-17T02:45:49+08:00`
- 总耗时：约 `8 分钟`

## 模型和工具统计

- 模型：Luna high（临时分派）
- 工具：文件读取、`apply_patch`、`node --check`、定向 pytest、`git diff --check`
- 网络/真实数据：未使用
