# Spec027 Task05 前端交接报告

## 状态

**前端实现完成；Task05 后端动态事件合同已由固定样本复验，等待 Task06 集成验收。**

本轮严格按 `frontend-dev` 边界执行：只新增/修改 `frontend/research-tasks.js`；未修改 `backend/**`、`AGENTS.md`、`.codebuddy/**`、长期模型配置或前端 HTML/CSS。当前工作树中的其它后端、文档、`frontend/index.html`、`frontend/styles.css` 和测试变更属于本轮开始前已存在的并行工作，未由本交付代行处理。

## 实现内容

- 消费安全事件摘要并以白名单字段呈现：`coverage.gaps/round`、`plan_version`、任务/Worker 状态、`model_tier`、`resolved_model`、`worker_slot`、`selected_count`、候选数、稳定错误码、证据等级和报告限制。
- 计划区新增计划版本历史：首轮显示 `v1`，后续版本显示 `Re-plan · 计划 vN`；不覆盖既有事件，仍按 `event_seq` 顺序保留。
- 执行摘要新增真实终态、当前计划版本、覆盖缺口、Re-plan 次数、模型升级、停止/失败原因和证据摘要。
- 对 `BUDGET_EXCEEDED`、`SOURCE_DEGRADED`、`SOURCE_UNAVAILABLE`、`RESOURCE_PROBE_FAILED`、`MODEL_ESCALATED` 及可选的无新增证据稳定码/停止原因做安全文案映射；未知码保持通用兜底，不展示原始内部文本。
- 报告限制按已知摘要字段呈现覆盖缺口、来源失败/降级数量、证据范围、预算耗尽和无新增证据；未知限制只显示“另有未展开的限制摘要”。
- 论文选集显示 `catalog` / `abstract` 证据标记；只显示 `catalog_paper_id`、相关性、facets 和时间，不消费或展示 title/abstract。
- 保留 Task04 已冻结边界：正整数 `event_seq` 去重/推进游标、合成 `terminal` 不推进游标、断线按 `after_seq` 重连、显式取消、报告白名单、`textContent`/DOMPurify 安全渲染、无暂停/恢复、普通聊天不创建研究任务。

## 兼容策略

- 当前详情/报告/事件若缺少新增字段，页面显示“等待事件”“暂无 Re-plan/升级事件”或通用限制摘要，不根据缺失字段推导结果。
- 只读取已知安全摘要字段；未知 payload 字段不展开，不序列化整个对象，不显示 Prompt、思维链、原始论文 title/abstract 或异常文本。
- 报告 Markdown 继续沿用 Marked → DOMPurify → DOMParser；依赖不可用或解析失败时回退纯文本。

## 后端合同现状与未验证项

后续后端增量已补齐 coverage 缺口触发的有界 Re-plan：最多两轮、计划版本不可覆盖、旧 WorkItem 保留；并已接入阶段边界软预算 `budget_exhausted` 停止语义，以及安全的 `MODEL_ESCALATED` model 事件投影。对应后端合同测试已通过。

当前仍未完成的 Task06 收口项为：

1. 固定样本已证明真实 `ModelRouter` 的 fast→重试→strong 算法和安全升级事件投影；真实 Ollama HTTP 探测因当前环境 `Operation not permitted` 延期，未伪造推理成功。
2. 固定样本已证明真实 `CatalogSearchAdapter` 惰性装配既有 Spec015 `CatalogSearchGraph`/`CatalogRagAdapter`，无 source 时 `SOURCE_DEGRADED`，固定 source 时可返回目录 ID；未伪造 USENIX/DBLP 网络成功。
3. 未执行真实 USENIX/DBLP/Ollama、真实浏览器桌面/390px smoke、跨端 Task05 端到端验收或全量回归；这些留给 Task06。

## 验证命令与结果

| 命令 | 结果 |
|---|---|
| `node --check frontend/research-tasks.js` | 退出码 0 |
| `git diff --check -- frontend/research-tasks.js` | 退出码 0 |
| `rg -n 'innerHTML|\\bpause\\b|\\bresume\\b' frontend/research-tasks.js` | 无匹配 |
| 研究动态 class 反向核对 | `research-plan-label`、`research-timeline`、`research-event`、`research-summary-item` 均已有样式 |
| `tests/test_frontend_*.js` 逐文件运行 | 5/5 通过 |
| `.venv/bin/python -m pytest tests/test_frontend_*.py -q` | **101 passed** |
| 后端 pytest | 未运行，符合纯前端改动边界 |

## 风险与交接

- 后端现在已发出 Re-plan、模型升级、预算耗尽和无新增证据安全摘要；前端仍对缺少字段保持兼容，页面不会展示原始 Prompt/论文文本。
- 前端没有新增测试文件；本轮复用了现有 Node 合同和 Python 前端静态合同。Task06 应补真实浏览器与跨端动态事件验收，并核对新增后端字段是否仍落在本报告的白名单范围内。
