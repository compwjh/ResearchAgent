# Spec 030 Task 10：人工验收案例（Security Research Methodology）

## 本次验证基线

- 服务地址：<http://127.0.0.1:8000>，端口 `8000`；2026-10-31 03:58:30 UTC 的 health 响应为 HTTP 200、`status=ok`。
- 本次运行版本：部署 commit `44752b60`；Task `f19f879e4b05587ba0246768fa15cf46`；Session `b4dfc9390b884b86b2d2b1045321625d`；Plan v1；Report `4b7212ea-7f22-40ae-bf32-1b788f9a466b` v1。
- 运行实际使用 `deepseek:deepseek-flash`，reasoning effort `off`；入口截图的选择器显示该 DeepSeek 模型、`思考档位`为`关闭`。本地 Qwen 能力缓存另有未解决记录；此案例使用 DeepSeek，不改动模型配置，也不把 Qwen 缓存问题当作本案例失败。
- 新建对话页顶部模式显示 `Normal`。无需手动切换研究模式；本次自然语言消息触发了 Intake 和研究计划。输入框真实占位仍显示 `给 Ollama 发消息`，但本次 DeepSeek 选择与实际发送成功；这是待修正的旧占位，不要因此切回或改配 Ollama。
- 本次从开始到正式发布约 8 分 52 秒，其中 report 阶段约 294 秒。它是一次实测值，不是固定倒计时；按页面状态推进，不按时间猜测完成。

## 操作步骤

### 1. 打开新对话并设定本次验证参数

1. 打开 <http://127.0.0.1:8000>。若服务已在运行，直接使用；若服务停止，在项目目录按 `deploy/README.md` 的命令启动：`./deploy/start.sh -d`。本次运行监听端口 8000。
2. 左上点击真实控件 `+ 新建对话`。
3. 保持页面顶部 `模式`为 `Normal`。
4. 在底部模型选择器选 `deepseek:deepseek-flash`。打开 aria-label 为 `思考档位` 的选择器，选 `关闭`（请求中的值为 `off`）。
5. 在消息输入框粘贴以下原始自然语言输入。该框当前显示的占位是 `给 Ollama 发消息`，仍是本次验证使用的输入框。

```text
帮我做一个深度研究，主题是 security research methodology，目标是比较 USENIX Security 2022 论文中的实证评估方法，涵盖测量研究、受控实验、用户研究和方法审计，比较研究对象、样本、评价指标、可重复性与证据限制。时间范围是2022-2022，来源限定 USENIX，目标论文数为5篇，至少5篇。本研究允许不同安全领域的论文，重点是各论文如何设计和验证研究，不要求它们解决同一种安全机制。报告使用中文，正文至少1500个中文字符，逐篇分析，包含跨论文比较和至少三条由多篇证据支持的综合发现。只依据取得的证据，不补写摘要未说明的实验细节。
```

6. 点击发送控件（aria-label `发送`，界面显示 `↑`）。本次 SSE 证据显示 `研究计划`步骤先为 `running`，随后为 `completed`；正常情况下等待该处理状态结束，并等待页面出现首轮计划。

**点击后提示与等待条件：** 计划卡显示目标“比较 USENIX Security 2022 论文中的实证评估方法”、Plan v1，随后状态进入 `plan_pending_approval`。若页面仍显示“正在生成研究计划”，继续等待，不重复发送相同请求。

### 2. 审批计划并等待研究完成

7. 在 Plan v1 卡片中点击实际控件 `批准计划`。`browser-plan-approval.jpg` 直接显示该按钮和 `待审批` 状态；该截图来自独立 Intake-only UI 核对，没有点击按钮或创建第二个研究任务。当前正式运行的计划审批由 `02-approval.json` 记录为 HTTP 200、`plan_version=1`、状态 `approved`。
8. 批准后到左侧 `研究通知` 查看该任务进度。等待匹配此对话/任务的完成通知；本次通知 `#230` 显示研究已完成，报告为 v1。不同复现运行的通知编号会变化，应选本次最新且匹配的任务，不要固定寻找 `#230`。
9. 当页面/右侧显示 `报告 v1 · 已完成` 与 `正式发布` 后再打开报告。报告状态必须是 completed 且 published；只看到 task 正在运行、report generating 或矩阵尚未就绪时继续等待。

**实际等待证据：** 本次早期 report 检查在 03:45:46 UTC 返回 HTTP 404，后续 03:48:11 UTC 返回 HTTP 200 且仍在生成，最终 03:53:35 UTC 返回 completed/published。短暂的 `REPORT_NOT_READY`/未就绪响应应作为等待信号，不要据此重复创建新对话或重复提交计划。

