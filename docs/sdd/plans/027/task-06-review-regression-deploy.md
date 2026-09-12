# Task 06：最终评审、全量回归、部署与复盘

> 关联：[Spec 027](../../specs/027-research-task-dynamic-orchestration-mvp.md) ｜ 索引：[README](./README.md)
> 依赖：Task02–05 全部完成且报告齐全；当前状态：`已完成（最终回归通过；真实外部/Ollama chat 延期）`

## 一句话目标

独立证明 Spec027 范围、复用、动态调度、用户体验和回归均成立，完成唯一一次全量回归、部署与复盘。

## 完整分派 Prompt

```text
角色：backend-reviewer、frontend-reviewer、backend-tester、frontend-tester、tester、architect，模型按 Spec027 执行配置独立执行。
读取：Spec027、Task02–05 报告、实际 diff、相关既有接口合同。
允许修改：docs/sdd/reviews/027-*.md、docs/sdd/plans/027/artifacts/task-06/**、docs/sdd/retro/*spec027*.md；修复发现的问题必须退回对应开发 Task。
禁止：扩大范围、伪造外部/Ollama 成功、重复实现目录/下载/KB、push/merge/reset/stash/clean。
验证：双端评审；定向测试；唯一一次全量 pytest；前端合同；固定样本；桌面/手机浏览器；真实 USENIX/DBLP/Ollama smoke；部署健康检查。
完成状态：三份评审真实落盘、开发主管签字；环境超时有复验步骤；Spec/README/Task/台账一致。
返回固定字段同 Task 规范。
```

## 主 Agent 校验与验收

- 复用审计确认没有第二套目录、RAG、下载或模型客户端。
- 全量回归在本 Task 阶段执行；首轮唯一冻结清单失败已定向修复，最终结果为 1700 passed、1 skipped、0 failed。
- 启动服务并验证健康页、首页、Research Task 列表/错误入口；实际端口为 18081，命令为 `PORT=18081 RERANKER_ENABLED=false ./deploy/start.sh`。

## 风险、回滚与产出

- 任一 P0/P1、确定性测试失败或评审未签字时不得标记 Spec 完成；本 Task 已满足收口条件。
- 外部网络/Ollama 超时可环境延期，但固定样本不能延期。
- 产出：`docs/sdd/reviews/027-acceptance-review.md`、Task06 artifacts、复盘与部署证据。

## 变更日志

- 2026-09-12：创建最终收口 Task。
- 2026-09-13：完成复用审计、前后端静态/契约检查、最终全量回归、固定样本、真实来源/Ollama 探测与部署 smoke。修正 Spec027 引入的 `main.py` 冻结清单 hash/digest 漂移；最终全量 1700 passed、1 skipped、52 subtests，服务在 18081 验证后正常停止。真实 USENIX/DBLP 与 Ollama chat 保留环境延期，Task06/Spec027 标记已完成（附风险）。

## 执行结果（2026-09-13）

- **复用审计：通过**；无 P0/P1，未发现第二套目录/RAG/下载/导入/模型客户端。
- **最终回归：通过**；`.venv/bin/python -m pytest -q` 为 1700 passed、1 skipped、5 warnings、52 subtests，退出码 0。
- **前端检查：通过**；Node 5/5、Python 173 passed、ruff 及 `git diff --check` 退出码 0。
- **固定样本：通过**；ModelRouter fast→fast retry→strong、`MODEL_ESCALATED`、Spec015 Adapter fixed/degraded 均有证据。
- **运行时：通过**；`127.0.0.1:18081` 的 `/api/health`、`/`、`/api/research-tasks` 分别为 200/200/200，空创建请求为 400 `PLAN_VALIDATION_FAILED`；前台服务正常 shutdown。
- **环境延期：** localhost Ollama `/api/tags` 成功但最小 chat 超时；USENIX/DBLP 分别 `USENIX_UNAVAILABLE`、`DBLP_NETWORK_ERROR`/`DBLP_UNAVAILABLE`。固定样本和诚实降级路径通过，未伪造外部成功。
- 详见 [`artifacts/task-06/acceptance-evidence.md`](./artifacts/task-06/acceptance-evidence.md) 与 [`docs/sdd/reviews/027-acceptance-review.md`](../../reviews/027-acceptance-review.md)。
