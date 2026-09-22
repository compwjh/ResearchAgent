# Spec032 / Spec039 准备度矩阵

| # | 门禁 | 结果 | 证据/缺口 |
|---:|---|---|---|
| 1 | 服务启动并可访问 | PASS | `/api/health`、`/api/ready` HTTP 200 |
| 2 | 真实 API 创建入口成功 | PASS | 运行 A 创建会话与 Intake |
| 3 | 主路径参数正确解析 | PASS | 运行 A `missing=[]`、时间范围确认 |
| 4 | 任务状态从初始态推进 | PASS | 运行 B 最终 `completed`，5 个 WorkItem completed |
| 5 | 前端处理中提示可见 | FAIL | API 已有阶段事件，但本轮未完成真实浏览器提示复核 |
| 6 | 用户知道何时点击/等待 | PASS | 本文已写明，但产品尚未验证 UI 文案 |
| 7 | 核心报告真实生成 | FAIL | 运行 B 有 Artifact，但内容是目录证据 ID 占位文本 |
| 8 | 失败状态可操作恢复 | FAIL | 本轮未完成真实登录/重试/重连闭环 |
| 9 | 页面状态与 API 状态一致 | FAIL | API 已完成，但本轮未完成真实浏览器投影复核 |
| 10 | 未读上下文用户可复现 | PASS（文档） | 步骤已具体化；实际 UI 仍待修复后复验 |

**总分：6/10（60%），低于 9/10 交付门槛。状态：`BLOCKED`。**

## 运行 D/E 复评（2026-09-20）

旧表保留运行 A–C 的失败证据；修复后的门禁按真实 API、真实浏览器和恢复接口重新计算：

| # | 门禁 | 最新结果 | 证据 |
|---:|---|---|---|
| 1 | 服务启动并可访问 | PASS | `http://127.0.0.1:18080/api/health` HTTP 200 |
| 2 | 自然语言 Intake | PASS | 运行 D `missing=[]`；运行 E 同样由聊天自然语言创建 |
| 3 | 参数、来源、时间范围 | PASS | 运行 D/E 均为 USENIX、2024–2024 |
| 4 | 任务终态推进 | PASS | 运行 D `completed`、5 个 WorkItem completed |
| 5 | 前端处理中提示 | PASS | 运行 E 浏览器展开“处理过程”看到 task/Worker/Skill/Tool 分阶段状态 |
| 6 | 用户知道等待和下一步 | PASS | 人工案例运行 D/E 写明点击、等待、通知和失败恢复 |
| 7 | 核心报告可读 | PASS | 运行 D Artifact `339d5e66f23a4deb9dc07e9759148613`，5 篇标题/摘要/关键词/URL |
| 8 | 失败状态可恢复 | PASS | 真实 `recover` 接口返回 `recovery_required`、checkpoint/lease 状态 |
| 9 | 页面与 API 状态一致 | PASS | CUA 复核运行 D 会话显示 5 篇报告和“研究已完成 · 报告 v1” |
| 10 | 人工案例可复现 | PASS | `artifacts/spec032-manual-acceptance.md` 运行 D/E |

**最新准备度：10/10；技术修复门禁：通过。** 运行 E 的任务本身仍作为处理中/部分完成边界样本保留，不替代运行 D 的成功报告；只有运行 D 的完整报告用于最终人工内容验收。
