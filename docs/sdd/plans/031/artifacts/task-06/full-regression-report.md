# Spec031 Task06 全量回归报告

## 固定字段

- spec：031 — 动态模型路由与资源调度优化
- task：Task06 — 最终评审、回归、基准、部署与复盘
- 角色：跨端 tester/reviewer
- 执行模型：Luna high（临时执行）
- 执行时间：2026-09-17 16:18–16:29 CST
- 范围：唯一一次全量 pytest、Task05 前端合同、差异/敏感字段/冲突标记扫描，以及 Task02–05 收口矩阵
- 初次执行时工作树：干净；初次报告未修改业务代码，未启动或修改 Ollama，未部署，未提交/推送。后续修复已在本 Task 范围内完成并复跑。

## 初始结论（历史记录）

**NO-GO（初次回归未通过；该结论已由后续修复与复跑取代）。**

Task05 前端合同和静态安全检查全部通过，Task02–05 的既有交接门禁仍可复核；但唯一一次全量 pytest 以退出码 1 结束，存在 4 个失败。失败不在 Spec031 改动文件或 Task02–05 定向集合中，其中两个是摘要/失败注入行为断言，两个是异步 worker 在测试等待窗口内仍为 `running`；不能把它们标记为“环境失败”或声称全量回归通过。按收口规则，先保留阻塞并停止，不自行修复或扩大范围。

## 全量回归

命令：

```text
.venv/bin/python -m pytest -q
```

- 退出码：`1`
- 结果：`2534 passed, 4 failed, 5 warnings, 67 subtests passed`
- 用时：`621.25s (0:10:21)`
- warnings：4 个 `SwigPy*`/`swigvarlink` `DeprecationWarning`（汇总显示为 5 warnings）

失败项：

1. `tests/test_conversation_compaction_summary.py::test_worker_writes_segment_and_finishes_done`：生成摘要缺少断言所需的 `【指令与约束】` 段。
2. `tests/test_conversation_compaction_summary.py::test_worker_failure_sets_failed_and_thread_alive`：注入 `build_rule_summary` 异常后任务仍为 `done`，预期为 `failed`。
3. `tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse`：2 秒等待窗口结束时 evolution checkpoint 仍为 `running`，预期为 `completed`。
4. `tests/test_memory_repositories.py::test_evolution_worker_consumes_more_than_1000_events_and_recovers`：5 秒等待窗口结束时 checkpoint 仍为 `running`，预期为 `completed`。

这 4 项属于 conversation compaction/evolution worker，不是 Spec031 Task02–05 的路由、观测、调度或前端 UI 合同；但它们是全量回归真实失败，故当前结论仍为 NO-GO。未将其归因为网络/Ollama 等环境故障：本次失败均为测试断言或异步状态断言，不能静默忽略。

## 前端合同与静态检查

| 检查 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/research-tasks.js` | 0 | 通过 |
| `node tests/test_frontend_spec034_task09.js` | 0 | `Task09 frontend Session/Fake-DOM contract: PASS` |
| Task05 + Spec034/030/029/028 前端合同 pytest | 0 | `43 passed in 0.99s` |
| `git diff --check` | 0 | 通过 |
| 工作树状态 | — | 干净，无未提交/未跟踪文件 |

静态扫描：

- 变更前端文件未发现 `innerHTML`、`outerHTML`、`insertAdjacentHTML`、`dangerouslySetInnerHTML` 或 `document.write`。
- 未发现从 `payload` 直接渲染 `prompt`、`answer`、`thought`、`chain_of_thought`、`owner_token` 或 `host_path` 的路径；敏感词只出现在 `safeRoutingText()` 的拒绝规则。
- 仓库未发现 `<<<<<<<` 或 `>>>>>>>` 冲突标记。文档中的普通 `====` 表格分隔线不属于冲突标记。

## Task02–05 最终矩阵

| 范围 | 证据与复核结果 | 收口判断 |
|---|---|---|
| Task02 benchmark/raw | `benchmark-raw.json` 固定 `[1,2,3,4]`、`qwen3.5:9b`、fixed prompt、cold/warm、失败率、TTFT、吞吐和 `size_vram` 均存在；单实例 cap=1，1–4 worker 仅观察，多实例无第二实例证据，维持 NO-GO。 | 单实例条件通过；质量响应与 provenance 已在 Task06 补齐；多实例不实施。 |
| Task03 value redaction / owner / shadow | `task-03/backend-report.md`、`review-report.md`：值级敏感内容在 service/store/Langfuse seam 拒绝；owner 读取/写入隔离；生产装配失败静默回退；shadow 仅计算候选，不改生产选择；定向 `111 passed, 5 subtests`。 | GO（保留报告中的 P2 idempotency 完整比较和 production outcome 接入建议）。 |
| Task04 four P1 | `task-04/review-report.md`：strong 原子单并发、过期 quota 回收、同 task grant 隔离、服务端质量/资源 evidence gate 四项均已关闭；定向 `154 passed, 5 subtests`。Task02 cap=1/多实例 NO-GO 约束保持。 | GO（保留控制面权限、runtime smoke、观测字段覆盖 P2；不扩大范围）。 |
| Task05 UI contract | `task-05/review-report.md`、`tester-report.md`：路由白名单/路径拒绝、严格数值边界、XSS/textContent、只读 active/shadow、DOM/CSS 作用域、`research-tasks.js?v=10` 均通过；本次复跑 Node/pytest 合同通过。 | GO（保留事件 `routing_benchmark` 投影遗漏 P2）。 |

## 修复与最终复跑

针对初次回归暴露的问题完成了定向修复：

- 压缩摘要先完成 durable checkpoint，再执行可选模型抽取，避免摘要缺段或失败状态被吞掉。
- 测试前后清理 evolution worker，并隔离 memory repository 的模型抽取 mock，消除跨用例残留 worker 与 mock 污染。
- benchmark 现在校验固定响应 JSON 为 `{"ok": true}`，并记录 `ResourceProbe`、可用内存、监听端口、运行时 provenance；多实例仍无证据，维持 NO-GO。
- evaluator 完成事件只投影安全的 `selected_paper_ids`，前端在报告生成前即可显示论文选集；不投影标题、摘要、Prompt 或思维链。

最终命令：

```text
.venv/bin/python -m pytest -q
```

- 退出码：`0`
- 结果：`2539 passed, 5 warnings, 67 subtests passed`
- 用时：`501.56s (0:08:21)`
- 部署 smoke：`GET /api/health=200`、`GET /=200`、前端资源 `research-tasks.js?v=10`

最终结论：**GO（单实例范围）**。Spec031 可收口；多 Ollama 实例仍为 NO-GO，不作为本 Spec 的已实现能力。

## 阻塞项与后续动作

已关闭的初始阻塞：全量回归失败与 benchmark 证据缺口均已修复并复跑通过。

保留边界：多实例没有独立实例和资源证据，继续保持 NO-GO；Langfuse 不可用只影响观测，不阻塞主流程。

后续动作：

- 不启动、下载、卸载或修改 Ollama；多实例维持 NO-GO。
