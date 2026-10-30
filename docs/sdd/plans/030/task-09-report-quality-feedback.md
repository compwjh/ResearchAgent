# Task 09：前端报告质量与进度反馈

关联：Spec 030 2026-10-29 修订；依赖 Task 08 后端合同与 API。Task 02–06 的旧报告工作台保持可读。
状态：实施中。后端报告重生成、质量状态与发布接口已通过独立定向复审并部署，真实 report_version=2 已生成并发布；正文忠实度修订与前端反馈并行推进，Spec 尚未收口。

## 目标与角色边界

在现有研究工作台清楚区分正式报告、部分完成和未发布草稿，显示可复核的质量指标、当前阶段、已用时间与可操作的重试。frontend-dev 只改 frontend/**；frontend-reviewer 只评 frontend/**；frontend-tester 只跑前端契约/静态核对，不跑后端 pytest。

## 交互合同

- 复用现有报告区 research-report-state、research-report-limitations、版本选择器、Artifact 列表和现有事件流；不新增第二套研究任务/SSE 状态机。
- 对有 report-quality-v1 的版本显示正式发布/草稿状态、CJK 正文数/1,500、有效逐篇数/5、支持的综合发现数/3、当前 revision_count/2、证据等级与稳定缺项原因。历史版本缺字段时显示“旧版，未按本质量合同核验”，不得根据旧 status=completed 冒充通过。
- 每次用户主动“重试生成新版本”创建并持久化一个 UUID `Idempotency-Key`；同一次网络重试复用同 key。POST 202 仅表示受理，显示 generating/pending；收到 completed+published 后才显示正式完成。显示 report_url 与报告行 version；重复 key 返回同 report_version，新 key 才能新开版本。
- 从既有 report 事件显示证据整理、比较、写作、校验、定向补写、发布/保存草稿/失败阶段及已耗时间。离页后重进通过现有游标继续；不显示无测量依据的倒计时。
- 草稿可在现有 canonical Markdown/JSON 视图中查看；artifact list/download 已按后端规则隐藏 unpublished report_version，正式 Artifact 只在 published=true 时显示。质量失败保留旧版选择和下载不变，并显示可执行的“重试生成新版本”操作；每次重试采用后端返回的新 report_version，不覆盖原草稿或旧正式版。202/任务受理不能显示“报告已完成”。
- 所有提示使用 textContent/既有安全 Markdown 渲染；不将模型文本、错误栈或任意 HTML 写入 DOM。

## 变更面与验证

预期文件：frontend/research-tasks.js、frontend/index.html、必要时 frontend/styles.css。JS/CSS 变更后更新 index.html cache-bust 版本。扩展 tests/frontend/test_evidence_report_frontend_contract.py、test_research_session_workspace.js 与 test_report_action_race.js 覆盖缺字段旧版、质量状态、事件阶段、离页/重进、同 key 网络重试、新 key 主动重试、202 受理态、版本竞态、未发布 Artifact 隐藏与安全渲染；只做前端静态/契约验证和 node --check，不运行后端回归。

## 完成、失败与回滚

frontend-reviewer 需确认 DOM/CSS 契约、资源版本和 XSS 边界；frontend-tester 给出精确命令、退出码与结果。若后端没返回质量字段/版本身份，前端显示未知/草稿并在报告中标阻塞，不自行推断通过。回滚前端时旧字段路径仍能读取历史报告；删除缓存版本号变化会回退到现有工作台，不修改任何报告或 Artifact。
