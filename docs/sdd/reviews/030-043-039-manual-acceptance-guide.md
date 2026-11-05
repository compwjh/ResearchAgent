# Spec 030 / 043 / 039 人工验收指引（2026-11-05）

> 主会话纯文档代行落盘。目标是让**未读上下文的人**也能照着点完：每步点什么、点完显示什么、
> 何时等待、等待时看到什么、下一步、失败如何恢复、去哪里看产物。
> 本文件不新增验收口径，只把已落盘的真实案例整理成可复现步骤。

## 0. 通用前置（三个 spec 都要做）

- 服务地址：<http://127.0.0.1:8000/>，先确认 `/api/health` 返回 200。
- 若服务已停：`PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`（或按 `deploy/README.md`）。
- **必须硬刷新**：`Cmd+Shift+R`（Windows/Linux `Ctrl+Shift+R`）。当前静态资源版本为
  `app.js?v=67`、`literature-maps.js?v=40`、`literature-maps.css?v=26`。
  **只改 URL hash 不会重载文档**，页面会继续跑内存里的旧脚本——这是此前「改了却测不到」的主因。
  Console 自检：

  ```js
  [...document.querySelectorAll('script[src]')].map(s => s.src).filter(s => s.includes('literature-maps.js'))
  // 期望 ["http://127.0.0.1:8000/assets/literature-maps.js?v=40"]
  ```

- 刷新后默认停在「对话」视图；`#literature-maps-view` 不会自动切视图，需手动点左侧导航（已知限制，见 §2）。

---

## 1. Spec 030 — 深度研究报告（跨论文证据矩阵 / 内容质量）

**主路径是自然语言聊天入口，不能用表单或后端直调替代。**
完整真实案例与截图：`docs/sdd/plans/030/2026-10-31-manual-acceptance.md`。

| 步 | 操作 | 点击后提示 / 等待条件 |
|---|---|---|
| 1 | 打开首页，点左上 `+ 新建对话` | 出现空白对话，顶部「模式」为 `Normal` |
| 2 | 底部模型选 `deepseek:deepseek-flash`；「思考档位」选 `关闭` | 选择器显示所选值 |
| 3 | 在输入框粘贴自然语言研究主题（完整原文见 `docs/sdd/plans/030/artifacts/20261031-methods-e2e/request.json`，主题为 `security research methodology` 的 USENIX Security 2022 实证评估方法比较） | 输入框显示全文；占位文字仍是「给 Ollama 发消息」属正常 |
| 4 | 点 `发送`（↑） | 出现「研究计划」卡：先 `running` → `completed`，随后状态 `plan_pending_approval`；**等到不再 running 再继续**，不要重复发送 |
| 5 | 在 Plan v1 卡片点 `批准计划` | 左侧「研究通知」出现任务进度；**等待条件**：等通知显示「研究已完成 · 报告 v1」。本次实测全程约 8 分 52 秒、report 阶段约 294 秒，是实测值不是倒计时，**按页面状态推进** |
| 6 | 在左侧选中与当前 Session 匹配、带 `已完成` 的任务卡 | 右栏应显示 `报告 v1 · 已完成`、`正式发布`；不要选相邻旧 LLM 卡 |
| 7 | 右栏切换 `Markdown` / `HTML` 标签，再点三个下载链接 | 两种格式均可读且属同一 v1；Markdown / HTML / citation manifest 下载均 HTTP 200 |

**成功判据**：报告正式发布；正文 CJK ≥ 1500（本次 3020）；5 篇逐篇分析、4 项比较、5 条 supported findings；Citation 5/5 有效；右栏状态与 API `report_version` 一致。

**失败恢复**

- 早期 `REPORT_NOT_READY` / 404 或 `report generating`：回「研究通知」继续等**同一 task**，不要重建任务。
- 卡片显示「研究失败，可重试（第2次）」：先确认是当前任务，再按卡片重试操作继续。
- 服务不可达：记录当前对话与 task ID，按 §0 命令重启，确认健康后从当前任务继续。
- 正文已完成但发布 / 下载失败：不要把草稿当正式产物，保留报告版本与 Artifact ID 交维护者核查。

**产物路径**：`docs/sdd/plans/030/artifacts/20261031-methods-e2e/`（`report.md`、`report.html`、`citations.json`、`request.json`、`execution-manifest.json`、`http-execution-record.json`、`download-verification.json`、浏览器截图）。

---

## 2. Spec 043 — 文献地图（含第四轮 UX 修复）

更细的运行时证据：`docs/sdd/reviews/043-node-style-disclosure-live-e2e.md`。

| 步 | 操作 | 点击后提示 / 等待条件 |
|---|---|---|
| 1 | 左侧点 `⌘ 文献地图` | 「我的地图」列出 7 张（默认停在对话视图，必须手动点） |
| 2 | 点 `API E2E graph attention networks r2` | **等画布出现 28 个节点**、标题栏更新 |
| 3 | 点「节点样式」展开，**不要动滑块**，点 `应用外观` | 提示 `外观未变更，已收起节点样式设置。`；详情立即消失，只剩「节点样式」标题行 |
| 4 | 再展开 → 拖「填充透明度」→ 点 `应用外观` | 提示 `节点外观已保存。`，详情同样收起；再次展开能看到新值 |
| 5 | 点 `多选模式` → 点画布上 1 个节点 → 点任一色板 → 点 `应用到 1 篇` | 提示 `颜色已保存，设置面板已收起。`；颜色面板消失，「已选 1 篇」与「退出多选模式」仍在 |
| 6 | 再点另一个节点 | 颜色面板重新出现，按钮变 `应用到 2 篇`（证明不是「永远打不开」） |
| 7 | 点 `退出多选模式` | 回到普通视图 |