### 3. 阅读、切换格式并下载产物

10. 在左侧选择与当前主题/Session 匹配、带 `已完成` 状态的研究任务卡；不要选相邻旧 LLM 卡。`browser-identity.json` 记录选中卡 class 为 `research-task-card is-selected`，details Session 与 API Session 均为 `b4dfc9390b884b86b2d2b1045321625d`；`browser-selection.jpg` 显示该匹配关系。打开对应的 `研究已完成`通知卡后，检查右栏标题为 `只读报告`，状态为 `报告 v1 · 已完成`、`正式发布`。
11. 在右栏切换 `Markdown` 和 `HTML` 标签；本次两种格式均实测可读，内容属于同一 report_version v1。HTML 直接阅读页也已实测。
12. 点击与 Markdown、HTML、citation manifest 对应的下载链接。本次下载均 HTTP 200，且链接与下列 Artifact ID 对应；新运行的 ID 会变化，应按新任务的 Artifacts 响应匹配，不复用本次 ID。

| 产物 | 本次 Artifact ID | 本次下载状态 |
|---|---|---|
| Markdown | `ae94321e15f1431a85a40b127cd9fa87` | HTTP 200，SHA-256 匹配 |
| HTML | `a575eff722d046d6b0a26538a40c1a3e` | HTTP 200，SHA-256 匹配 |
| Citation manifest | `bcba50d0dede4797bb61ecb3598debaa` | HTTP 200，SHA-256 匹配 |

本次产物副本位于 `docs/sdd/plans/030/artifacts/20261031-methods-e2e/`：`report.md`、`report.html`、`citations.json`。可与右栏内容及当前任务的 report_version 对照。

## 成功与失败判据

**成功：** 页面已显示报告 v1 正式发布；正文 CJK 3,020（门槛 1,500）；5 篇逐篇分析、4 项比较、5 条 supported findings；Citation 5/5 有效；Markdown、HTML、manifest 三种 Artifact 均可阅读/下载且属于 v1。当前语义审核是人工 5/5 PASS；其中专家访谈是限定的人类参与研究方法，不是终端用户研究，不宣称四类方法均已全面覆盖。

**失败：** 首轮计划不含请求的主题/年份/USENIX/至少 5 篇约束；批准后没有任务推进；任务最终失败或报告没有正式发布；右栏状态与 API report_version 不一致；关键 Artifact 缺失、下载失败、版本不匹配或 hash 不符；最终人工内容 rubric 出现任何 FAIL。

## 失败恢复

- 若仍是任务进行中、report generating，或遇到本次那种早期 `REPORT_NOT_READY`/404：回到 `研究通知`，继续等相同 task 达到 completed/published，不重新创建任务。
- 若当前任务卡明确显示 `研究失败，可重试（第2次）`，先确认它对应当前任务，再按该卡片呈现的重试操作继续；这次截图核实了该 retryable 状态文案，但没有在当前成功任务上执行重试。若页面没有明确重试操作，保留 task ID 和错误提示并停止，不猜按钮、不重复提交。
- 若服务不可达：记录当前对话和 task ID；需要重新启动时按本节启动命令启动默认端口 8000，再从健康状态确认服务可访问。不要更改 Qwen/DeepSeek 的模型配置来处理服务问题。
- 若正文已完成但发布/下载失败：不要把草稿当正式产物；保留报告版本和 Artifact ID，报告给维护者核查。此恢复分支不覆盖或改写旧版本。

## 本次证据对照

- 自然语言输入与模型/effort：`docs/sdd/plans/030/artifacts/20261031-methods-e2e/request.json`
- 已执行请求的 method/path、payload/response 文件映射：`http-execution-record.json`（这是基于实际 tool 参数转录的执行记录，不是 HAR 或 wire capture）
- E2E ID、部署 commit 和最终状态：`execution-manifest.json`
- Intake SSE 与审批响应：`01-intake.sse`、`02-approval.json`、对应 `.headers`
- 报告状态和质量计数：`10-report.json`
- 产物 ID 与下载地址：`11-artifacts.json`
- 浏览器入口/审批/选中任务/报告/正文/HTML 截图：`browser-manual-entry.jpg`、`browser-plan-approval.jpg`、`browser-selection.jpg`、`browser-report.jpg`、`browser-body.jpg`、`browser-html.jpg`
- 浏览器所选卡与详情 Session 对照：`browser-identity.json`
- 下载 HTTP 状态与 hash：`download-verification.json`
