# Task 06：最终评审、全量回归、部署与复盘

> 关联：[Spec 027](../../specs/027-research-task-dynamic-orchestration-mvp.md) ｜ 索引：[README](./README.md)
> 依赖：Task02–05 全部完成且报告齐全；当前状态：`待执行`

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
- 全量回归只在本 Task 运行一次；失败必须修复后再以最终一次结果收口。
- 启动服务并验证健康页、首页、Research Task 完整案例；给出实际端口和命令。

## 风险、回滚与产出

- 任一 P0/P1、确定性测试失败或评审未签字时不得标记 Spec 完成。
- 外部网络/Ollama 超时可环境延期，但固定样本不能延期。
- 产出：三份评审、验收报告、复盘、部署证据；执行结果待填写。

## 变更日志

- 2026-09-12：创建最终收口 Task。