**成功判据**：两个「应用」按钮点击后设置详情都真实消失（computed style `display:none` / 矩形 `0×0`），状态文案正确；多选上下文不被清空。

**失败恢复**：保存冲突 / 网络错误时面板**故意保持展开**、草稿保留，按提示核对后重试，**不要刷新页面**（刷新会丢草稿）；若按钮行为与上述不符，先按 §0 硬刷新确认拿到 `v=40`。

**刻意设计，不算缺陷**：成功后不退出多选模式；失败 / 409 / 结果未确认时面板不收起。

**产物路径**：`docs/sdd/reviews/043-node-style-disclosure-live-e2e.md`、`043-node-style-disclosure-frontend-review.md`、`043-node-style-disclosure-frontend-regression.md`。

**自动化复跑**：

```bash
cd /Users/wjh/ResearchAgent
node --check frontend/literature-maps.js
for f in tests/frontend/*.js; do node "$f" || exit 1; done
.venv/bin/python -m pytest tests/frontend/test_frontend_node_style_visibility.py tests/frontend/test_frontend_selection_color_palette_ux.py -q
```

---

## 3. Spec 039（`039-api-e2e-manual-acceptance-protocol`）— 验收协议本身

这个 spec 交付的是**协议 / Skill / 模板**，所以人工验收 = 按它的「十项准备度检查」逐项打勾，
并以**自然语言 Intake 为主路径**跑一个核心成功案例；表单或直接 JSON 只可用于诊断兜底。

> 历史注意：`docs/sdd/reviews/039-acceptance-review.md` 曾给出 **BLOCKED**（当时报告产物缺标题、摘要、
> 关键词、研究方法与安全比较，内容质量不合格）；后续运行 D/E 补齐后状态转为 `待人工验收`。
> 本次验收重点因此是**报告内容质量 + 主路径可复现性**，而不只是「任务能跑完」。

### 3.1 逐步操作（核心成功案例，以 Spec030 的真实运行为示范）

| 步 | 操作 | 点击后提示 / 等待条件 |
|---|---|---|
| 1 | 按 §0 确认服务 `/api/health` 200 与静态资源版本 | 健康检查通过 |
| 2 | 新建对话，在**聊天框用自然语言**提交完整研究需求（用 §1 第 3 步的原文） | 不能用表单或直接 JSON 代替；页面出现研究计划卡 |
| 3 | 观察 Intake / 计划阶段 | 显示 `running` 等处理中提示，不是静态「处理中」；记录每条状态文案 |
| 4 | 点 `批准计划` | 任务状态从 `plan_pending_approval` → `running/queued` → `completed`；等通知出现完成提示 |
| 5 | 打开报告 | 核对标题、摘要、关键词、研究方法、安全问题比较均存在；Markdown / HTML 可读 |
| 6 | 记录证据 | 请求、响应状态码、关键响应、实体 ID（task / session / report / artifact）、最终 `completed` + `published`、产物路径 |
| 7 | 额外跑一个**失败或恢复场景** | 例如不批准计划后重试、或等待早期 404 后继续等同一任务；确认用户能按提示继续 |

### 3.2 十项准备度检查（逐项打勾，至少 9/10 通过才可交付）

1. 服务启动并可访问；
2. 真实 API 创建入口成功；
3. 主路径参数被正确解析（主题 / 年份 / 来源 / 篇数约束进入计划）；
4. 任务状态从初始态推进；
5. 前端显示处理中提示（阶段 / 心跳，非静态文案）；
6. 用户知道何时需要点击或等待；
7. 核心业务产物真实生成（报告 + Artifact，内容合格）；
8. 失败状态有可操作恢复；
9. 页面状态与 API 状态一致；
10. 步骤文档可由未读上下文的人复现。

**阻断条件**：自然语言 Intake 失败时，不得把表单成功当作主路径成功，须记录为产品路径缺陷并阻止交付；
不得有未解决的 P0/P1、API E2E 失败或关键产物缺失；成功案例必须是**当前部署版本**。

**产物路径**：`artifacts/spec032-api-e2e-success.md`、`artifacts/spec032-manual-acceptance.md`、
`artifacts/spec032-readiness-matrix.md`、`docs/sdd/plans/039/`（`README.md` 与 task-02～07）、
`docs/sdd/plans/030/artifacts/20261031-methods-e2e/`（最新一次合格报告）。

---

## 4. 三个 spec 的验收顺序建议

1. 先按 §0 硬刷新 + 健康确认（一次性）。
2. §2 文献地图（最快，约 2 分钟，纯 UI）。
3. §1 / §3.1 深度研究自然语言主路径（约 9 分钟，可同时覆盖 030 与 039 的核心成功案例）。
4. 最后按 §3.2 十项检查打勾并记录结论。
