# BLOCKED — Spec032 Task14 fuzzing 专题真实自然语言 E2E

## 结论

本轮按交接要求使用当前部署 `e83fdd6`、全新自然语言 conversation，并限定
USENIX Security 2024 的模糊测试与漏洞发现、目标五篇、中文 Markdown/inline 引用。
服务前置门禁通过，但真实 `POST /api/conversations/messages` 在模型推理档位预检阶段
返回不可重试错误 `REASONING_EFFORT_UNSUPPORTED`（`retryable=false`），没有进入
Intake、计划、批准或 ResearchTask。

本轮没有切换 `reasoning_effort`、没有重试、没有创建第二 run，也没有修改模型、阈值、
环境或业务代码。结论为 **BLOCKED**；不存在可声称的五篇候选、导入、矩阵或报告证据。

## 运行与部署

- `run_id`: `spec032-task14-fuzzing-20261011T034710Z`
- 服务：`http://127.0.0.1:8000`
- 分支：`codex/spec032-final-acceptance`
- 部署提交：`e83fdd6f8a43484f42e06d69a0d57f29f408bf51`
- 请求级模型：`qwen3.5:9b`；`reasoning_effort=low`
- `/api/ready`：HTTP 200，`ready=true`；jieba、ollama_tags、embedding、qdrant 均为 `ready`
- 首页：HTTP 200，62488 bytes；实际资源 `styles.css?v=56`、`app.js?v=57`
- `/api/models`：HTTP 200，投影显示 qwen3.5:9b `ready` 且 capabilities 包含 `low`
- memory schema：此前只读核对为 `8`
- 当前 `AGENTS.md` 的主会话试行文档 dirty；本轮未修改该文件或业务代码

## 真实自然语言请求与错误

请求：

```text
请进行一次新的深度研究。研究主题限定为 USENIX Security 2024 的模糊测试与漏洞发现。
研究目标是比较至少5篇研究的方法与局限。请最少选择5篇论文，最多选择5篇论文，目标论文数为5；
来源限定为 USENIX Security，时间范围为 2024-2024；输出中文 Markdown 报告并使用行内引用；
生成计划后等待我批准。
```

真实响应为 HTTP 200 SSE：

- `conversation_id=604007cfb6cb4e7494b26d741ed59a98`
- `user_message_id=f98a2492eef040148f3986d54c0f8d0b`
- `assistant_message_id=66b53a70988347b4bc8f8088c66576c5`
- `event_seq=2`：`code=REASONING_EFFORT_UNSUPPORTED`
- `message=当前模型不支持该推理档位`
- `retryable=false`
- `done.status=failed`

虽然 `/api/models` 的能力投影列出 `low`，实际消息预检却拒绝该档位；这是本轮唯一
可复核的失败阶段，不能推断后续 Intake、计划或任务行为。没有 `research_session_id`、
`plan_version`、`output_hash`、approval、search ID 或 task ID。

## 下游验证边界

由于自然语言入口在 Intake 前失败，下列步骤均未执行且没有伪造响应：

- 未生成/批准计划，因此不能核对 `min=max=target=budget=5` 的实际 plan；
- 未运行 s1/s2/e1/c1/syn，未获得 raw tool 候选或 Search Worker 交接数量；
- 未产生候选选择、5 篇导入 IDs、acquisition batch 或 document IDs；
- 未读取 Evidence Matrix、legacy report、canonical JSON/Markdown/HTML 或 artifacts；
- 未重试该消息、未切换 `off`、未改全局模型/阈值/env、未从本地目录人工补选。

## 人工验收准备度

1. 服务已启动并可访问：**PASS**（ready/home 实测）。
2. 真实 API 创建入口成功：**FAIL**（消息已创建但主路径在档位预检失败）。
3. 主路径参数正确解析：**FAIL**（未进入 Intake）。
4. 任务/实体状态推进：**FAIL**（无 session/plan/task）。
5. 前端显示处理中提示：**FAIL**（本轮只验证 API，未执行 UI）。
6. 用户知道何时点击或等待：**FAIL**（入口不可继续）。
7. 核心业务产物：**FAIL**（无候选、导入、matrix 或报告）。
8. 失败状态有可操作恢复：**FAIL**（错误标记不可重试；未验证恢复）。
9. 页面状态与 API 状态一致：**FAIL**（未执行前端验收）。
10. 无上下文步骤可复现：**FAIL**（主路径未通过，UI 文案未验证）。

准备度为 `1/10`，存在模型能力预检 P1 阻塞，不能交付人工验收。

## 解除阻塞边界

需由部署/模型能力 owner 解释并修复“`/api/models` 宣称 qwen3.5:9b 支持 low、但实际
消息入口返回 `REASONING_EFFORT_UNSUPPORTED`”的环境或能力解析一致性。解除后必须用
全新 conversation/run 重做本 fuzzing 专题；本轮不把切换 off 或重跑当作成功证据。

## 未验证事项

未验证 fuzzing 主题的候选池、raw tool 候选与 Search Worker 交接数量、evaluator 选择、
5 篇导入、matrix 200、canonical 三格式正文/citations、artifact 下载、终态和前端人工
验收路径。

## 证据与日志

- 结构化证据：[current-research-e2e-fuzzing-evidence.json](/Users/wjh/ResearchAgent/docs/sdd/plans/032/artifacts/task-14/current-research-e2e-fuzzing-evidence.json)
- backend-tester 日志：[/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261011-fuzzing-e2e.md](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-032/task-14/backend-tester/20261011-fuzzing-e2e.md)

最终裁决：**BLOCKED**。错误发生在自然语言入口的模型推理档位预检，后续所有业务产物
均不可用；未进行任何绕过或盲目重试。
